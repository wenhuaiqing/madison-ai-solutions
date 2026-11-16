// Drive the operator's path in a real browser: a refusal, a decision, an
// approval that reprocesses the quarter, a triage run, then reset.
//
//   BASE=http://localhost:5251 TOKEN=<DEMO_WRITE_TOKEN> node evals/flow.mjs

import { chromium } from "playwright";

const BASE = process.env.BASE || "http://localhost:5251";
const TOKEN = process.env.TOKEN || "";
const CHANNEL = process.env.BROWSER_CHANNEL || undefined;
const OUT = process.env.OUT || "./page-shots";
const browser = await chromium.launch(CHANNEL ? { channel: CHANNEL } : {});
const page = await (await browser.newContext({ viewport: { width: 1500, height: 1000 } })).newPage();
const steps = [];
const expect = async (name, locator) => {
  await locator.first().waitFor({ timeout: 20_000 });
  steps.push(name);
  console.log(`ok   ${name}`);
};

await page.goto(`${BASE}/exceptions?write_token=${TOKEN}`, { waitUntil: "networkidle" });
await expect("the token is scrubbed from the URL", page.getByText("Operator: writes enabled"));
if (page.url().includes("write_token")) throw new Error("token still in the URL");

await page.getByLabel("Check").selectOption("bank_details");
await page.locator("tbody tr").first().click();
await page.getByLabel("Decision").selectOption("release_for_payment");
await page.getByRole("button", { name: "Record the decision" }).click();
await expect("releasing a changed bank account is refused", page.getByText("cannot be actioned from this queue"));
await page.getByLabel("Decision").selectOption("escalate_to_human");
await page.getByRole("button", { name: "Record the decision" }).click();
await expect("escalating it is recorded", page.getByText("Escalate to a person, by AP team lead"));

await page.getByLabel("Acting as").first().fill("ap-automation");
await page.getByRole("button", { name: "Approve and reprocess" }).click();
await expect("the proposer cannot approve", page.getByText("cannot also decide it"));
await page.getByLabel("Acting as").first().fill("Procurement lead");
await page.getByRole("button", { name: "Approve and reprocess" }).click();
await expect("approval reprocesses from raw", page.getByText("Reprocessed from raw"));
await page.screenshot({ path: `${OUT}/flow-approved.png`, fullPage: true });

await page.goto(`${BASE}/lakehouse`, { waitUntil: "networkidle" });
await page.getByRole("button", { name: "Re-run and compare" }).click();
await expect("the re-run matches after the approval", page.getByText("Every digest matches."));

await page.goto(`${BASE}/triage`, { waitUntil: "networkidle" });
await page.getByRole("button", { name: "Run the runbook" }).click();
await expect("the runbook triages a held invoice", page.getByText("Evidence grounded"));

await page.goto(`${BASE}/operations`, { waitUntil: "networkidle" });
await expect("refusals are in the audit log", page.getByText("refused"));
await page.getByRole("button", { name: "Reset the demo" }).click();
await page.waitForTimeout(800);
await browser.close();
console.log(`\n${steps.length} steps passed`);
