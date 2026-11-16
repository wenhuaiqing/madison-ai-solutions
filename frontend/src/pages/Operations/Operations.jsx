// Running it: every run with its cost, who did what, how the API is behaving,
// and whether anyone is using it.

import { useState } from "react";
import { RotateCcw } from "lucide-react";
import { useTheme } from "../../context/ThemeContext.jsx";
import { apiWrite, fmtAud, fmtDateTime, fmtInt, fmtMs, useApi } from "../../lib/api.js";
import { Badge, Button, Callout, Card, ErrorNote, Grid, KeyValues, Loading, Mono, PageHeader, SectionTitle, Stat, Table } from "../../lib/ui.jsx";

export default function Operations() {
  const { t } = useTheme();
  const { data, error, reload } = useApi("/api/operations");
  const { data: meta } = useApi("/api/meta");
  const [err, setErr] = useState(null);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const u = data.usage;
  const reset = async () => {
    setErr(null);
    try { await apiWrite("/api/reset"); reload(); } catch (e) { setErr(e); }
  };

  return (
    <>
      <PageHeader
        title="Operations & adoption"
        brief="Owning the relationship with your stakeholders - demos, training, UAT, adoption. If nobody's using it, it doesn't count."
        subtitle="Adoption is a number, so it is counted: decisions recorded, agent runs, and writes the server refused, all from this deployment's own audit log. Beside it, what running this costs and how it behaves. The counts start at zero on every fresh replica, and the page says so rather than inventing a trend."
        right={<Button icon={RotateCcw} onClick={reset}>Reset the demo</Button>}
      />
      {err && <Callout tone="critical" title="Refused">{err.message}</Callout>}
      <Grid cols={4} min={200}>
        <Stat label="Decisions recorded" value={fmtInt(u.decisions)} sub="held invoices decided by a named person" emphasis />
        <Stat label="Agent and runbook runs" value={fmtInt(u.triage_runs)} sub="first reads asked for on this replica" />
        <Stat label="Writes refused" value={fmtInt(u.refused_writes)} sub="the rule said no, and it is on the record" tone={u.refused_writes ? "warning" : undefined} />
        <Stat label="Build" value={`${data.build_seconds} s`} sub="generate, match, ablation, acceptance scenarios" />
      </Grid>

      <Grid cols={2} min={420}>
        <Card title="How this is deployed" hint="Sized to cost nothing while nobody is looking at it.">
          <KeyValues columns={1} items={[
            ["Compute", "One Azure Container App, two containers (nginx and FastAPI), scale to zero. A cold start is a few seconds."],
            ["Data", "Built inside the image from code and a seed, and verified against digests pinned in the repository. No database server, no storage account."],
            ["Images", "Public on GitHub Container Registry, built by GitHub Actions on every push. No registry to pay for."],
            ["Secrets", "The model key and the write token are Container Apps secrets, set by Terraform. Nothing is in the image or the repository."],
            ["Cost guard", "Its own resource group with a monthly budget alert; logs capped by a daily quota. Deleting the resource group removes everything."],
            ["Version", <Mono>{meta?.version || "dev"}</Mono>],
          ]} />
        </Card>
        <Card title="Checks that run before anything ships">
          <KeyValues columns={1} items={[
            ["Build", "Regenerates the quarter and fails if any raw file or governed partition differs from the pinned digest."],
            ["Acceptance", `${data.uat.filter((x) => x.passed).length} of ${data.uat.length} scenarios pass; a failing one fails the build.`],
            ["Tests", "Pipeline, workflow rules, guards and the delivery record, run in CI before the images are published."],
            ["Pages", "Every page rendered in a browser at desktop and phone width; fails on a console error, a failed call or a number that did not format."],
            ["Agent eval", data.eval.model ? `${data.eval.cases} cases, ${data.eval.model}, ${fmtDateTime(data.eval.run_at, { seconds: false })}` : `${data.eval.cases ?? 0} cases graded for the runbook; the agent run needs a model key`],
          ]} />
        </Card>
      </Grid>

      <SectionTitle>Runs</SectionTitle>
      <Card>
        <Table columns={[
          { key: "run_id", label: "Run", render: (r) => <Mono>{r.run_id}</Mono> },
          { key: "kind", label: "Kind" },
          { key: "trigger", label: "Triggered by", wrap: true },
          { key: "wall_ms", label: "Time", align: "right", render: (r) => fmtMs(r.wall_ms) },
          { key: "cost_aud", label: "Cost at list price", align: "right", render: (r) => fmtAud(r.cost_aud, { decimals: 6 }) },
          { key: "output_sha256", label: "Output digest", render: (r) => <Mono dim>{r.output_sha256.slice(0, 12)}</Mono> },
        ]} rows={data.runs} />
      </Card>

      <SectionTitle>Audit log</SectionTitle>
      <Card hint="Every write and every refusal. Empty until someone with the operator link does something.">
        <Table maxHeight={360} columns={[
          { key: "ts", label: "When", render: (r) => fmtDateTime(r.ts) },
          { key: "actor", label: "Who" },
          { key: "action", label: "Action", render: (r) => <Mono>{r.action}</Mono> },
          { key: "subject", label: "On", render: (r) => <Mono>{r.subject}</Mono> },
          { key: "outcome", label: "Outcome", render: (r) => <Badge tone={r.outcome === "done" ? "good" : "critical"}>{r.outcome}</Badge> },
          { key: "detail", label: "Detail", wrap: true, render: (r) => <span style={{ fontSize: 12, color: t.textMuted }}>{String(r.detail).slice(0, 160)}</span> },
        ]} rows={data.audit} empty="Nothing written yet on this replica." />
      </Card>

      <SectionTitle>API latency since this replica started</SectionTitle>
      <Card hint="Kept in memory; resets when the app scales to zero.">
        <Table maxHeight={360} columns={[
          { key: "path", label: "Endpoint", render: (r) => <Mono>{r.path}</Mono> },
          { key: "calls", label: "Calls", align: "right", render: (r) => fmtInt(r.calls) },
          { key: "p50_ms", label: "p50", align: "right", render: (r) => fmtMs(r.p50_ms) },
          { key: "p95_ms", label: "p95", align: "right", render: (r) => fmtMs(r.p95_ms) },
          { key: "refused", label: "Refused", align: "right", render: (r) => r.refused || "-" },
          { key: "errors", label: "Errors", align: "right", render: (r) => r.errors || "-" },
        ]} rows={data.timings} empty="No calls yet." />
      </Card>
    </>
  );
}
