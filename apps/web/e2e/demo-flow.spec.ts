import { expect, test } from "@playwright/test";

const PASSWORD = process.env.SEED_DEMO_PASSWORD ?? "TwinPM-demo-2026!";

/**
 * The Section 13 demo flow, in demo mode (no Anthropic key):
 * login as Priya → Payments briefing → See options → rebalance → approve →
 * audit/activity shows it → executive status report → approve & send.
 */
test("TPM demo flow", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("priya@novapay.example");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/novapay\/command-center/);

  // Health and the #1 briefing item.
  await expect(page.getByTestId("health-card")).toContainText("Program health");
  const first = page.getByTestId("briefing-item").first();
  await expect(first).toContainText("Payments API v2 likely to slip");

  // Why? shows drivers and evidence.
  await first.getByRole("button", { name: /Why\?/ }).click();
  await expect(first.getByRole("list", { name: "Contributing factors" })).toBeVisible();

  // Options: three simulated scenarios.
  await first.getByRole("button", { name: "See options" }).click();
  const options = page.getByTestId("options");
  await expect(options).toContainText("Rebalance");
  await expect(options).toContainText("Descope");
  await expect(options).toContainText("Move the date");
  await options.getByRole("button", { name: /Choose rebalance/ }).click();

  // Delegation: rebalance plan with Karan and Li Wei; approve all.
  await expect(page).toHaveURL(/\/novapay\/delegation/);
  await expect(page.getByText("Karan Malhotra").first()).toBeVisible();
  await expect(page.getByText("Li Wei").first()).toBeVisible();
  await page.getByRole("button", { name: /Approve all/ }).click();
  await expect(page.getByText(/accepted/i).first()).toBeVisible();

  // Audit trail: the activity feed shows the reassignments.
  await page.getByRole("link", { name: "Command Center" }).click();
  await expect(page.getByTestId("activity")).toContainText(/reassigned a work item/);

  // Executive update in Priya's voice, edited and approved.
  await page.getByRole("link", { name: "Comms Studio" }).click();
  await page.getByRole("button", { name: "Generate" }).click();
  const draft = page.getByRole("textbox", { name: /draft/i });
  await expect(draft).toHaveValue(/Status: (Red|Amber|Green)/);
  await expect(draft).toHaveAttribute("aria-busy", "false");
  await expect(page.getByRole("button", { name: /Approve & send/ })).toBeEnabled();
  await draft.press("ControlOrMeta+End");
  await draft.pressSequentially("\nAsk: please confirm the rebalance by Friday.");
  await expect(page.getByText(/Edited\./)).toBeVisible();
  await page.getByRole("button", { name: /Approve & send/ }).click();
  await expect(page.getByText(/Ask: please confirm the rebalance by Friday/).last()).toBeVisible();
});
