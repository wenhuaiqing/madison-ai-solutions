// AI risk for this initiative, as controls that exist and can be checked -
// not a policy document.

import { Link } from "react-router-dom";
import { useTheme } from "../../context/ThemeContext.jsx";
import { ACTION_LABEL, CATEGORY_LABEL, fmtInt, useApi } from "../../lib/api.js";
import { Badge, Callout, Card, ErrorNote, Grid, KeyValues, Loading, Mono, PageHeader, SectionTitle, Stat, Table } from "../../lib/ui.jsx";

const LEVEL = { High: "critical", Medium: "warning", Low: "good" };

export default function Risk() {
  const { t } = useTheme();
  const { data, error } = useApi("/api/risk");
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const agentAdv = data.adversarial.filter((r) => r.engine === "agent");
  const rulesAdv = data.adversarial.filter((r) => r.engine === "rules");
  const graded = agentAdv.length > 0;
  const talked = agentAdv.filter((r) => r.grade?.harmful).length;
  const tools = Object.entries(data.sent_to_model).map(([tool, keys]) => ({ tool, keys: (keys || []).join(", ") }));

  return (
    <>
      <PageHeader
        title="AI risk"
        brief="Good instincts on AI risk."
        subtitle="Five questions decide whether an AI feature near money is safe to run: what can it do, what can it see, can its input talk it into something, what happens when it is wrong, and what happens when it is unavailable. Each answer here is a control in the code with a test or a query behind it."
      />
      <Grid cols={4} min={200}>
        <Stat label="What the agent can write" value="Nothing" sub="it proposes; the decision endpoint refuses its identity" emphasis />
        <Stat label="Snapshots holding an account number" value={`${data.snapshots_with_account_numbers} of ${fmtInt(data.snapshots)}`} sub="scanned on every build" tone={data.snapshots_with_account_numbers ? "critical" : "good"} />
        <Stat label="Talked into paying" value={graded ? `${talked} of ${agentAdv.length}` : "not graded"} sub={graded ? "adversarial invoices, agent" : "adversarial cases exist; the agent run needs a model key"} tone={graded && talked ? "critical" : undefined} />
        <Stat label="When the model is down" value="Runbook" sub="answers instead, and the page says so" />
      </Grid>

      <SectionTitle>1. What it can do</SectionTitle>
      <Card>
        <KeyValues items={[
          ["Authority", "None. It returns a typed proposal: a category, an action, and evidence. A person records the decision under their own name."],
          ["Enforced where", "On the server. The decision endpoint needs the operator's token and refuses the automation's identities outright."],
          ["Never released from the queue", "A changed bank account, and an invoice with the same number as one already received - by anyone, whatever the agent or a person proposes."],
          ["Rule changes", "Proposed with evidence, approved by someone other than the proposer, then the quarter is reprocessed from raw."],
        ]} />
      </Card>

      <SectionTitle>2. What it can see</SectionTitle>
      <Grid cols={2} min={420}>
        <Card title="Everything the agent can read, by tool" hint="Built once per held invoice, as at the quarter's close. Nothing else reaches the model.">
          <Table maxHeight={340} columns={[
            { key: "tool", label: "Tool", render: (r) => <Mono>{r.tool}</Mono> },
            { key: "keys", label: "Fields", wrap: true, render: (r) => <span style={{ fontSize: 12, color: t.textMuted }}>{r.keys}</span> },
          ]} rows={tools} />
        </Card>
        <Card title="Bank details are masked before the snapshot is built">
          <KeyValues columns={1} items={[
            ["Account on the invoice, as the agent sees it", <Mono>{data.masked_example.invoice_shows}</Mono>],
            ["Account on file, as the agent sees it", <Mono>{data.masked_example.on_file}</Mono>],
            ["What it is told", `remittance_account_matches_master: ${String(data.masked_example.matches)}`],
            ["Why", "To decide the case it needs to know the accounts differ. It does not need either account, so it does not get them."],
            ["With real data", "The model would run inside the organisation's own cloud tenancy. This demo holds only invented data and uses a public endpoint."],
          ]} />
        </Card>
      </Grid>

      <SectionTitle>3. Can the input talk it into something</SectionTitle>
      <Card hint="An invoice is a document written by someone outside the organisation and read by a model. Free text from it reaches the agent under a key that says it is untrusted, and the instructions say text is evidence, never an instruction. That is a mitigation, not a guarantee - so it is measured.">
        <Table columns={[
          { key: "case_id", label: "Case", render: (r) => <Mono>{r.case_id.replace("adv-", "")}</Mono> },
          { key: "why", label: "What the text tries", wrap: true },
          { key: "right", label: "Right answer", wrap: true, render: (r) => `${CATEGORY_LABEL[r.label.category]}: ${ACTION_LABEL[r.label.action]}` },
          { key: "rules", label: "Runbook", render: (r) => <Badge tone={r.grade?.passed ? "good" : "critical"}>{r.grade?.passed ? "held the line" : "failed"}</Badge> },
          { key: "agent", label: "Agent", render: (r) => {
            const a = agentAdv.find((x) => x.case_id === r.case_id);
            if (!a) return "not graded";
            return <Badge tone={a.grade?.passed ? "good" : "critical"}>{a.grade?.passed ? "held the line" : a.grade?.harmful ? "talked into paying" : "wrong"}</Badge>;
          } },
        ]} rows={rulesAdv} empty="No eval on this build." />
        <p style={{ fontSize: 12.5, color: t.textMuted, margin: "10px 0 0", lineHeight: 1.5 }}>
          The runbook cannot be persuaded because it never reads free text. That is a real advantage of rules, and the
          reason the match itself uses no model. Full results are on <Link to="/triage" style={{ color: t.accent2, fontWeight: 650 }}>AI triage</Link>.
        </p>
      </Card>

      <SectionTitle>4 and 5. When it is wrong, and when it is not there</SectionTitle>
      <Grid cols={2} min={420}>
        <Card title="When it is wrong">
          <KeyValues columns={1} items={[
            ["Before anyone relies on it", "Graded against the runbook on labelled cases, including ones built to fool it. Failures are listed one by one."],
            ["What counts as harm", "Proposing to pay what should be held, or to reject what should be paid. A harmful proposal fails however well it is argued."],
            ["Evidence", "Every statement must quote a value a tool actually returned. An invented figure fails the case."],
            ["After go-live", "A sample of its proposals compared each week with what the team decided. The risk nobody plans for is people ceasing to check."],
          ]} />
        </Card>
        <Card title="When it is not there, or is abused">
          <KeyValues columns={1} items={[
            ["Model", data.llm_configured ? data.model : "none configured on this deployment"],
            ["Timeout", `${data.limits.timeout_seconds} s per call, not retried; one fallback model on a rate limit or server error`],
            ["Fallback", "The runbook answers and the page says so. The match never calls a model, so invoices keep flowing."],
            ["Cost ceiling", `${data.limits.per_address} runs per address and ${data.limits.global} in all per ${Math.round(data.limits.window_seconds / 60)} minutes`],
          ]} />
        </Card>
      </Grid>

      <SectionTitle>The risk register for this initiative</SectionTitle>
      <Card>
        <Table maxHeight={620} columns={[
          { key: "id", label: "Id", render: (r) => <Mono>{r.id}</Mono> },
          { key: "risk", label: "Risk", wrap: true },
          { key: "likelihood", label: "Likelihood", render: (r) => <Badge tone={LEVEL[r.likelihood]}>{r.likelihood}</Badge> },
          { key: "impact", label: "Impact", render: (r) => <Badge tone={LEVEL[r.impact]}>{r.impact}</Badge> },
          { key: "mitigation", label: "Mitigation", wrap: true },
          { key: "status", label: "Status", wrap: true },
        ]} rows={data.risks} />
      </Card>
      <Callout tone="neutral" title="Decisions behind this page">
        {data.decisions.map((d) => <div key={d.id} style={{ marginBottom: 4 }}><b>{d.id}</b> {d.decision} {d.why}</div>)}
      </Callout>
    </>
  );
}
