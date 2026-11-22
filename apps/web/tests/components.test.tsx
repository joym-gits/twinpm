import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { DriverList } from "@/components/twin/driver-list";
import { ForecastBand } from "@/components/twin/forecast-band";
import { HealthGauge } from "@/components/twin/health-gauge";
import { RiskBadge } from "@/components/twin/risk-badge";
import { SuggestionCard } from "@/components/twin/suggestion-card";
import type { Suggestion } from "@/lib/hooks/use-suggestions";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const base: Suggestion = {
  id: "11111111-1111-1111-1111-111111111111",
  program_id: null,
  agent: "delegation",
  type: "reassign",
  title: "Reassign PAY-239 to Karan Malhotra",
  payload: { work_item_ids: ["x"], to_person_id: "y" },
  explanation: "Karan Malhotra: strong skill match (68%), 38% spare capacity.",
  drivers: [{ feature: "skill_match", value: 0.68, contribution: 0.68, label: "skill match" }],
  citations: [{ type: "work_item", id: "x", label: "PAY-239" }],
  autonomy_level_required: 3,
  status: "pending",
  responded_by: null,
  responded_at: null,
  feedback_reason: null,
  result: {},
  created_at: new Date().toISOString(),
  expires_at: null,
  undone_at: null,
  thread_id: null,
};

describe("HealthGauge", () => {
  it("labels the score, tone and weekly delta", () => {
    render(<HealthGauge score={72.4} delta={-6.2} />);
    expect(screen.getByLabelText(/Program health 72 out of 100, At risk/)).toBeInTheDocument();
    expect(screen.getByText(/↓6 this week/)).toBeInTheDocument();
  });
  it("marks high scores healthy", () => {
    render(<HealthGauge score={91} />);
    expect(screen.getByText("Healthy")).toBeInTheDocument();
  });
});

describe("DriverList", () => {
  it("renders factors largest first with widths relative to the max", () => {
    render(
      <DriverList
        drivers={[
          { feature: "a", label: "Owner at 112% utilisation", contribution: 0.8 },
          { feature: "b", label: "PR review time 2.6x the team norm", contribution: 0.4 },
        ]}
      />,
    );
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Owner at 112% utilisation");
    const bar = items[1]!.querySelector(".bg-warning") as HTMLElement;
    expect(bar.style.width).toBe("50%");
  });
  it("shows an empty message", () => {
    render(<DriverList drivers={[]} />);
    expect(screen.getByText(/No contributing factors/)).toBeInTheDocument();
  });
});

describe("ForecastBand", () => {
  it("shows P50/P80/P95 and days late vs target", () => {
    render(<ForecastBand p50="2027-03-10" p80="2027-03-22" p95="2027-04-02" target="2027-03-13" />);
    expect(screen.getByText(/\(\+9d\)/)).toBeInTheDocument();
    expect(screen.getByLabelText(/P50 .*P80 .*P95 .*target/)).toBeInTheDocument();
  });
  it("reports on track when P80 is before target", () => {
    render(<ForecastBand p50="2027-03-01" p80="2027-03-05" p95="2027-03-09" target="2027-03-13" />);
    expect(screen.getByText(/on track/)).toBeInTheDocument();
  });
});

describe("RiskBadge", () => {
  it("never relies on colour alone", () => {
    render(<RiskBadge probability={0.97} />);
    expect(screen.getByLabelText("Critical risk, 97 percent")).toHaveTextContent("Critical");
  });
});

describe("SuggestionCard", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("shows level, status and twin label, and reveals drivers on Why?", () => {
    wrap(<SuggestionCard s={base} twinName="Priya's twin" />);
    expect(screen.getByText("L3 Approve")).toBeInTheDocument();
    expect(screen.getByText(/Proposed by Priya's twin/)).toBeInTheDocument();
    expect(screen.queryByText("skill match")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Why\?/ }));
    expect(screen.getByText("skill match")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Open source: work item PAY-239/ })).toBeInTheDocument();
  });

  it("accepts via the respond endpoint", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ...base, status: "accepted" }), { status: 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    wrap(<SuggestionCard s={base} />);
    fireEvent.click(screen.getByRole("button", { name: /Accept/ }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const req = (fetchMock.mock.calls[0] as unknown as [Request])[0];
    expect(req.url).toContain(`/api/v1/suggestions/${base.id}/respond`);
    expect(await req.clone().json()).toMatchObject({ action: "accept" });
  });

  it("lets status reports be edited before approval", () => {
    wrap(<SuggestionCard s={{ ...base, type: "status_report", payload: { title: "t", body: "Status: Amber" } }} />);
    fireEvent.click(screen.getByRole("button", { name: /Edit/ }));
    expect(screen.getByLabelText(/Edit before approving/)).toHaveValue("Status: Amber");
    expect(screen.getByRole("button", { name: /Save & approve/ })).toBeInTheDocument();
  });

  it("offers undo for executed reversible actions", () => {
    wrap(<SuggestionCard s={{ ...base, status: "accepted" }} />);
    expect(screen.getByRole("button", { name: /Undo/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Accept/ })).not.toBeInTheDocument();
  });
});
