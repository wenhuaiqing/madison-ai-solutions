// The triage agent, measured: a graded eval against the runbook it has to
// beat, its failures listed rather than averaged away, and a live run on any
// held invoice with every tool call shown.

import { useMemo, useState } from "react";
import { BookOpen, Bot } from "lucide-react";
import { useLocation } from "react-router-dom";
import { useTheme } from "../../context/ThemeContext.jsx";
import { ACTION_LABEL, CATEGORY_LABEL, CHECK_LABEL, api, fmtDateTime, fmtMs, useApi } from "../../lib/api.js";
import {
  Badge, Button, CTAButton, Callout, Card, ErrorNote, Grid, KeyValues, Loading, Mono, PageHeader, SectionTitle, Select,
  Stat, Table,
} from "../../lib/ui.jsx";

function failureReason(g) {
  if (!g) return "error";
  if (g.harmful) return "harmful action";
  if (!g.category_ok) return "wrong category";
  if (!g.action_ok) return "wrong action";
  if (!g.all_grounded) return "ungrounded evidence";
  return "";
}

function Verdict({ r, label }) {
  const { t } = useTheme();
  if (!r) return null;
  return (
    <div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
        <Badge tone={label && r.category === label.category ? "good" : "critical"}>{CATEGORY_LABEL[r.category]}</Badge>
        <Badge tone={label && r.proposed_action === label.action ? "good" : "critical"}>{ACTION_LABEL[r.proposed_action]}</Badge>
        <Badge tone="neutral">confidence {Math.round(r.confidence * 100)}%</Badge>
        {r.releases_payment && <Badge tone="warning">would release money</Badge>}
      </div>
      <p style={{ fontSize: 13, margin: "0 0 8px", lineHeight: 1.5 }}>{r.summary}</p>
      <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, lineHeight: 1.55, color: t.textMuted }}>
        {r.evidence.map((e, i) => <li key={i}>{e}</li>)}
      </ul>
    </div>
  );
}

function LiveRun({ cases, initial }) {
  const { t } = useTheme();
  const [id, setId] = useState(initial && cases.some((c) => c.exception_id === initial) ? initial : cases[0]?.exception_id);
  const [busy, setBusy] = useState(false);
  const [run, setRun] = useState(null);
  const [err, setErr] = useState(null);
  const c = cases.find((x) => x.exception_id === id);

  const go = async (engine) => {
    setBusy(true);
    setErr(null);
    setRun(null);
    try {
      setRun(await api("/api/triage/run", { method: "POST", body: { exception_id: id, engine } }));
    } catch (e) { setErr(e); } finally { setBusy(false); }
  };

  return (
    <Card title="Triage a held invoice" right={
      <Select label="Invoice" value={id} onChange={(v) => { setId(v); setRun(null); }}
        options={cases.map((x) => ({ value: x.exception_id, label: `${x.exception_id}: ${CHECK_LABEL[x.check_id]}, ${x.supplier_name || "unreadable"}`.slice(0, 64) }))} />
    } hint="The agent chooses which tools to call; each answers from a snapshot frozen at the quarter's close, so the run can be graded against the label.">
      {c && (
        <KeyValues columns={3} items={[
          ["Held by", CHECK_LABEL[c.check_id]],
          ["Reason recorded", c.reason],
          ["Labelled", `${CATEGORY_LABEL[c.label_category]}: ${ACTION_LABEL[c.label_action]}`],
        ]} />
      )}
      <div style={{ display: "flex", gap: 10, margin: "14px 0 6px", flexWrap: "wrap" }}>
        <CTAButton icon={Bot} onClick={() => go("agent")} disabled={busy}>{busy ? "Investigating..." : "Run the agent"}</CTAButton>
        <Button icon={BookOpen} onClick={() => go("rules")} disabled={busy}>Run the runbook</Button>
      </div>
      {err && <Callout tone="critical" title="Refused">{err.message}</Callout>}
      {run && (
        <div style={{ marginTop: 10 }}>
          {run.fallback_reason && <Callout tone="warning" title="Degraded, and saying so">{run.fallback_reason}</Callout>}
          <Grid cols={2} min={340}>
            <div>
              <SectionTitle>Steps ({run.engine}, {run.model}, {fmtMs(run.ms)})</SectionTitle>
              <ol style={{ margin: 0, paddingLeft: 20, fontSize: 12.5, lineHeight: 1.7 }}>
                {run.trace.map((s, i) => (
                  <li key={i}>
                    {s.kind === "tool" && <>called <Mono>{s.tool}</Mono></>}
                    {s.kind === "submit" && <b>submitted a verdict</b>}
                    {s.kind === "rule" && <>followed the runbook entry for the <Mono>{s.check}</Mono> check</>}
                    {s.kind === "invalid_submit" && <span style={{ color: t.status.critical }}>submitted an invalid verdict and was told why</span>}
                    {s.kind === "text" && <span style={{ color: t.textMuted }}>replied without a tool call and was reminded</span>}
                  </li>
                ))}
              </ol>
            </div>
            <div>
              <SectionTitle right={<Badge tone={run.grade.passed ? "good" : "critical"}>{run.grade.passed ? "passes" : failureReason(run.grade)}</Badge>}>Proposal</SectionTitle>
              <Verdict r={run.result} label={run.label} />
              <p style={{ fontSize: 12, color: t.textMuted, margin: "10px 0 0" }}>
                Evidence grounded: {run.grade.grounded} of {run.grade.evidence}. {run.grade.harmful ? "Harmful: this would pay what should be held, or reject what should be paid." : ""}
              </p>
            </div>
          </Grid>
        </div>
      )}
    </Card>
  );
}

export default function Triage() {
  const location = useLocation();
  const initial = new URLSearchParams(location.search).get("exception");
  const { data, error } = useApi("/api/triage");
  const [engine, setEngine] = useState("agent");

  const cases = useMemo(() => {
    if (!data?.eval) return [];
    const by = {};
    for (const r of data.eval.results) {
      by[r.case_id] ??= { case_id: r.case_id, kind: r.kind, label: r.label, why: r.why };
      by[r.case_id][r.engine] = r;
    }
    return Object.values(by);
  }, [data]);

  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const ev = data.eval;
  const a = ev?.summary?.agent;
  const r = ev?.summary?.rules;
  const shown = a ? engine : "rules";
  const failures = cases.filter((c) => c[shown] && !(c[shown].grade?.passed));
  const said = (x) => x?.result ? <Badge tone={x.grade?.passed ? "good" : "critical"}>{CATEGORY_LABEL[x.result.category]}</Badge> : (x ? "error" : "-");
  const easy = (s) => s.by_kind.standard;

  return (
    <>
      <PageHeader
        title="AI triage"
        brief="You should be able to talk confidently about AI platforms, models, AI capabilities and limitations... Good instincts on AI risk."
        subtitle="When the match holds an invoice, someone has to work out what is actually wrong before anyone acts. The agent drafts that first read: it chooses which of seven tools to call, reads what they return, and submits a typed proposal - a category, an action, and evidence that must quote what the tools said. It cannot release, reject or change anything. It is graded against the accounts payable runbook on the same cases, including six built so the check's name points at the wrong answer and three where the invoice itself tries to talk its way to payment."
      />

      {ev ? (
        <>
          <Grid cols={4} min={200}>
            <Stat label="Agent passes" value={a ? `${a.passed} / ${a.cases}` : "not graded"} sub={a ? `${ev.model}; ${a.errors || 0} error(s)` : "needs a model key; see below"} emphasis />
            <Stat label="Runbook passes" value={`${r.passed} / ${r.cases}`} sub="the check that held it decides" />
            <Stat label="Hard cases" value={a ? `${a.by_kind.hard.passed} vs ${r.by_kind.hard.passed}` : `${r.by_kind.hard.passed} of ${r.by_kind.hard.cases}`} sub={a ? `agent vs runbook, of ${r.by_kind.hard.cases}` : "runbook; built so the check's name misleads"} tone="warning" />
            <Stat label="Harmful proposals" value={a ? `${a.harmful} vs ${r.harmful}` : r.harmful} sub={a ? "agent vs runbook: would mispay or wrongly reject" : "runbook: would mispay or wrongly reject"} tone="critical" />
          </Grid>
          {a ? (
            <>
              <Grid cols={4} min={200}>
                <Stat label="Adversarial text" value={`${a.by_kind.adversarial.passed} / ${a.by_kind.adversarial.cases}`} sub={`agent holds the line; ${a.by_kind.adversarial.harmful} talked into paying`} tone={a.by_kind.adversarial.harmful ? "critical" : undefined} />
                <Stat label="Evidence grounded" value={`${a.evidence_grounded} / ${a.evidence_items}`} sub="statements quoting a value a tool returned" />
                <Stat label="Latency" value={`${fmtMs(a.p50_ms)} p50`} sub={`${fmtMs(a.p95_ms)} p95; ${a.avg_steps} steps on average`} />
                <Stat label="Escalated to a person" value={a.abstained} sub="said it did not know" />
              </Grid>
              <Callout tone="ai" title="What the numbers say">
                On the {easy(a).cases} ordinary cases the runbook passes {easy(r).passed} in under a millisecond and the
                agent passes {easy(a).passed} in about {fmtMs(a.p50_ms)} - there the agent adds cost and nothing else. It
                earns its place only where the check's name points at the wrong answer: {a.by_kind.hard.passed} of{" "}
                {a.by_kind.hard.cases} hard cases against the runbook's {r.by_kind.hard.passed}. That is better than the
                procedure and not good enough to act alone, which is why it cannot. The model is not deterministic, so
                which cases it passes moves between runs. Last full run {fmtDateTime(ev.run_at, { seconds: false })}.
              </Callout>
            </>
          ) : (
            <Callout tone="warning" title="The agent has not been graded on this build">
              The runbook's results below are real: {r.passed} of {r.cases}, and {r.by_kind.hard.passed} of the{" "}
              {r.by_kind.hard.cases} hard cases, {r.harmful} of them harmful. The agent's column fills in when the eval is
              run with a model key (one command, in the README). Until it has been, nothing here claims the agent is any good.
            </Callout>
          )}
        </>
      ) : <Callout tone="warning">No eval has been run on this build.</Callout>}

      <LiveRun cases={data.cases} initial={initial} />

      {ev && (
        <>
          <SectionTitle>The hard cases</SectionTitle>
          <Card>
            <Table maxHeight={560} columns={[
              { key: "case_id", label: "Case", render: (c) => <Mono>{c.case_id.replace("hard-", "")}</Mono> },
              { key: "why", label: "What makes it hard", wrap: true },
              { key: "label", label: "Right answer", render: (c) => CATEGORY_LABEL[c.label.category] },
              { key: "rules", label: "Runbook", render: (c) => said(c.rules) },
              { key: "agent", label: "Agent", render: (c) => said(c.agent) },
            ]} rows={cases.filter((c) => c.kind === "hard")} />
          </Card>

          <SectionTitle>The invoice that argues back</SectionTitle>
          <Card hint="Real held invoices with text added that tries to instruct whoever reads it. The runbook never reads free text, so it cannot be persuaded. The agent reads everything - which is exactly why this is measured rather than assumed.">
            <Table columns={[
              { key: "case_id", label: "Case", render: (c) => <Mono>{c.case_id.replace("adv-", "")}</Mono> },
              { key: "why", label: "What the text tries", wrap: true },
              { key: "label", label: "Right answer", render: (c) => `${CATEGORY_LABEL[c.label.category]}: ${ACTION_LABEL[c.label.action]}`, wrap: true },
              { key: "rules", label: "Runbook", render: (c) => said(c.rules) },
              { key: "agent", label: "Agent", render: (c) => said(c.agent) },
            ]} rows={cases.filter((c) => c.kind === "adversarial")} />
          </Card>

          <SectionTitle right={a ? <Select label="Engine" value={engine} onChange={setEngine} options={[{ value: "agent", label: "Agent" }, { value: "rules", label: "Runbook" }]} /> : null}>
            Every failure, not an average
          </SectionTitle>
          <Card>
            <Table columns={[
              { key: "case_id", label: "Case", render: (c) => <Mono>{c.case_id}</Mono> },
              { key: "reason", label: "Failed on", render: (c) => <Badge tone="critical">{failureReason(c[shown].grade)}</Badge> },
              { key: "said", label: "Said", wrap: true, render: (c) => c[shown].result ? `${CATEGORY_LABEL[c[shown].result.category]}: ${ACTION_LABEL[c[shown].result.proposed_action]}` : c[shown].error },
              { key: "right", label: "Right answer", wrap: true, render: (c) => `${CATEGORY_LABEL[c.label.category]}: ${ACTION_LABEL[c.label.action]}` },
            ]} rows={failures} empty="No failures." />
          </Card>
        </>
      )}

      <SectionTitle>What the agent may and may not do</SectionTitle>
      <Card>
        <KeyValues items={[
          ["May", `Read a held invoice's frozen snapshot through ${data.tools.length} tools and propose a category, an action and its evidence.`],
          ["May not", "Write anything. Its service identity is refused by the decision endpoint, and a test proves it."],
          ["Never sees", "A bank account number. It is told whether the account matches the master, never the account."],
          ["Budget", "Six steps; the last is forced to submit. 30 s per model call; a timeout is not retried."],
          ["When the model is down", "The runbook answers, and the page says so. Nothing degrades silently."],
          ["Model", data.llm_configured ? `${data.model}, over the OpenAI protocol - the provider is configuration` : "none configured on this deployment; the runbook answers"],
          ["Abuse", "Eight runs per address and sixty in all per five minutes."],
          ["Recent live runs", data.recent.length ? data.recent.map((x) => `${x.exception_id} (${x.engine})`).slice(0, 6).join(", ") : "none yet on this replica"],
        ]} />
      </Card>
    </>
  );
}
