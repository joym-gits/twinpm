"""Static synthetic content for the NovaPay "Checkout 2.0" demo dataset."""

from __future__ import annotations

from typing import TypedDict


class DocSpec(TypedDict):
    key: str
    type: str
    title: str
    author: str
    days_ago: int
    body: str


class OptionSpec(TypedDict):
    name: str
    pros: str
    cons: str


class DecisionSpec(TypedDict):
    key: str
    title: str
    context: str
    options: list[OptionSpec]
    chosen_option: str
    rationale: str
    participants: list[str]
    days_ago: int
    source_doc: str | None


class FeedbackTheme(TypedDict):
    label: str
    summary: str
    count: int
    sentiment_mean: float
    sentiment_sd: float
    growth: str
    segments: list[str]
    sentences: list[str]


DESIGN_DOCS: list[DocSpec] = [
    {
        "key": "payments-api-v2",
        "type": "design_doc",
        "title": "Payments API v2",
        "author": "vikram",
        "days_ago": 165,
        "body": """# Payments API v2

## Context

The v1 Payments API grew organically over four years. It mixes resource styles, has no
consistent error envelope, and paginates with offset/limit, which degrades past 100k rows.
Checkout 2.0 needs a clean public surface. Mobile checkout UI, the Platform rate limiter and
Fraud hooks all depend on this API, which makes it the critical path for the program.

## Goals

- Resource-oriented REST API covering payments, refunds, payment methods and customers.
- p99 latency under 250 ms for create/capture, p50 under 80 ms, at a sustained 1,200 RPS.
- Availability SLO of 99.95% measured monthly at the edge.
- Cursor-based pagination on every list endpoint.
- Idempotent writes via the Idempotency keys epic.

## Non-goals

- Replacing the ledger or settlement pipeline.
- A GraphQL surface. Partners have not asked for it.
- Backfilling v1 clients; v1 is frozen and sunset 12 months after launch.

## Design

The API is a Go service behind the shared gateway. Every mutating endpoint accepts an
`Idempotency-Key` header. Errors use a single envelope with `code`, `message`, `request_id`
and optional `details`. Versioning is path-based (`/v2`), with additive changes only inside a
major version.

Payment lifecycle: `created -> authorized -> captured -> settled`, with `failed`, `voided`
and `refunded` terminal states. Refunds are a sub-resource with their own state machine, so
partial and multiple refunds are first class. State changes emit events consumed through
Event streaming for payment events.

## API and data model

- `POST /v2/payments`, `GET /v2/payments/{id}`, `POST /v2/payments/{id}/capture`
- `POST /v2/payments/{id}/refunds`, `GET /v2/payments?cursor=...&limit=50`
- Cursors are opaque, signed base64 tokens encoding `(created_at, id)`.
- `payments` table partitioned monthly; hot index on `(merchant_id, created_at, id)`.

## Risks

- Refund endpoints are the most complex surface and the least staffed (Payments is stretched).
- Fraud hooks add a synchronous call on the create path; budget is 40 ms of the 250 ms p99.
- Mobile cannot start integration testing until the OpenAPI spec is published.

## Open questions

- Do we expose webhooks signing keys per merchant or per environment?
- Should list endpoints support filtering by arbitrary metadata at launch?

## Alternatives considered

We considered evolving v1 in place and rejected it: the inconsistent resource shapes would
leak into every new client, and the offset pagination cannot be fixed without a breaking
change. We also considered a thin v2 facade over v1 handlers, but that would double the
number of code paths on the critical path. A clean service lets us delete v1 after the
sunset window and keeps the testing matrix small for Mobile and partners alike.

## Rollout

Internal dogfood at week 6, partner beta at week 10 behind a feature flag, and general
availability with the public launch. v1 and v2 run side by side for the whole period.
""",
    },
    {
        "key": "rate-limiter",
        "type": "design_doc",
        "title": "Platform rate limiter",
        "author": "ananya",
        "days_ago": 150,
        "body": """# Platform rate limiter

## Context

Today each service rolls its own throttling, and an abusive merchant integration took down
the v1 capture path twice last year. Payments API v2 will be exposed publicly, so we need a
single, shared limiter at the gateway before launch.

## Goals

- Enforce per-API-key and per-IP limits at the gateway with under 2 ms added p99 latency.
- Support burst tolerance: default 100 RPS sustained with bursts to 300 RPS per key.
- Handle 5,000 RPS aggregate with headroom, and degrade open on limiter failure.
- Return standard `429` responses with `Retry-After` and `RateLimit-*` headers.

## Non-goals

- Billing-grade usage metering. That is a separate pipeline.
- Per-endpoint cost weighting in the first release.
- Bot detection; the Fraud hooks epic owns risk signals.

## Design

We use a token bucket per key, implemented as an atomic Lua script in Redis (cluster mode,
three shards). The bucket stores `tokens` and `last_refill`; the script refills lazily and
decrements in one round trip. A local in-process cache of recent denials avoids hammering
Redis for keys that are already blocked.

If Redis is unreachable for more than 200 ms the gateway fails open and raises an alert,
because blocking real payments is worse than a short window of unthrottled traffic.

## Configuration and data model

- Limits live in a `rate_limit_policies` table in Postgres, synced to Redis every 30 s.
- Tiers: `default`, `partner`, `internal`. Overrides per merchant require Platform approval.
- Metrics: allowed, throttled and fail-open counts per policy, exported through the
  Checkout observability pipeline.

## Risks

- Redis is a new hard-ish dependency on the hot path; mitigated by fail-open and replicas.
- Clock skew across gateways could distort refills; we use Redis server time only.
- The limiter cannot be fully tested until Payments API v2 stabilizes real traffic shapes.

## Open questions

- Do mobile SDK calls share the merchant bucket or get their own?
- Should idempotent retries count against the limit?

## Alternatives considered

An in-process limiter per gateway pod is simple but allows N times the intended rate when
pods scale out. A sliding window log is exact but costs too much memory at 5,000 RPS. A
managed edge limiter was evaluated; it lacks per-merchant policy sync and adds a second
vendor to the hot path. The Redis token bucket gives bursts, shared state and a small,
well-understood failure mode, which is why we picked it for launch.

## Rollout

Shadow mode (log only) for two weeks, then enforce for `default` tier, then partners. A
load test at 5k RPS gates the enforcement step. Kill switch is a single feature flag.
""",
    },
    {
        "key": "mobile-checkout",
        "type": "design_doc",
        "title": "Mobile checkout UI",
        "author": "rohan",
        "days_ago": 140,
        "body": """# Mobile checkout UI

## Context

The current mobile checkout is two separate native flows with diverging behavior and a 4.1%
higher drop-off than web. Checkout 2.0 introduces a single shared checkout experience for
iOS and Android that consumes Payments API v2.

## Goals

- One codebase for checkout screens, with native wallet handoff for Apple Pay and Google Pay.
- Time to interactive under 1.2 s on a mid-range Android device, 60 fps transitions.
- Crash-free sessions above 99.8% at launch.
- Accessibility: full VoiceOver and TalkBack coverage, dynamic type up to 200%.

## Non-goals

- Rewriting the rest of the app in React Native.
- Offline payment initiation.
- Tablet-specific layouts at launch.

## Design

Checkout is a React Native module embedded in the existing native shells. Navigation, state
and API access live in TypeScript; native modules cover wallet sheets, biometrics, and
secure card entry. State is managed with a small reducer-based store and a typed client
generated from the Payments API v2 OpenAPI spec, which is why Mobile is blocked until that
spec lands.

Screens: cart summary, payment method selection, saved cards, review, result. Errors map to
the API error envelope codes so copy can be localized without string matching.

## Integration points

- iOS wallet integration and Android wallet integration deliver native modules exposing
  `presentWalletSheet()` and a token callback.
- Rate limit responses (`429`) trigger exponential backoff with jitter, max three retries.
- Idempotency keys are generated client-side per checkout attempt (UUIDv4).

## Risks

- Bridge overhead on low-end devices; we budget a perf spike in week 3.
- Wallet SDK upgrades may lag behind OS releases.
- Spec churn in Payments API v2 forces client regeneration and re-testing.

## Open questions

- Do we ship the module via over-the-air updates or only with store releases?
- How do we handle in-flight payments if the app is killed mid-authorization?

## Success metrics

- Checkout conversion on mobile improves by 3 points against the current baseline.
- Median time from cart to confirmation drops from 41 s to under 30 s.
- Wallet sheet opens within 300 ms of the tap on 95% of devices.
- Support contacts tagged as checkout issues fall by 20% within a quarter of launch.
- Payments API v2 error rates seen from mobile stay under 0.5% excluding user cancellations.
We will review these weekly with Platform and Payments during the staged rollout.

## Rollout

Internal builds in week 8, 5% staged rollout through feature flags, ramping to 100% over
three weeks as crash and conversion metrics hold.
""",
    },
    {
        "key": "fraud-hooks",
        "type": "design_doc",
        "title": "Fraud hooks",
        "author": "meera",
        "days_ago": 130,
        "body": """# Fraud hooks

## Context

Fraud scoring currently runs as a batch job after capture, so we find bad transactions after
money moves. Checkout 2.0 should evaluate risk before authorization. This work extends
Payments API v2 with pre-authorization hooks and cannot ship until that API is stable.

## Goals

- Synchronous risk check on payment creation with a 40 ms p99 budget.
- Asynchronous post-event analysis on the event stream for patterns spanning many payments.
- Decisions: `allow`, `review`, `block`, with reason codes visible to support.
- Chargeback rate below 0.35% of volume at launch.

## Non-goals

- Building our own ML models; we call the vendor scoring service and an internal rules engine.
- Manual review tooling. That is a later program.
- Account-level fraud (login, takeover).

## Design

A hook interface sits in the create-payment handler. It calls the rules engine in process
(velocity, geography, BIN checks) and the vendor score over HTTP with a hard 30 ms timeout.
On timeout we fall back to rules-only and tag the payment `degraded_risk`. Decisions are
persisted in a `risk_decisions` table and emitted as events.

Asynchronous analyzers consume payment events from Kafka and can raise a hold on captured
but unsettled payments before the settlement cut-off.

## Data model

- `risk_decisions(payment_id, decision, score, reasons jsonb, latency_ms, created_at)`
- Rules are versioned config reloaded without deploy; every decision stores the rules version.

## Risks

- Latency budget is tight; the vendor p99 today is 55 ms, so timeout fallback is essential.
- False positives hurt conversion; we target under 0.8% unnecessary blocks.
- Dependence on Payments API v2 schedule.

## Open questions

- Should `review` decisions hold funds or allow capture with a delayed hold?
- How is vendor PII handling scoped under the data retention policy?

## Success metrics

- Pre-authorization blocks catch at least 60% of fraud that is currently found only after
  capture, measured over the first eight weeks of shadow scoring.
- Added latency from the hook stays under 40 ms at p99, and the degraded fallback is used
  for fewer than 2% of requests.
- Unnecessary blocks stay below 0.8% of legitimate volume.
- Every decision is explainable from stored reason codes within one support interaction.
Results feed back into the rules versioning process so tuning does not require deploys.

## Rollout

Shadow scoring for four weeks, then enforce `block` only, then `review`. Per-merchant
overrides are available for the partner beta.
""",
    },
    {
        "key": "observability",
        "type": "design_doc",
        "title": "Checkout observability",
        "author": "marcus",
        "days_ago": 120,
        "body": """# Checkout observability

## Context

When checkout latency spiked last quarter it took three hours to find that a downstream
vendor call was responsible. Logs, metrics and traces live in separate tools with no shared
request identifier. Checkout 2.0 launches publicly, so we need one coherent picture.

## Goals

- End-to-end tracing from mobile and web clients through gateway, Payments and Platform.
- Golden-signal dashboards per service, and SLO burn-rate alerts for checkout success.
- Mean time to detect under 5 minutes, mean time to diagnose under 20 minutes.
- Log volume held under 1.5 TB/day with sampling.

## Non-goals

- Replacing the existing metrics vendor this year.
- Business analytics; product events go through the analytics pipeline.
- Full session replay.

## Design

We standardize on OpenTelemetry for traces, metrics and logs. Every service uses the shared
Go and TypeScript middleware, which propagates W3C `traceparent` and attaches `request_id`.
Collectors run as a daemonset and forward to the vendor backend. Tail-based sampling keeps
100% of errors and slow traces (over 500 ms) and 5% of the rest.

Payment events from Event streaming for payment events carry the trace id, so an async
fraud decision links back to the originating request.

## Key SLOs

- Checkout success rate: 99.5% over 30 days.
- Payments API v2 create p99: 250 ms; capture p99: 300 ms.
- Rate limiter added latency p99: 2 ms.
- Event consumer lag: under 5 s at p99.

## Risks

- Instrumentation overhead on mobile; we cap trace export to Wi-Fi or batched uploads.
- Cardinality explosions from labels such as merchant id; enforce allowlists.
- PII leaking into spans; scrubber is mandatory in the middleware.

## Open questions

- Do we need per-merchant SLO views for partners at launch?
- Who is on call for the collectors themselves?

## Alerting and ownership

Alerts page the owning team only when an SLO burn rate predicts budget exhaustion within
six hours; everything else goes to a ticket queue. Each service owns its dashboards and
runbooks, while Platform owns the collectors and shared middleware. A weekly review looks
at the noisiest alerts and retires or tunes them, with a goal of fewer than five pages per
on-call week during the launch period. Synthetic checkout probes run every minute from two
regions to catch failures before customers report them.

## Rollout

Instrument Payments and gateway first (week 4), then Platform, then mobile SDK. Dashboards
and alerts must be in place before the partner beta.
""",
    },
    {
        "key": "data-retention",
        "type": "design_doc",
        "title": "Data retention policy",
        "author": "liwei",
        "days_ago": 110,
        "body": """# Data retention policy

## Context

Payment data currently has no uniform retention. Some tables grow without bound, which
inflates storage cost (about 38 TB in the primary cluster) and complicates privacy requests.
Checkout 2.0 adds new data classes, so we need rules before launch.

## Goals

- A written retention schedule per data class, enforced automatically.
- Meet regulatory minimums: 7 years for ledger and settlement records, 5 years for KYC.
- Delete or anonymize personal data within 30 days of a verified erasure request.
- Reduce primary Postgres storage growth to under 4% per month.

## Non-goals

- Legal hold tooling; handled by the Compliance team.
- Rewriting historical archives older than 2019.

## Design

Data is classified into four tiers: ledger, transactional, operational and ephemeral.

- Ledger (7 years): immutable, never anonymized, archived to cold storage after 18 months.
- Transactional (24 months hot, then archived): payments, refunds, payment methods.
- Operational (90 days): risk decisions, request logs, webhooks deliveries.
- Ephemeral (24 hours to 7 days): idempotency keys, rate limit counters, sessions.

Monthly partitions make drops cheap. A retention worker detaches expired partitions and
writes a signed deletion manifest. Personal fields are tokenized so erasure only requires
deleting the token mapping, leaving the ledger intact.

## Data model

- `retention_policies(data_class, ttl, action, owner)`
- `deletion_manifests(partition, rows, checksum, executed_at)`

## Risks

- Partition detach locks if not scheduled off-peak; run in the low-traffic window.
- Conflict between erasure rights and ledger immutability; tokenization is the answer.
- Idempotency keys expiring early could allow duplicate charges (see Idempotency keys).

## Open questions

- Is cold storage in-region for all markets, including India?
- Do audit logs count as ledger data?

## Success metrics

- Primary cluster storage growth falls from about 9% to under 4% per month within a quarter.
- Erasure requests complete within the 30 day commitment in 100% of audited cases.
- Zero ledger rows are lost or altered by retention jobs, verified by checksum manifests.
- Retention jobs complete inside the low-traffic window without lock waits above 1 s.
The Compliance team receives the deletion manifests monthly for audit evidence and sign-off.

## Rollout

Document and approve in week 2, implement worker in week 6, dry-run for one month before
enabling deletes in production.
""",
    },
    {
        "key": "idempotency-keys",
        "type": "design_doc",
        "title": "Idempotency keys",
        "author": "karan",
        "days_ago": 100,
        "body": """# Idempotency keys

## Context

Mobile clients on flaky networks retry payment requests, and v1 has produced duplicate
charges in roughly 0.02% of retried captures. Payments API v2 must make every write safe to
retry. This design defines the key contract and its storage.

## Goals

- Any `POST` carrying an `Idempotency-Key` executes at most once per 24 hours.
- Replays return the original response, status code and body, byte for byte.
- Added latency under 5 ms p99 on the write path.
- Support 1,500 key writes per second with no single hot row.

## Non-goals

- Exactly-once delivery of downstream events; consumers must still be idempotent.
- Keys for `GET` requests.

## Design

Clients send a UUID in the `Idempotency-Key` header. On arrival the handler inserts a row
into `idempotency_keys` inside the same Postgres transaction that creates the payment, so
the key and the side effect commit atomically. Redis was rejected because a cache loss could
silently allow a duplicate charge.

A request hash (method, path, body digest) is stored. Reusing a key with a different payload
returns `422 idempotency_key_reuse`. Concurrent duplicates hit a unique constraint and wait
on an advisory lock, then return the stored result.

## Data model

- `idempotency_keys(key, merchant_id, request_hash, status, response jsonb, created_at,
  expires_at)`; unique on `(merchant_id, key)`.
- Rows expire after 24 hours; a sweeper drops monthly partitions, per the Data retention
  policy, and hourly deletes handle the tail.

## Risks

- Table churn increases vacuum pressure; partitioning and aggressive autovacuum tuning.
- Large stored responses; we cap stored body at 16 KB and store a pointer beyond that.
- Mobile clients must regenerate keys only on new user intent, not on every retry.

## Open questions

- Should webhooks deliveries reuse the same mechanism?
- Is 24 hours long enough for delayed settlement retries?

## Alternatives considered

A Redis-backed store with a 24 hour TTL is faster, but a failover can drop recent keys and
let a retry charge twice. A dedicated key-value service adds another system to run for a
modest table. Deduplicating downstream by natural keys such as order id was also discussed,
though it cannot cover payments created without an order. Writing the key in the same
Postgres transaction is the only option that makes the guarantee atomic by construction.

## Rollout

Ship behind a flag on `POST /v2/payments`, enforce for refunds next, and make the header
mandatory for partners at general availability.
""",
    },
    {
        "key": "event-streaming",
        "type": "design_doc",
        "title": "Event streaming for payment events",
        "author": "marcus",
        "days_ago": 90,
        "body": """# Event streaming for payment events

## Context

Payment state changes are consumed by fraud analyzers, the ledger, notifications and
analytics. Today each integration polls the database or receives ad hoc webhooks. We need
a durable, ordered event backbone for Checkout 2.0 before Fraud hooks and Checkout
observability can rely on it.

## Goals

- Publish every payment and refund state change exactly once per transition (at-least-once
  delivery with idempotent consumers).
- Ordered per payment: events for the same `payment_id` arrive in order.
- Sustain 3,000 events/s with 5x headroom; end-to-end lag under 5 s at p99.
- Replay any consumer from an arbitrary timestamp within 14 days.

## Non-goals

- A general-purpose company-wide bus.
- Streaming PII; events carry tokens and ids only.

## Kafka vs SQS

- Ordering: Kafka orders strictly within a partition, and keying by `payment_id` gives
  per-payment ordering at any scale. SQS FIFO orders per message group, but throughput per
  group is limited and standard queues give no ordering at all.
- Replay: Kafka retains the log, so consumers can rewind offsets and reprocess. SQS deletes
  messages on ack; replay needs a separate archive and custom tooling.
- Throughput: Kafka handles hundreds of thousands of messages per second per cluster. SQS FIFO
  is capped around 3,000 messages/s per queue even with high-throughput mode tuning.
- Ops cost: SQS is near zero to operate. Kafka needs capacity planning, upgrades, and
  partition management, roughly 0.5 engineer of ongoing effort.
- Managed vs self-run: we would use a managed Kafka service, which removes broker upkeep but
  costs about 2.5x the SQS bill at our volume.

We conclude Kafka. Replay and per-key ordering matter more to fraud and the ledger than the
extra operational cost, and managed hosting keeps that cost bounded.

## Design

Topic `payments.events.v1`, 24 partitions, replication factor 3, keyed by `payment_id`.
Producers use the transactional outbox pattern from Postgres to avoid dual writes. Schemas
use Avro with a registry and backward-compatible evolution only.

## Risks

- Hot partitions from large merchants; we key on payment, not merchant.
- Consumer lag during deploys; rolling restarts and cooperative rebalancing.
- Team Kafka expertise is concentrated in Platform.

## Open questions

- Cross-region replication for the India launch?
- Dead-letter topic ownership per consumer.

## Success metrics

- Consumer lag stays under 5 s at p99 during peak, with alerts at 5 s.
- Zero lost events in a monthly reconciliation between the outbox and the topic.
- Fraud analyzers and the ledger replay a 24 hour window in under 30 minutes.
- Managed cluster cost stays within the approved budget of roughly three times the SQS
  estimate, reviewed quarterly by Platform and Finance.

## Rollout

Dual-publish alongside webhooks for four weeks, migrate fraud analyzers first, then ledger.
""",
    },
]

_ARCH_TRANSCRIPT = """\
Priya: Thanks everyone for joining. Goal today is to lock the open items on Payments API v2.
Priya: Rohan, Mobile is blocked on the spec, so give us the view from your side first.
Rohan: We can't generate the typed client until the OpenAPI spec is stable. Two sprints idle.
Vikram: Understood. The spec is about eighty percent there, refunds are the gap.
Karan: On list endpoints, offset pagination is already hurting us in v1 past a hundred k rows.
Li: Agreed, deep offsets scan and discard rows. Keyset on created_at and id is much cheaper.
Rohan: Mobile prefers cursors anyway, infinite scroll on the order history screen.
Priya: Okay, let's go with cursor-based pagination for the Payments API v2 list endpoints.
Vikram: Fine by me. Cursors are opaque and signed so we can change internals later.
Priya: Next, idempotency. Where do the keys live?
Li: Postgres, in the same transaction as the payment. Redis can lose data on failover.
Ananya: Redis is faster but a lost key means a duplicate charge. Not worth it.
Karan: Twenty-four hours covers every retry window we have seen in the mobile logs.
David: And that lines up with the retention tiers Li wrote for ephemeral data.
Priya: So, we're agreed that idempotency keys are stored for 24 hours in Postgres, not Redis.
Marcus: Noted, I will add the table to the dashboards.
Priya: Now events. Marcus has been quiet but the Kafka versus SQS question keeps coming back.
Ananya: Replay matters for fraud, and ordering by payment id is non-negotiable for the ledger.
Meera: Fraud analyzers need to rewind. With SQS we would be building that archive ourselves.
David: Cost is higher, but finance already signed off on the managed cluster.
Priya: Then we'll stick with Kafka for payment events, SQS is off the table for launch.
Priya: Let's talk about the pace of reviews. Payments PRs are sitting for three or four days.
David: That is mostly on Vikram's queue. He is on every review and half the incidents.
Vikram: Honestly I am stretched thin. I am the bottleneck and I know it.
Karan: I have capacity. I know the Go code from the gateway and I want to learn payments.
Vikram: That would help a lot, especially on the refund endpoints, they are the tricky part.
David: Karan reviewing first pass on Payments PRs would cut the wait roughly in half.
Priya: Good. Let's turn that into concrete follow-ups before we hang up.
Priya: Karan, can you pair with Vikram on the refund endpoints by Wednesday?
Karan: Happy to. I will block the mornings for it.
Vikram: I'll publish the v2 OpenAPI spec by Tuesday.
Rohan: That unblocks us. Thank you.
Priya: Rohan, can you confirm the mobile client handles cursor pagination by Monday?
Rohan: Yes, we will spike it against the mock server.
Priya: Li, can you write the idempotency keys migration with the expiry sweeper by Thursday?
Li: Yes. I want the partitioning reviewed by Marcus as well.
Marcus: Sure, send it over when it is ready.
Ananya: I'll load-test the rate limiter at 5k RPS by Friday.
Priya: Meera, can you draft the refund state machine diagram by Wednesday?
Meera: On it. I want fraud holds in the same diagram.
David: One concern, the fraud hooks timeline depends entirely on the spec date.
Vikram: If the spec slips past Tuesday I will flag it in the channel right away.
Ananya: The limiter shadow mode is ready, so enforcement is not on the critical path.
Rohan: Wallet integration is on track on both platforms, no new risks from Mobile.
Priya: Great. I will send notes tonight and update the risk register tomorrow morning.
Priya: Thanks all, that was a productive hour.
"""

MEETING_NOTES: list[DocSpec] = [
    {
        "key": "weekly-sync-w1",
        "type": "meeting_notes",
        "title": "Program sync - kickoff and dependency map",
        "author": "priya",
        "days_ago": 170,
        "body": """# Program sync - Checkout 2.0 kickoff

## Attendees

Priya Sharma, Arjun Mehta, Grace Lee, David Kim, Fatima Al-Sayed, Ananya Iyer,
Vikram Rao, Rohan Gupta.

## Notes

- Reviewed the 16-week-to-launch plan and the eight epics in scope.
- Payments API v2 is the critical path. Mobile checkout UI, Platform rate limiter and Fraud
  hooks all depend on it, so any slip there moves the launch.
- Platform confirmed capacity for Idempotency keys and Checkout observability in parallel.
- Mobile asked for a draft OpenAPI spec within three weeks to start client generation.
- Payments flagged that the refund surface is larger than the original estimate.

## Decisions

- Weekly program sync moves to Tuesdays at 10:00.
- Payments API v2 is the single source of truth for the dependency map.
- Arjun owns the epic-level status page; Priya owns the risk register.

## Action items

- Vikram: share a first spec outline with Mobile.
- Ananya: size the rate limiter and event streaming work.
- Arjun: set up epic dashboards and the status template.
- Priya: publish the dependency map and the risk register.
""",
    },
    {
        "key": "design-review-api",
        "type": "meeting_notes",
        "title": "Design review - Payments API v2",
        "author": "arjun",
        "days_ago": 155,
        "body": """# Design review - Payments API v2

## Attendees

Vikram Rao, Karan Malhotra, Meera Nair, Aisha Khan, Li Wei, Arjun Mehta, David Kim.

## Notes

- Vikram walked through the resource model, lifecycle states and error envelope.
- Karan raised that offset pagination will not scale and proposed cursors.
- Aisha reviewed OAuth scopes; partners need a read-only scope for reconciliation.
- Li wants monthly partitioning on the payments table before launch volumes arrive.
- Meera noted fraud hooks need a pre-authorization extension point in the create handler.
- Concern: the refund state machine is not fully specified yet.

## Decisions

- REST over gRPC for the public API; gRPC stays internal.
- Cursor-based pagination is preferred; a final call is deferred to the next review.
- Error envelope is frozen as drafted.

## Action items

- Vikram: add the refund sub-resource to the spec.
- Aisha: define the OAuth scope matrix.
- Li: share the partitioning plan.
- Arjun: collect written review comments by Friday.
""",
    },
    {
        "key": "sprint-review-1",
        "type": "meeting_notes",
        "title": "Sprint review - sprint 3",
        "author": "arjun",
        "days_ago": 140,
        "body": """# Sprint review - sprint 3

## Attendees

Arjun Mehta, Priya Sharma, Grace Lee, Fatima Al-Sayed, Ananya Iyer, Rohan Gupta,
Meera Nair, Marcus Johnson.

## Notes

- Platform rate limiter: token bucket prototype passes unit tests; Redis script reviewed.
- Checkout observability: collectors deployed to staging; first traces visible end to end.
- Mobile checkout UI: navigation skeleton done, blocked on the typed client.
- Payments API v2: create and capture endpoints implemented; refunds not started.
- Velocity was 34 points against a plan of 40, mostly because of review wait time.

## Decisions

- Move two small Payments tickets to Platform engineers for review cover.
- Demo format stays as recorded walkthroughs, with live Q and A.

## Action items

- Marcus: add sampling configuration to the collector chart.
- Rohan: mock the API so Mobile can progress without the spec.
- Meera: write up the fraud hook interface for review.
- Arjun: track review wait time as a sprint metric.
""",
    },
    {
        "key": "mobile-design-review",
        "type": "meeting_notes",
        "title": "Mobile design review - checkout flow",
        "author": "rohan",
        "days_ago": 125,
        "body": """# Mobile design review - checkout flow

## Attendees

Rohan Gupta, Emily Chen, Kwame Mensah, Neha Joshi, Lucas Silva, Fatima Al-Sayed,
Arjun Mehta.

## Notes

- Neha presented the five-screen flow: cart, method selection, saved cards, review, result.
- Emily raised Apple Pay sheet timing: the sheet must open within 300 ms of the tap.
- Kwame flagged Google Pay tokens expire quickly, so we should fetch them late.
- Lucas measured bridge overhead on a low-end Android device: cold start adds about 180 ms.
- Accessibility audit found two contrast issues on the review screen; both fixed in design.
- Discussed React Native for the shared module versus two native implementations.

## Decisions

- Build the checkout UI in React Native with native wallet modules.
- Saved cards are shown first, with the last-used method preselected.

## Action items

- Lucas: profile cold start with and without Hermes precompilation.
- Emily and Kwame: draft the wallet module interface.
- Neha: update the designs with the contrast fixes.
- Rohan: confirm the staged rollout plan with Fatima.
""",
    },
    {
        "key": "risk-review-1",
        "type": "meeting_notes",
        "title": "Risk review - first full pass",
        "author": "priya",
        "days_ago": 110,
        "body": """# Risk review - first full pass

## Attendees

Priya Sharma, Arjun Mehta, Grace Lee, David Kim, Fatima Al-Sayed, Vikram Rao,
Ananya Iyer.

## Notes

- R1: Payments API v2 slipping delays every dependent epic. Likelihood high, impact high.
- R2: Vikram is overloaded; review latency on Payments PRs is up to four days.
- R3: Redis becomes a new dependency in the hot path for the rate limiter.
- R4: Wallet SDK upgrades lag behind iOS and Android releases.
- R5: Vendor fraud scoring p99 is 55 ms against a 40 ms budget.
- Fraud hooks cannot start integration testing until the create endpoint is stable.

## Decisions

- Escalate R2 to Grace and David; look for reviewer cover from Platform.
- Add a timeout fallback to the fraud hook design rather than negotiating with the vendor.
- Keep the rate limiter fail-open.

## Action items

- David: propose a reviewer rotation for Payments.
- Meera: add the timeout and degraded-risk path to the Fraud hooks doc.
- Priya: re-score risks weekly and add owners to each line.
""",
    },
    {
        "key": "weekly-sync-w9",
        "type": "meeting_notes",
        "title": "Program sync - week 9",
        "author": "priya",
        "days_ago": 90,
        "body": """# Program sync - week 9

## Attendees

Priya Sharma, Arjun Mehta, Ananya Iyer, Vikram Rao, Rohan Gupta, David Kim,
Marcus Johnson.

## Notes

- Event streaming doc reviewed. Marcus summarized the Kafka versus SQS comparison.
- Payments API v2 spec at roughly 70 percent; refunds remain open.
- Idempotency keys design approved; migration to be scheduled.
- Mobile is idle on API-dependent tickets for the second week running.
- Observability dashboards now show create latency, currently 310 ms p99 against a 250 ms goal.

## Decisions

- Use Kafka over SQS for payment events.
- Idempotency keys will be stored in Postgres.
- Platform will provide a mock server so Mobile can keep moving.

## Action items

- Marcus: provision the managed Kafka cluster in staging.
- Vikram: publish an interim spec revision covering create and capture.
- Ananya: stand up the mock server from the interim spec.
- Arjun: update the status page with the dependency delays.
""",
    },
    {
        "key": "exec-checkpoint-1",
        "type": "meeting_notes",
        "title": "Exec checkpoint - Checkout 2.0",
        "author": "priya",
        "days_ago": 75,
        "body": """# Exec checkpoint - Checkout 2.0

## Attendees

Rahul Verma, Priya Sharma, Grace Lee, David Kim, Fatima Al-Sayed, Arjun Mehta.

## Notes

- Priya presented status: overall amber. Payments API v2 is the main source of risk.
- Rahul asked what a one-month slip would cost; Priya answered the partner launch window
  would be missed and the marketing campaign would need to move.
- David reported Payments headcount is stretched; one backfill is open for six weeks.
- Fatima said Mobile is on plan once the spec is stable.
- Grace offered two Platform engineers part time to share Payments review load.
- Budget for managed Kafka and the observability vendor was confirmed.

## Decisions

- Approve borrowing Platform engineers for Payments review for eight weeks.
- Launch in India first, then expand; do not widen scope before launch.
- Next checkpoint in six weeks, earlier if the spec slips.

## Action items

- David: close the Payments backfill and share the interview schedule.
- Priya: send a one-page risk summary to Rahul by Friday.
- Grace: name the Platform reviewers.
""",
    },
    {
        "key": "weekly-sync-w13",
        "type": "meeting_notes",
        "title": "Program sync - week 13",
        "author": "arjun",
        "days_ago": 55,
        "body": """# Program sync - week 13

## Attendees

Arjun Mehta, Priya Sharma, Vikram Rao, Karan Malhotra, Ananya Iyer, Rohan Gupta,
Meera Nair.

## Notes

- Karan has started reviewing Payments PRs; average review wait dropped from four days to two.
- Rate limiter shadow mode live at 1,000 RPS with no fail-open events.
- Fraud hooks interface merged; vendor integration in progress.
- Mobile wallet modules: iOS wallet integration at 70 percent, Android wallet integration at
  55 percent.
- Spec for refunds still in draft; Vikram cited incident load.

## Decisions

- Karan formally joins Payments reviews and will shadow refund work.
- Shadow mode continues two more weeks before any enforcement.
- Review wait time will be reported weekly until it holds under two days.

## Action items

- Vikram: finish the refund section of the spec.
- Ananya: prepare the 5k RPS load test plan.
- Meera: share the fraud shadow scoring dashboard.
- Rohan: report wallet module risks next sync.
""",
    },
    {
        "key": "sprint-review-2",
        "type": "meeting_notes",
        "title": "Sprint review - sprint 9",
        "author": "arjun",
        "days_ago": 35,
        "body": """# Sprint review - sprint 9

## Attendees

Arjun Mehta, Priya Sharma, Grace Lee, Fatima Al-Sayed, David Kim, Emily Chen,
Kwame Mensah, Li Wei.

## Notes

- Emily demoed the Apple Pay flow end to end against the staging API.
- Kwame demoed Google Pay; token refresh edge case still open.
- Li shipped the idempotency_keys table with monthly partitions and a sweeper job.
- Payments API v2 refunds endpoints are in code review.
- Observability: SLO burn-rate alerts live for the create endpoint.
- Velocity recovered to 41 points.

## Decisions

- Feature flags will control staged rollout of every customer-facing change.
- Code freeze for Payments API v2 schema in two sprints.

## Action items

- Kwame: fix the token refresh edge case.
- Li: add partition drop automation to the runbook.
- Arjun: add flag inventory to the launch checklist.
- Fatima: schedule a device lab session for low-end Android.
""",
    },
    {
        "key": "weekly-sync-w15",
        "type": "meeting_notes",
        "title": "Program sync - week 15",
        "author": "priya",
        "days_ago": 20,
        "body": """# Program sync - week 15

## Attendees

Priya Sharma, Arjun Mehta, Vikram Rao, Karan Malhotra, Ananya Iyer, Rohan Gupta,
Marcus Johnson, David Kim.

## Notes

- Payments API v2 create p99 is 262 ms, slightly over the 250 ms target.
- Karan and Vikram traced most of the extra latency to the fraud vendor call.
- Kafka dual-publish running; consumer lag at 2.1 s p99.
- Mobile reports the typed client regenerated cleanly after the last spec revision.
- Overall status remains amber; the refund endpoints are the largest remaining risk.

## Decisions

- Lower the vendor timeout from 30 ms to 25 ms and rely on the rules-only fallback.
- Hold a dedicated refund review session before the schema freeze.

## Action items

- Vikram: schedule the refund review with Karan and Meera.
- Marcus: add a lag alert at 5 s on the payment events consumers.
- Rohan: finish the retry and backoff tests for 429 responses.
- Priya: update the risk register and send the weekly summary.
""",
    },
    {
        "key": "launch-readiness",
        "type": "meeting_notes",
        "title": "Launch readiness checkpoint",
        "author": "priya",
        "days_ago": 5,
        "body": """# Launch readiness checkpoint

## Attendees

Priya Sharma, Arjun Mehta, Grace Lee, David Kim, Fatima Al-Sayed, Rahul Verma,
Vikram Rao, Rohan Gupta.

## Notes

- Readiness checklist: 31 of 48 items done; 9 in progress; 8 not started.
- Load test of the rate limiter at 5k RPS is scheduled; shadow data looks healthy.
- Wallet integrations pass internal QA; store review submission planned for next month.
- Data retention worker dry-run completed with no unexpected deletions.
- Rahul asked for a clear go or no-go date; Priya proposed a check four weeks out.
- Support training has not yet been scheduled.

## Decisions

- Launch in India first, with a staged rollout starting at 5 percent of traffic.
- Go or no-go review set four weeks before launch.

## Action items

- Fatima: submit the mobile builds for store review.
- David: confirm on-call coverage for the first two weeks.
- Arjun: schedule support training and the runbook walkthrough.
- Priya: circulate the final readiness checklist to all leads.
""",
    },
    {
        "key": "architecture-sync",
        "type": "transcript",
        "title": "Architecture sync — Payments API v2 and launch dependencies",
        "author": "priya",
        "days_ago": 2,
        "body": _ARCH_TRANSCRIPT,
    },
]

DECISIONS: list[DecisionSpec] = [
    {
        "key": "kafka-over-sqs",
        "title": "Use Kafka over SQS for payment events",
        "context": (
            "Fraud analyzers, the ledger and notifications need ordered, replayable payment "
            "events at roughly 3,000 events/s."
        ),
        "options": [
            {
                "name": "Kafka",
                "pros": "Per-key ordering, log replay, high throughput headroom.",
                "cons": "Higher cost and more operational work, even when managed.",
            },
            {
                "name": "SQS FIFO",
                "pros": "Near-zero operations and low cost.",
                "cons": "No native replay, per-queue throughput cap, group-level ordering only.",
            },
        ],
        "chosen_option": "Kafka",
        "rationale": (
            "Replay and per-payment ordering matter more to fraud and the ledger than the extra "
            "cost, and a managed service bounds the operational burden."
        ),
        "participants": ["vikram", "ananya", "marcus", "priya", "david"],
        "days_ago": 90,
        "source_doc": "event-streaming",
    },
    {
        "key": "rest-over-grpc",
        "title": "REST over gRPC for the public Payments API",
        "context": "Partners and mobile clients need a public API; internal services use gRPC.",
        "options": [
            {
                "name": "REST/JSON",
                "pros": "Universal tooling, easy debugging, simple partner onboarding.",
                "cons": "Larger payloads and no streaming.",
            },
            {
                "name": "gRPC",
                "pros": "Compact, typed, streaming support.",
                "cons": "Poor browser and partner support; harder to debug.",
            },
        ],
        "chosen_option": "REST/JSON",
        "rationale": "Partner adoption outweighs payload size; gRPC stays for internal calls.",
        "participants": ["vikram", "karan", "aisha", "arjun"],
        "days_ago": 155,
        "source_doc": "payments-api-v2",
    },
    {
        "key": "cursor-pagination",
        "title": "Cursor-based pagination for list endpoints",
        "context": "Offset pagination degrades past 100k rows and shifts when rows are inserted.",
        "options": [
            {
                "name": "Cursor-based",
                "pros": "Stable results and constant cost per page.",
                "cons": "No random page access; cursor format must be maintained.",
            },
            {
                "name": "Offset/limit",
                "pros": "Simple and familiar.",
                "cons": "Slow at depth and inconsistent under concurrent writes.",
            },
        ],
        "chosen_option": "Cursor-based",
        "rationale": "Mobile infinite scroll fits cursors, and Postgres keyset queries stay cheap.",
        "participants": ["karan", "vikram", "liwei", "rohan", "priya"],
        "days_ago": 3,
        "source_doc": "payments-api-v2",
    },
    {
        "key": "postgres-idempotency",
        "title": "Store idempotency keys in Postgres, not Redis",
        "context": "Retried writes must never double charge, even through a cache failover.",
        "options": [
            {
                "name": "Postgres",
                "pros": "Atomic with the payment write; durable.",
                "cons": "Extra write load and table churn.",
            },
            {
                "name": "Redis",
                "pros": "Very fast and native TTL.",
                "cons": "Data loss on failover could allow duplicate charges.",
            },
        ],
        "chosen_option": "Postgres",
        "rationale": "Atomicity with the payment transaction removes the duplicate-charge risk.",
        "participants": ["karan", "liwei", "ananya", "vikram", "david"],
        "days_ago": 100,
        "source_doc": "idempotency-keys",
    },
    {
        "key": "idempotency-ttl-24h",
        "title": "Idempotency keys expire after 24 hours",
        "context": "We need a retention window long enough for client retries but bounded.",
        "options": [
            {
                "name": "24 hours",
                "pros": "Covers every retry window seen in mobile logs; small table.",
                "cons": "Retries after a day create a new payment.",
            },
            {
                "name": "7 days",
                "pros": "Very safe for delayed retries.",
                "cons": "Seven times the storage and vacuum load.",
            },
            {
                "name": "30 days",
                "pros": "Matches some competitor APIs.",
                "cons": "Large table and unclear benefit.",
            },
        ],
        "chosen_option": "24 hours",
        "rationale": "Mobile logs show no retries beyond 6 hours; 24 hours leaves wide margin.",
        "participants": ["karan", "liwei", "vikram", "priya"],
        "days_ago": 3,
        "source_doc": "idempotency-keys",
    },
    {
        "key": "token-bucket-limiter",
        "title": "Token bucket algorithm for the rate limiter",
        "context": "The gateway needs burst tolerance with predictable sustained rates.",
        "options": [
            {
                "name": "Token bucket",
                "pros": "Allows bursts, simple, one atomic operation.",
                "cons": "Bursts can briefly exceed the average rate.",
            },
            {
                "name": "Sliding window log",
                "pros": "Precise counting.",
                "cons": "Memory heavy at 5k RPS.",
            },
            {
                "name": "Fixed window",
                "pros": "Simplest implementation.",
                "cons": "Boundary spikes allow double the limit.",
            },
        ],
        "chosen_option": "Token bucket",
        "rationale": "Bursty checkout traffic is normal; token bucket fits and is cheap in Redis.",
        "participants": ["ananya", "sofia", "marcus", "grace"],
        "days_ago": 150,
        "source_doc": "rate-limiter",
    },
    {
        "key": "limiter-fail-open",
        "title": "Rate limiter fails open when Redis is unavailable",
        "context": "The limiter sits on the hot path; its failure must not block payments.",
        "options": [
            {
                "name": "Fail open",
                "pros": "Payments keep flowing during a Redis outage.",
                "cons": "Temporarily unthrottled traffic.",
            },
            {
                "name": "Fail closed",
                "pros": "Strict protection always.",
                "cons": "A cache outage becomes a payments outage.",
            },
        ],
        "chosen_option": "Fail open",
        "rationale": "Blocking real payments is worse than a short unthrottled window.",
        "participants": ["ananya", "marcus", "grace", "priya"],
        "days_ago": 110,
        "source_doc": "rate-limiter",
    },
    {
        "key": "react-native-checkout",
        "title": "Build the mobile checkout UI in React Native",
        "context": "iOS and Android checkout flows have diverged and drop-off differs from web.",
        "options": [
            {
                "name": "React Native",
                "pros": "One codebase, faster iteration, shared logic.",
                "cons": "Bridge overhead on low-end devices.",
            },
            {
                "name": "Two native apps",
                "pros": "Best performance and platform feel.",
                "cons": "Double the work and risk of diverging again.",
            },
            {
                "name": "Flutter",
                "pros": "Strong rendering performance.",
                "cons": "New stack for the team and a poor fit with existing shells.",
            },
        ],
        "chosen_option": "React Native",
        "rationale": "A shared module halves effort; wallet sheets stay native to cover the gap.",
        "participants": ["rohan", "emily", "kwame", "fatima", "arjun"],
        "days_ago": 125,
        "source_doc": "mobile-checkout",
    },
    {
        "key": "native-wallet-modules",
        "title": "Native modules for Apple Pay and Google Pay",
        "context": "Wallet sheets require platform APIs and strict timing.",
        "options": [
            {
                "name": "Native modules",
                "pros": "Full platform support and fast sheet presentation.",
                "cons": "Separate implementation per platform.",
            },
            {
                "name": "Third-party RN wallet library",
                "pros": "Less code to write.",
                "cons": "Lags OS releases and is hard to patch.",
            },
        ],
        "chosen_option": "Native modules",
        "rationale": "Timing and SDK currency matter; the team has strong native expertise.",
        "participants": ["emily", "kwame", "rohan", "lucas"],
        "days_ago": 118,
        "source_doc": "mobile-checkout",
    },
    {
        "key": "feature-flags-rollout",
        "title": "Use feature flags for staged rollout",
        "context": "Public launch carries risk; we need instant rollback without deploys.",
        "options": [
            {
                "name": "Feature flags with percentage ramps",
                "pros": "Gradual exposure and instant kill switch.",
                "cons": "Flag debt and more test combinations.",
            },
            {
                "name": "Big-bang release",
                "pros": "Simplest to plan.",
                "cons": "Any defect hits all users at once.",
            },
        ],
        "chosen_option": "Feature flags with percentage ramps",
        "rationale": "Staged exposure limits blast radius; flag cleanup is part of the checklist.",
        "participants": ["priya", "arjun", "grace", "fatima", "david"],
        "days_ago": 35,
        "source_doc": None,
    },
    {
        "key": "ledger-retention-7y",
        "title": "Retain ledger records for seven years",
        "context": "Regulators require multi-year retention of financial records.",
        "options": [
            {
                "name": "7 years",
                "pros": "Meets the longest applicable requirement.",
                "cons": "Long-term storage cost.",
            },
            {
                "name": "5 years",
                "pros": "Lower cost.",
                "cons": "Falls short of some jurisdictions.",
            },
        ],
        "chosen_option": "7 years",
        "rationale": "Compliance outranks storage savings; cold storage keeps the cost modest.",
        "participants": ["liwei", "grace", "priya", "rahul"],
        "days_ago": 110,
        "source_doc": "data-retention",
    },
    {
        "key": "opentelemetry-standard",
        "title": "Standardize on OpenTelemetry",
        "context": "Logs, metrics and traces use different tools and identifiers.",
        "options": [
            {
                "name": "OpenTelemetry",
                "pros": "Vendor-neutral, shared context propagation, broad library support.",
                "cons": "Migration effort for older services.",
            },
            {
                "name": "Vendor agent only",
                "pros": "Quick to turn on.",
                "cons": "Lock-in and inconsistent propagation.",
            },
        ],
        "chosen_option": "OpenTelemetry",
        "rationale": "A neutral standard avoids lock-in and gives one trace id everywhere.",
        "participants": ["marcus", "ananya", "sofia", "grace"],
        "days_ago": 120,
        "source_doc": "observability",
    },
    {
        "key": "fraud-sync-with-fallback",
        "title": "Synchronous fraud check with rules-only fallback",
        "context": "Risk must be assessed before authorization within a 40 ms p99 budget.",
        "options": [
            {
                "name": "Sync check with timeout fallback",
                "pros": "Blocks bad payments before money moves.",
                "cons": "Adds latency and a vendor dependency.",
            },
            {
                "name": "Post-capture batch only",
                "pros": "Zero latency impact.",
                "cons": "Fraud is found after funds move.",
            },
        ],
        "chosen_option": "Sync check with timeout fallback",
        "rationale": "Pre-authorization blocking reduces chargebacks; fallback protects latency.",
        "participants": ["meera", "vikram", "david", "priya"],
        "days_ago": 110,
        "source_doc": "fraud-hooks",
    },
    {
        "key": "india-first-launch",
        "title": "Launch Checkout 2.0 in India first",
        "context": "A public launch in all markets at once multiplies compliance and support load.",
        "options": [
            {
                "name": "India first",
                "pros": "Largest volume, UPI readiness, a contained rollout.",
                "cons": "Other markets wait longer.",
            },
            {
                "name": "All markets at once",
                "pros": "Single marketing moment.",
                "cons": "Much higher risk and support burden.",
            },
        ],
        "chosen_option": "India first",
        "rationale": "A single market limits risk while covering most of the volume.",
        "participants": ["rahul", "priya", "grace", "david", "fatima"],
        "days_ago": 75,
        "source_doc": None,
    },
    {
        "key": "refund-review-reviewers",
        "title": "Share Payments PR review across Platform and Payments",
        "context": "Review latency on Payments PRs reached four days with one overloaded lead.",
        "options": [
            {
                "name": "Shared reviewer rotation",
                "pros": "Cuts wait time and spreads knowledge.",
                "cons": "Reviewers need payments context first.",
            },
            {
                "name": "Hire and wait",
                "pros": "Permanent solution.",
                "cons": "Too slow for the launch timeline.",
            },
        ],
        "chosen_option": "Shared reviewer rotation",
        "rationale": "It relieves the bottleneck now and lets Karan grow into payments.",
        "participants": ["david", "grace", "vikram", "karan", "priya"],
        "days_ago": 75,
        "source_doc": None,
    },
]

FEEDBACK_THEMES: dict[str, FeedbackTheme] = {
    "bulk_export": {
        "label": "Bulk export",
        "summary": "Customers want to export large sets of transactions and reports in bulk.",
        "count": 40,
        "sentiment_mean": -0.6,
        "sentiment_sd": 0.2,
        "growth": "rising",
        "segments": ["enterprise", "smb", "partner"],
        "sentences": [
            "We need to export all of last quarter's transactions to CSV in one go.",
            "The dashboard only lets me download 500 rows at a time, which is unusable.",
            "Our finance team spends a day each month stitching together exported pages.",
            "Please add a bulk export of settlements for reconciliation.",
            "Export times out whenever the date range is longer than two weeks.",
            "Can we schedule a nightly export of payments to our S3 bucket?",
            "Auditors keep asking for full transaction dumps and we cannot produce them.",
            "A downloadable report of all refunds would save us hours of manual work.",
            "The export button silently fails for large merchants with many transactions.",
            "We need an API to pull every payment for a period, not paginated clicking.",
            "Enterprise customer asked for bulk data export as a renewal condition.",
            "Export to Excel is limited to the current page, which makes no sense.",
            "Reconciliation against our ERP needs a full settlement file each day.",
            "I would pay extra for scheduled bulk reports delivered by email.",
            "Support tickets about export limits are our most common complaint this month.",
            "Competitor offers one-click full history export; we do not.",
            "Large CSV downloads hang at 90 percent and then give an empty file.",
            "We want to export dispute and chargeback history in a single file.",
            "Our tax accountant needs yearly totals by payment method in bulk.",
            "Partner platform needs a bulk transaction feed to sync with their ledger.",
            "Please let us export payouts together with fees in one statement.",
            "Too many manual steps just to get a complete list of orders out of the system.",
            "Survey comment: exports are the weakest part of the merchant dashboard.",
            "Sales note: prospect with 2M monthly payments will not sign without bulk export.",
            "Could exports include custom metadata fields we attach to each payment?",
        ],
    },
    "saved_cards": {
        "label": "Saved cards",
        "summary": "Feedback on storing, managing and reusing saved payment cards.",
        "count": 28,
        "sentiment_mean": -0.1,
        "sentiment_sd": 0.35,
        "growth": "flat",
        "segments": ["consumer", "smb"],
        "sentences": [
            "I want my card saved so I do not retype it every time I check out.",
            "Saved cards disappeared after I updated the app.",
            "It is great that I can pick my saved card with one tap.",
            "How do I delete a card I no longer use?",
            "Please let me choose a default card for subscriptions.",
            "My expired card is still showing as the preferred option.",
            "I would feel safer if saved cards asked for a CVV on each purchase.",
            "Can I save more than three cards? I use different ones for work.",
            "The saved card list shows only the last four digits, I cannot tell cards apart.",
            "Adding a nickname to a card would help me recognize it.",
            "Card details were not updated even after my bank reissued the number.",
            "I tried to save a card and the form just spun forever.",
            "Customers keep asking whether their stored cards are secure.",
            "Returning shoppers love the one-click saved card flow.",
            "Please add automatic card updater so my saved card does not fail on renewal.",
            "Saved card selection resets to the wrong card after each purchase.",
            "I can't edit the billing address on a saved card without removing it.",
            "Survey comment: storing cards is convenient but the management screen is confusing.",
            "Merchant feedback: shoppers abandon when they have to re-enter card details.",
            "Why does the app ask me to re-add my card every few weeks?",
            "Let me see which saved card was used for each past order.",
            "Support ticket: customer charged on a card they thought they had removed.",
            "I prefer tokenized cards so the merchant never sees my full number.",
            "Saved cards should sync between the website and the mobile app.",
            "The delete card confirmation is missing, I removed the wrong one.",
            "Could we mark one saved card as business and another as personal?",
        ],
    },
    "upi_autopay": {
        "label": "UPI AutoPay",
        "summary": "Demand for recurring UPI mandates and autopay for subscriptions.",
        "count": 26,
        "sentiment_mean": -0.2,
        "sentiment_sd": 0.3,
        "growth": "rising",
        "segments": ["consumer", "smb", "enterprise"],
        "sentences": [
            "We need UPI AutoPay so subscribers are billed without a manual approval.",
            "Most of our customers in India pay by UPI, recurring cards are not enough.",
            "Does the new checkout support UPI mandates for monthly plans?",
            "Customers churn when they must approve every renewal payment by hand.",
            "Please add e-mandate support for utility and insurance bill payments.",
            "UPI autopay is the number one request from our subscription merchants.",
            "My monthly gym payment fails because I have to approve it each time.",
            "Can I set a maximum amount for a recurring UPI mandate?",
            "Sales note: SaaS prospect in Mumbai needs recurring UPI before they can migrate.",
            "We lose renewals because UPI collect requests expire before users see them.",
            "How soon will standing instructions via UPI be available?",
            "Enterprise client wants autopay mandates with pre-debit notifications.",
            "I would like to pause or cancel my UPI mandate from inside the app.",
            "Survey comment: add auto debit through UPI, cards are too much hassle for rent.",
            "Recurring billing on UPI would double our successful renewal rate.",
            "The mandate registration flow should show the amount cap clearly.",
            "Our telecom clients ask for UPI-based recurring top-ups.",
            "Please support mandate modification when the plan price changes.",
            "Customers do not trust giving a card for subscriptions but accept a UPI mandate.",
            "When can I use UPI for my SIP investments on autopay?",
            "Interview quote: if you offered UPI AutoPay we would move all our billing to you.",
            "Pre-debit notification wording needs to follow the regulator's rules.",
            "Failed autopay debits should retry automatically before the plan lapses.",
            "We need webhook events for mandate created, paused and revoked.",
            "A partner marketplace wants UPI recurring for their seller subscriptions.",
        ],
    },
    "refund_status": {
        "label": "Refund status",
        "summary": "Confusion and frustration about tracking where a refund is.",
        "count": 24,
        "sentiment_mean": -0.4,
        "sentiment_sd": 0.25,
        "growth": "flat",
        "segments": ["consumer", "smb"],
        "sentences": [
            "I requested a refund ten days ago and I still cannot see where it is.",
            "The app says refund initiated but gives no date for when I will get the money.",
            "There is no way to check the status of a refund in the dashboard.",
            "Customers email us daily asking if their refund has been processed.",
            "My refund shows as pending for two weeks with no explanation.",
            "Please add refund tracking with clear stages like requested and processed.",
            "I got a refund notification but nothing arrived in my bank account.",
            "Support told me to wait five to seven days but could not see my refund.",
            "Partial refund was issued and I cannot tell how much is still owed.",
            "Merchant feedback: our team has no visibility into refund progress for buyers.",
            "A refund reference number would let me follow up with my bank.",
            "Refund to original payment method failed and nobody told me.",
            "Why does the same refund show different statuses in email and in the app?",
            "We need webhooks for refund status changes to update our order system.",
            "The refund timeline is not displayed anywhere on the receipt.",
            "I was told the refund was completed, but the bank says nothing was received.",
            "Support ticket: refund stuck in processing for more than twelve days.",
            "Survey comment: refunds are slow and I never know what is happening.",
            "Customers want an estimated refund arrival date, not a vague message.",
            "Can partial and multiple refunds on one order be shown together?",
            "No notification when my refund finally completes, I had to keep checking.",
            "Our accountant cannot match refund payouts to the original orders.",
            "I filed a refund request twice because the first showed no confirmation.",
            "Refund status page should explain why a refund is delayed.",
        ],
    },
    "multi_currency": {
        "label": "Multi-currency",
        "summary": "Requests to price and settle in multiple currencies.",
        "count": 18,
        "sentiment_mean": -0.3,
        "sentiment_sd": 0.3,
        "growth": "flat",
        "segments": ["enterprise", "smb", "partner"],
        "sentences": [
            "We need to charge customers in euros and settle in rupees.",
            "Can checkout show prices in the shopper's local currency automatically?",
            "Foreign buyers drop off because they see unexpected conversion fees.",
            "Please support settlement in USD for our exporters.",
            "Currency conversion rates are not shown before payment confirmation.",
            "Sales note: UK retailer needs GBP pricing before expanding with us.",
            "We want one account holding balances in several currencies.",
            "How are exchange rates determined and can we lock a rate for a day?",
            "Reports mix currencies in a single column, which breaks our reconciliation.",
            "Customers abroad ask why their card is charged in a different currency.",
            "Multi-currency invoices would help our international B2B clients.",
            "Refunds in a foreign currency come back at a worse rate than the original charge.",
            "Survey comment: add support for AED and SGD, our travel clients need them.",
            "We pay suppliers in dollars and would like to avoid converting twice.",
            "Partner platform asks for per-currency payout schedules.",
            "Display the total in both the local and the presentment currency.",
            "Enterprise prospect requires 15 currencies at launch of the new checkout.",
            "Please add dynamic currency conversion that the shopper can accept or decline.",
            "Our Dubai clients invoice in AED but our payouts arrive in INR with hidden spreads.",
            "Can we hold a USD balance instead of converting every payout immediately?",
            "International shoppers want to pay in their home currency, not guess the rate.",
            "Currency rounding differs between the receipt and the settlement report.",
            "Interview quote: no multi-currency means we lose every cross-border deal to rivals.",
        ],
    },
    "dark_mode": {
        "label": "Dark mode",
        "summary": "Requests and comments about dark mode in the app and dashboard.",
        "count": 14,
        "sentiment_mean": 0.1,
        "sentiment_sd": 0.3,
        "growth": "flat",
        "segments": ["consumer", "smb"],
        "sentences": [
            "Please add a dark mode, the white screen is harsh at night.",
            "Love the new look, but it would be even nicer in dark theme.",
            "Does the dashboard have a dark theme? My eyes hurt in the evening.",
            "The checkout screen blinds me when I pay in bed.",
            "Would be great if the app followed my phone's system dark setting.",
            "Dark mode would match the rest of the apps I use on my device.",
            "Survey comment: dark theme would make the dashboard nicer for late shifts.",
            "Our night support team asks for a dark interface on the admin console.",
            "The receipt email is bright white, a dark version would be a nice touch.",
            "Any plans for a dark appearance option in settings?",
            "I like the clean design, but a dark option would be a bonus.",
            "Charts are hard to read on the light background in low light.",
            "Please respect OLED battery saving with a true black theme.",
            "Not urgent, but a dark theme in the merchant app would be appreciated.",
            "A night mode option would be lovely for the evening bill payments I do.",
            "The bright payment confirmation screen is jarring in a dark room.",
            "Will you add a dark skin to the web dashboard like other tools I use?",
            "Dark theme please, I work night shifts and the app is too glaring.",
            "My phone is always in dark mode, so your white screens stand out badly.",
            "Product feedback: a dark appearance setting would make the app feel more modern.",
            "Nice app, though the light-only design is tiring on the eyes after midnight.",
            "Could the dashboard remember a dark preference across sessions?",
            "Dark mode for the invoice preview would be handy when I review late at night.",
        ],
    },
}
