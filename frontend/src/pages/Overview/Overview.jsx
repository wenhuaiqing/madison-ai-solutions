// The roadmap: one initiative built and running, and what its data turned up
// next. Each card says what the AI does and what it is not allowed to do.

import { Link } from "react-router-dom";
import { Bar, BarChart } from "recharts";
import { useTheme } from "../../context/ThemeContext.jsx";
import { CHECK_LABEL, fmtAud, fmtInt, pct, useApi } from "../../lib/api.js";
import {
  Badge, Callout, Card, ChartFrame, ChartOrTable, ErrorNote, Grid, KeyValues, Loading, PageHeader, SectionTitle, Stat,
  Table, useChartParts,
} from "../../lib/ui.jsx";

const STAGE_TONE = { "Pilot ready": "good", Discovery: "ai", Candidate: "neutral", Backlog: "neutral", "Not yet worth building": "warning" };
const LINK_LABEL = { exceptions: "Exception queue", triage: "AI triage", value: "What it is worth", process: "Process", selfserve: "Self-serve reporting" };

export default function Overview() {
  const { t } = useTheme();
  const { data, error } = useApi("/api/overview");
  const parts = useChartParts();
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const h = data.headline;
  const months = data.by_month.map((m) => ({ ...m, label: `${m.month.slice(5)}/${m.month.slice(0, 4)}` }));
  const pending = data.proposals.filter((p) => p.status === "pending");

  return (
    <>
      <PageHeader
        title="AI roadmap"
        brief="Project time: the bulk of your week, working directly with the AI Delivery Manager on initiatives pulled from our AI roadmap. Discovery, design, build, test, and getting people to actually use what you've built."
        subtitle="One initiative taken the whole way: a distributor's accounts payable, from how the work is done today to a running three-way match with an AI agent drafting the first read of every invoice it holds. The other initiatives are what that work turned up, sized from its data. The business, its suppliers and every invoice are invented."
      />
      <Grid cols={4} min={200}>
        <Stat label={`Invoices, ${data.period}`} value={fmtInt(h.documents)} sub={`${fmtAud(h.value_aud, { short: true })} billed by ${h.suppliers} suppliers`} emphasis />
        <Stat label="Matched, nobody touching" value={pct(h.straight_through)} sub={`${fmtInt(h.matched)} invoices agree with order and receipt`} />
        <Stat label="Held for a person" value={fmtInt(h.held)} sub={`${h.decided} decided so far on this deployment`} tone={h.held ? "warning" : undefined} />
        <Stat label="Held before payment" value={fmtAud(h.at_risk_aud, { short: true })} sub="would have been paid in error or without approval" />
      </Grid>

      {pending.length > 0 && (
        <Callout tone="ai" title="One decision is waiting">
          {pending[0].title}. Evidence and consequences are on the <Link to="/exceptions" style={{ color: t.accent2, fontWeight: 650 }}>exception queue</Link>;
          whoever proposed it cannot approve it.
        </Callout>
      )}

      <SectionTitle>Initiatives</SectionTitle>
      <Grid cols={2} min={420}>
        {data.roadmap.map((i) => (
          <Card key={i.id} title={`${i.id}  ${i.name}`} right={<Badge tone={STAGE_TONE[i.stage] || "neutral"}>{i.stage}</Badge>} hint={i.teams.join(", ")}>
            <KeyValues columns={1} items={[
              ["Problem", i.problem],
              ["Approach", i.approach],
              ["What the AI does", i.ai_role],
              ["How we would know it worked", i.measure],
              ["Risk", i.risk_tier],
              ["Next", i.next],
            ]} />
            {i.links.length > 0 && (
              <div style={{ display: "flex", gap: 14, marginTop: 12, flexWrap: "wrap" }}>
                {i.links.map((l) => <Link key={l} to={`/${l}`} style={{ color: t.accent, fontWeight: 650, fontSize: 12.5 }}>{LINK_LABEL[l]}</Link>)}
              </div>
            )}
          </Card>
        ))}
      </Grid>

      <SectionTitle>The quarter AI-01 ran on</SectionTitle>
      <Grid cols={2} min={420}>
        <Card title="Invoices by month" hint="Received in the month; matched with nobody touching them, or held.">
          <ChartOrTable
            chart={(
              <ChartFrame height={250}>
                <BarChart data={months}>
                  {parts.grid}
                  {parts.xAxis({ dataKey: "label" })}
                  {parts.yAxis({})}
                  {parts.tooltip({})}
                  {parts.legend({})}
                  <Bar dataKey="matched" name="Matched" stackId="a" fill={t.series[0]} />
                  <Bar dataKey="held" name="Held" stackId="a" fill={t.series[1]} />
                </BarChart>
              </ChartFrame>
            )}
            table={<Table columns={[
              { key: "label", label: "Month" },
              { key: "received", label: "Received", align: "right", render: (r) => fmtInt(r.received) },
              { key: "matched", label: "Matched", align: "right", render: (r) => fmtInt(r.matched) },
              { key: "held", label: "Held", align: "right", render: (r) => fmtInt(r.held) },
              { key: "value_aud", label: "Billed", align: "right", render: (r) => fmtAud(r.value_aud) },
            ]} rows={months} />}
          />
        </Card>
        <Card title="Why invoices were held" hint="The first check to fail is the reason on the exception.">
          <Table maxHeight={300} columns={[
            { key: "check_id", label: "Check", render: (r) => CHECK_LABEL[r.check_id] },
            { key: "held", label: "Held", align: "right", render: (r) => fmtInt(r.held) },
            { key: "at_risk_aud", label: "At risk", align: "right", render: (r) => fmtAud(r.at_risk_aud) },
          ]} rows={data.by_check} />
        </Card>
      </Grid>
      <p style={{ fontSize: 12, color: t.textMuted, margin: "4px 0 0", lineHeight: 1.5 }}>
        Acceptance scenarios passing: {data.uat.passed} of {data.uat.n}. Triage eval: {data.eval?.agent
          ? `agent ${data.eval.agent.passed} of ${data.eval.agent.cases}, runbook ${data.eval.rules.passed} of ${data.eval.rules.cases}`
          : data.eval ? `runbook ${data.eval.rules.passed} of ${data.eval.rules.cases}; the agent has not been graded on this build` : "not run"}.
      </p>
    </>
  );
}
