// Records the TwinPM product walkthrough video, paced to narration clip durations.
//
// node scripts/record-walkthrough.mjs <durations.json> <outdir> [--dry]
// Writes <outdir>/walkthrough.webm and <outdir>/timeline.json (scene start offsets, seconds).
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const [durationsPath, outDir, flag] = process.argv.slice(2);
const DRY = flag === "--dry";
const BASE = process.env.BASE_URL ?? "http://localhost:3100";
const PASSWORD = process.env.SEED_DEMO_PASSWORD ?? "TwinPM-demo-2026!";
const durations = JSON.parse(fs.readFileSync(durationsPath, "utf8"));
const narration = JSON.parse(
  fs.readFileSync(path.join(path.dirname(new URL(import.meta.url).pathname), "../../../docs/video/narration.json"), "utf8"),
);
const titles = Object.fromEntries(narration.map((s) => [s.id, s.title]));
const W = 1440;
const H = 900;

// Overlay helpers injected into every page: a visible cursor, chapter lower-thirds, title cards.
const OVERLAY = `
(() => {
  const ready = () => {
    if (document.getElementById("__cursor")) return;
    const c = document.createElement("div");
    c.id = "__cursor";
    c.style.cssText = "position:fixed;z-index:2147483647;width:22px;height:22px;border-radius:50%;" +
      "background:rgba(15,118,110,.35);border:2px solid #0f766e;pointer-events:none;transform:translate(-50%,-50%);" +
      "transition:transform .12s ease;left:-50px;top:-50px;box-shadow:0 0 0 4px rgba(255,255,255,.6)";
    document.body.appendChild(c);
    window.addEventListener("mousemove", (e) => { c.style.left = e.clientX + "px"; c.style.top = e.clientY + "px"; }, true);
    window.addEventListener("mousedown", () => { c.style.transform = "translate(-50%,-50%) scale(.7)"; }, true);
    window.addEventListener("mouseup", () => { c.style.transform = "translate(-50%,-50%) scale(1)"; }, true);
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", ready); else ready();
  window.__chapter = (n, title) => {
    let el = document.getElementById("__chapter");
    if (!el) {
      el = document.createElement("div");
      el.id = "__chapter";
      el.style.cssText = "position:fixed;left:24px;bottom:24px;z-index:2147483646;pointer-events:none;" +
        "background:rgba(20,33,61,.92);color:#fff;font:600 15px Inter,system-ui,sans-serif;padding:10px 16px;" +
        "border-radius:12px;box-shadow:0 8px 24px rgba(0,0,0,.25);letter-spacing:.2px;transition:opacity .4s";
      document.body.appendChild(el);
    }
    el.innerHTML = '<span style="color:#5eead4;margin-right:10px">' + n + '</span>' + title;
    el.style.opacity = "1";
  };
  window.__card = (title, sub) => {
    let el = document.getElementById("__card");
    if (!title) { if (el) el.remove(); return; }
    if (!el) { el = document.createElement("div"); el.id = "__card"; document.body.appendChild(el); }
    el.style.cssText = "position:fixed;inset:0;z-index:2147483645;display:flex;flex-direction:column;align-items:center;" +
      "justify-content:center;gap:18px;background:radial-gradient(circle at 30% 20%,#1f2f55,#14213d 60%,#0c1529);color:#fff;" +
      "font-family:Inter,system-ui,sans-serif;text-align:center;padding:80px";
    el.innerHTML = '<div style="display:flex;align-items:center;gap:14px"><div style="width:56px;height:56px;border-radius:14px;' +
      'background:#0f766e;display:grid;place-items:center;font:700 30px Inter">T</div><div style="font:700 52px Inter">' + title +
      '</div></div><div style="max-width:900px;font:400 26px/1.45 Inter;color:#d6dcea">' + sub + '</div>';
  };
})();
`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

async function main() {
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: W, height: H },
    deviceScaleFactor: 1,
    recordVideo: DRY ? undefined : { dir: outDir, size: { width: W, height: H } },
  });
  await context.addInitScript(OVERLAY);
  const page = await context.newPage();
  const t0 = Date.now();
  const timeline = [];
  const failures = [];

  const pace = async (ms) => sleep(DRY ? Math.min(ms, 400) : ms);
  async function moveTo(locator) {
    await locator.scrollIntoViewIfNeeded({ timeout: 8000 }).catch(() => {});
    const box = await locator.boundingBox({ timeout: 8000 });
    if (!box) throw new Error("no box");
    await page.mouse.move(box.x + box.width / 2, box.y + Math.min(box.height / 2, 18), { steps: 25 });
    await pace(350);
  }
  async function click(locator) {
    await moveTo(locator);
    await locator.click({ timeout: 10000 });
    await pace(500);
  }
  async function hover(locator, ms = 1200) {
    await moveTo(locator);
    await pace(ms);
  }
  async function typeSlow(locator, text) {
    await click(locator);
    await locator.pressSequentially(text, { delay: DRY ? 5 : 45 });
  }
  async function scrollBy(dy, steps = 6) {
    for (let i = 0; i < steps; i++) {
      await page.mouse.wheel(0, dy / steps);
      await pace(120);
    }
    await pace(500);
  }
  async function go(p) {
    await page.goto(BASE + p, { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle", { timeout: 20000 }).catch(() => {});
    await pace(800);
  }
  async function step(name, fn) {
    try {
      await fn();
    } catch (e) {
      failures.push(`${name}: ${String(e.message ?? e).split("\n")[0]}`);
      log("STEP FAILED", name, String(e.message ?? e).split("\n")[0]);
    }
  }
  const btn = (re) => page.getByRole("button", { name: re });

  async function scene(id, n, fn) {
    const start = (Date.now() - t0) / 1000;
    timeline.push({ id, start });
    log("scene", id, start.toFixed(1));
    if (id !== "s00_intro" && id !== "s20_outro") {
      await page.evaluate(([num, t]) => window.__chapter?.(num, t), [n, titles[id]]).catch(() => {});
    }
    const deadline = Date.now() + (durations[id] ?? 20) * 1000 + 700;
    await fn();
    const left = deadline - Date.now();
    if (left > 0 && !DRY) await sleep(left);
    if (left < -1500) log(`  scene ${id} overran by ${(-left / 1000).toFixed(1)}s`);
  }

  // ------------------------------------------------------------------ scenes
  await go("/login");
  await scene("s00_intro", "", async () => {
    await page.evaluate(() =>
      window.__card(
        "TwinPM",
        "An AI digital twin for technical program and product managers.<br/><br/>It doesn't just answer questions about your program.<br/>It runs it the way you would, and shows its reasoning every time.",
      ),
    );
  });

  await scene("s01_login", "1", async () => {
    await page.evaluate(() => window.__card(null));
    await page.evaluate(() => window.__chapter("1", "Sign in"));
    await step("pick priya", () => click(btn(/Priya Sharma/)));
    await step("password", () => typeSlow(page.getByLabel("Password"), PASSWORD));
    await step("sign in", () => click(btn(/^Sign in$/)));
    await page.waitForURL(/command-center/, { timeout: 30000 });
    await page.waitForLoadState("networkidle", { timeout: 20000 }).catch(() => {});
  });

  await scene("s02_health", "2", async () => {
    await step("gauge", () => hover(page.getByTestId("health-card"), 2500));
    for (const chip of ["Schedule", "Quality", "Dependencies", "Team"]) {
      await step(`chip ${chip}`, () => hover(page.getByTestId("health-card").getByRole("button", { name: new RegExp(chip) }), 2200));
    }
    await step("anomaly strip", () => hover(page.getByLabel("Metric anomalies"), 2500));
  });

  const first = () => page.getByTestId("briefing-item").first();
  await scene("s03_briefing", "3", async () => {
    await step("briefing", () => hover(first(), 4000));
    await step("why", () => click(first().getByRole("button", { name: /Why\?/ })));
    await pace(3000);
    await step("drivers", () => hover(first().getByRole("list", { name: "Contributing factors" }), 6000));
    await step("cite", () => click(first().getByRole("button", { name: /Open source/ }).first()));
    await pace(6000);
    await step("close panel", () => page.keyboard.press("Escape"));
    await step("why off", () => click(first().getByRole("button", { name: /Why\?/ })));
  });

  await scene("s04_forecast", "4", async () => {
    await step("forecast", () => hover(page.getByTestId("forecast-card"), 6000));
    await step("dist", () => click(btn(/Show distribution/)));
    await pace(4000);
    await step("hist", () => hover(page.getByRole("img", { name: /distribution/i }), 6000));
  });

  await scene("s05_options", "5", async () => {
    await step("scroll up", () => scrollBy(-1200));
    await step("see options", () => click(first().getByRole("button", { name: "See options" })));
    await page.getByTestId("options").waitFor({ timeout: 30000 }).catch(() => {});
    await pace(2000);
    for (const n of ["Rebalance", "Descope", "Move the date"]) {
      await step(`opt ${n}`, () => hover(page.getByTestId("options").getByText(n, { exact: true }).first(), 3500));
    }
    await pace(4000);
    await step("close", () => page.keyboard.press("Escape"));
  });

  await scene("s06_radar", "6", async () => {
    await go("/novapay/risk");
    await page.locator(".react-flow").first().waitFor({ timeout: 30000 }).catch(() => {});
    await pace(5000);
    await step("graph hover", () => hover(page.locator(".react-flow__node").filter({ hasText: "Payments API v2" }).first(), 5000));
    await step("slip days", async () => {
      const days = page.getByLabel("Slip (days)");
      await click(days);
      await days.fill("9");
    });
    await step("simulate", () => click(btn(/^Simulate/).first()));
    await pace(6000);
    await step("graph again", () => hover(page.locator(".react-flow").first(), 6000));
  });

  await scene("s07_risktables", "7", async () => {
    await step("scroll table", () => scrollBy(900, 8));
    await pace(5000);
    await step("scroll register", () => scrollBy(900, 8));
    await pace(5000);
    await step("scroll top", () => scrollBy(-2400, 8));
    await step("model card", () => click(btn(/Model card/)));
    await pace(9000);
    await step("close mc", () => page.keyboard.press("Escape"));
  });

  await scene("s08_ask", "8", async () => {
    await go("/novapay/command-center");
    await step("open twin", () => click(page.getByRole("banner").getByRole("button", { name: /Ask the Twin/ })));
    await pace(1500);
    await step("ask", () => typeSlow(page.locator("#twin-input"), "What should I do?"));
    await page.keyboard.press("Enter");
    await pace(4000);
    await step("trace", () => hover(page.getByTestId("agent-trace").first(), 8000));
    await page.getByTestId("twin-answer").last().getByText(/approval/).first().waitFor({ timeout: 60000 }).catch(() => {});
    await step("answer", () => hover(page.getByTestId("twin-answer").last().locator("p").nth(1), 6000));
  });

  await scene("s09_policy", "9", async () => {
    await step("scroll drawer", async () => {
      const ans = page.getByTestId("twin-answer").last();
      await ans.getByLabel("Actions waiting for approval").scrollIntoViewIfNeeded({ timeout: 10000 });
      await hover(ans.getByLabel("Actions waiting for approval"), 6000);
    });
    await step("approval card", () => hover(page.getByTestId("suggestion-card").first(), 8000));
  });

  await scene("s10_delegation", "10", async () => {
    await step("close twin", () => page.keyboard.press("Escape"));
    await step("close twin btn", async () => {
      const closeBtn = page.getByRole("button", { name: "Close panel" });
      if (await closeBtn.isVisible().catch(() => false)) await click(closeBtn);
    });
    await step("see options", () => click(first().getByRole("button", { name: "See options" })));
    await page.getByTestId("options").waitFor({ timeout: 30000 }).catch(() => {});
    await pace(1500);
    await step("choose rebalance", () => click(btn(/Choose rebalance/)));
    await page.waitForURL(/delegation/, { timeout: 30000 }).catch(() => {});
    await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
    await pace(4000);
    await step("karan", () => hover(page.getByText(/Karan Malhotra/).first(), 7000));
    await step("li wei", () => hover(page.getByText("Li Wei").first(), 4000));
    await step("approve all", () => click(btn(/Approve all/).first()));
    await pace(4000);
  });

  await scene("s11_workload", "11", async () => {
    await step("scroll heatmap", () => scrollBy(1400, 10));
    await pace(6000);
    await step("scroll more", () => scrollBy(1200, 10));
    await pace(5000);
    await step("stalled", () => click(btn(/Find stalled/).first()));
    await pace(5000);
    await step("scroll nudges", () => scrollBy(900, 8));
  });

  await scene("s12_audit", "12", async () => {
    await go("/novapay/command-center");
    await step("activity", async () => {
      const feed = page.getByTestId("activity");
      await feed.scrollIntoViewIfNeeded();
      await hover(feed, 4000);
      await click(feed.getByRole("button").first());
    });
    await pace(9000);
    await step("close audit", () => page.keyboard.press("Escape"));
  });

  await scene("s13_roadmap", "13", async () => {
    await go("/novapay/roadmap");
    await pace(3000);
    await step("card", () => hover(page.getByRole("heading", { name: /Payments API v2/ }).first(), 5000));
    await step("to simulator", () => hover(page.getByText("What-if simulator").first(), 2000));
    await step("change type", async () => {
      const sel = page.locator("select[id$='-type']").first();
      await moveTo(sel);
      const opts = await sel.locator("option").allTextContents();
      const cap = opts.find((o) => /capacity/i.test(o));
      if (cap) await sel.selectOption({ label: cap });
    });
    await pace(1200);
    await step("team", async () => {
      const sel = page.locator("select[id$='-team']").first();
      await moveTo(sel);
      await sel.selectOption({ label: "Payments (5)" });
    });
    await step("slider", async () => {
      const thumb = page.getByRole("slider").first();
      await click(thumb);
      for (let i = 0; i < 6; i++) await page.keyboard.press("ArrowRight");
    });
    await step("add change", () => click(btn(/Add change/)));
    await step("run sim", () => click(btn(/^Run simulation$/)));
    await pace(5000);
    await step("result", () => hover(page.getByText(/days? (earlier|later)|is unchanged/).first().or(page.getByText("Delta").first()).first(), 8000));
  });

  await scene("s14_strategy", "14", async () => {
    await go("/novapay/strategy");
    await pace(4000);
    await step("treemap", () => hover(page.getByText(/Export \/ Bulk/).first(), 5000));
    await step("table", async () => {
      await scrollBy(700, 8);
      await pace(5000);
      await scrollBy(-700, 8);
    });
    await step("quotes", () => hover(page.getByText("Representative quotes").first(), 6000));
  });

  await scene("s15_prd", "15", async () => {
    await step("draft prd", () => click(btn(/Draft (a )?PRD/).first()));
    await page.getByLabel(/PRD draft/).waitFor({ timeout: 30000 }).catch(() => {});
    await pace(9000);
    await step("draft hover", () => hover(page.getByLabel(/PRD draft/), 5000));
    await step("devils", () => click(btn(/Challenge this draft/)));
    await pace(8000);
  });

  await scene("s16_comms", "16", async () => {
    await go("/novapay/comms");
    await step("generate", () => click(btn(/^Generate$/)));
    const draft = page.locator("#report-draft");
    await draft.waitFor({ timeout: 30000 }).catch(() => {});
    await page.waitForFunction(() => document.querySelector("#report-draft")?.getAttribute("aria-busy") === "false", null, { timeout: 60000 }).catch(() => {});
    await pace(5000);
    await step("edit", async () => {
      await click(draft);
      await draft.press("ControlOrMeta+End");
      await draft.pressSequentially("\nAsk: please confirm the rebalance by Friday.", { delay: DRY ? 5 : 40 });
    });
    await pace(1500);
    await step("approve", () => click(btn(/Approve & send/)));
    await pace(6000);
  });

  await scene("s17_extract", "17", async () => {
    await step("tab extractor", () => click(page.getByRole("tab", { name: /Transcript/ })));
    await step("pick doc", async () => {
      const sel = page.getByLabel("Meeting document");
      await moveTo(sel);
      const opts = await sel.locator("option").allTextContents();
      const arch = opts.find((o) => /Architecture sync/i.test(o));
      if (arch) await sel.selectOption({ label: arch });
    });
    await step("extract", () => click(btn(/^Extract/).first()));
    await pace(7000);
    await step("tab decisions", () => click(page.getByRole("tab", { name: /Decision log/ })));
    await step("search", () => typeSlow(page.getByPlaceholder(/Kafka, rollout/), "Kafka"));
    await pace(2500);
    await step("pick decision", () => click(page.getByRole("button", { name: /Kafka over SQS/ }).first()));
    await pace(5000);
  });

  await scene("s18_insights", "18", async () => {
    await go("/novapay/insights");
    await step("team", () => page.locator("#m-team").selectOption({ label: "Payments" }));
    await step("metric", async () => {
      const sel = page.locator("#m-metric");
      await moveTo(sel);
      const opts = await sel.locator("option").allTextContents();
      const rl = opts.find((o) => /review/i.test(o));
      if (rl) await sel.selectOption({ label: rl });
    });
    await pace(5000);
    await step("chart", () => hover(page.getByText("Metric explorer").first(), 4000));
    await step("team health", () => hover(page.getByText("Team health").first(), 5000));
    await step("ask", async () => {
      await typeSlow(page.locator("#ask-q"), "How has Payments review latency changed over the last 6 weeks?");
      await page.keyboard.press("Enter");
    });
    await pace(6000);
  });

  await scene("s19_settings", "19", async () => {
    for (const [p, ms] of [["persona", 8000], ["autonomy", 9000], ["learning", 9000], ["integrations", 8000], ["api-tokens", 6000]]) {
      await go(`/novapay/settings/${p}`);
      await page.evaluate(() => window.__chapter?.("19", "Settings: persona, autonomy, learning"));
      await step(`settings ${p}`, () => scrollBy(400, 6));
      await pace(ms);
    }
  });

  await scene("s20_outro", "", async () => {
    await go("/novapay/command-center");
    await pace(8000);
    await page.evaluate(() =>
      window.__card(
        "TwinPM",
        "It doesn't just answer questions about your program.<br/>It runs it the way you would, and shows its reasoning every time.",
      ),
    );
  });

  const video = page.video();
  await context.close();
  await browser.close();
  if (video) fs.renameSync(await video.path(), path.join(outDir, "walkthrough.webm"));
  fs.writeFileSync(path.join(outDir, "timeline.json"), JSON.stringify(timeline, null, 1));
  fs.writeFileSync(path.join(outDir, "failures.json"), JSON.stringify(failures, null, 1));
  log(`done; ${failures.length} failed steps`);
  for (const f of failures) log("  -", f);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
