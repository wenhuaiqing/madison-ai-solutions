// What each control is worth, found by switching it off and running the
// quarter again - and what the whole thing is worth in hours, on stated
// assumptions.

import { Bar, BarChart, Cell } from "recharts";
import { Link } from "react-router-dom";
import { useTheme } from "../../context/ThemeContext.jsx";
import { CONTROL_LABEL, fmtAud, fmtInt, fmtNum, timeModel, useApi } from "../../lib/api.js";
import {
  Badge, Callout, Card, ChartFrame, ChartOrTable, ErrorNote, Grid, Loading, PageHeader, SectionTitle, Stat, Table,
  useChartParts,
} from "../../lib/ui.jsx";

const KIND_TONE = { "paid in error": "critical", exposure: "warning", work: "neutral" };

export default function Value() {
  const { t } = useTheme();
  const { data, error } = useApi("/api/value");
  const parts = useChartParts();
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const h = data.headline;
  const a = data.assumptions;
  const rows = data.ablation.filter((r) => r.control !== "all_controls_off");
  const sum = (kind) => rows.filter((r) => r.kind === kind).reduce((n, r) => n + r.amount_aud, 0);
  const money = rows.filter((r) => r.kind !== "work").sort((x, y) => y.amount_aud - x.amount_aud)
    .map((r) => ({ ...r, label: CONTROL_LABEL[r.control] }));
  const work = rows.filter((r) => r.kind === "work");
  const extra = work.reduce((n, r) => n + r.extra_holds, 0);
  const m = timeModel(h, a);
  const pending = data.proposals.find((p) => p.status === "pending");
  const colour = (r) => (r.kind === "exposure" ? t.series[1] : t.series[0]);

  return (
    <>
      <PageHeader
        title="What it is worth"
        brief="A pragmatic streak. We'd rather ship something useful this week than chase a perfect solution for a month."
        subtitle="Each control was switched off in turn and the whole quarter run again from the raw files. What follows is what would have been paid that should not have been - not an estimate, a count. Three kinds of answer are kept apart because they are not the same thing: money paid in error, money released without the approval policy requires, and work created for nothing."
      />
      <Grid cols={4} min={200}>
        <Stat label="Would have been paid in error" value={fmtAud(sum("paid in error"), { short: true })} sub="duplicates, overcharges, goods not received" tone="critical" />
        <Stat label="Released without approval" value={fmtAud(sum("exposure"), { short: true })} sub="no order, or a changed bank account" tone="warning" />
        <Stat label="False holds avoided" value={fmtInt(extra)} sub={`about ${fmtNum((extra * a.resolve_exception_today) / 60, 0)} hours at today's handling time`} />
        <Stat label="Hours returned a quarter" value={fmtNum(m.saved, 0)} sub={`${fmtAud(m.savedAud)}; on assumed handling times`} emphasis />
      </Grid>

      <Callout tone="neutral" title="How to read this">
        The largest numbers are not the cleverest controls. Duplicates and goods not yet received are plain checks any
        accounts payable team already does by eye; the gain is that they are done on every invoice, the same way, and
        leave a record. The time saving rests on assumed minutes, set on the{" "}
        <Link to="/process" style={{ color: t.accent, fontWeight: 650 }}>process page</Link>. The dollar figures do not.
      </Callout>

      <SectionTitle>Controls that stop money leaving</SectionTitle>
      <Card hint="Switched off one at a time. 'Paid in error' has to be recovered; 'exposure' was released without the approval policy requires and is not necessarily lost.">
        <ChartOrTable
          chart={(
            <ChartFrame height={330}>
              <BarChart data={money} layout="vertical" margin={{ left: 30, right: 20 }}>
                {parts.grid}
                {parts.xAxis({ type: "number", tickFormatter: (v) => `$${Math.round(v / 1000)}k` })}
                {parts.yAxis({ type: "category", dataKey: "label", width: 130 })}
                {parts.tooltip({ formatter: (v) => fmtAud(v) })}
                <Bar dataKey="amount_aud" name="At risk">
                  {money.map((r) => <Cell key={r.control} fill={colour(r)} />)}
                </Bar>
              </BarChart>
            </ChartFrame>
          )}
          table={<Table columns={[
            { key: "label", label: "Control switched off", render: (r) => <b>{r.label}</b> },
            { key: "kind", label: "Kind", render: (r) => <Badge tone={KIND_TONE[r.kind]}>{r.kind}</Badge> },
            { key: "released", label: "Invoices released", align: "right", render: (r) => fmtInt(r.released) },
            { key: "amount_aud", label: "At risk", align: "right", render: (r) => fmtAud(r.amount_aud) },
            { key: "invoice_value_released_aud", label: "Invoice value", align: "right", render: (r) => fmtAud(r.invoice_value_released_aud) },
          ]} rows={money} />}
          defaultView="table"
        />
        <p style={{ fontSize: 12, color: t.textMuted, margin: "10px 0 0", lineHeight: 1.5 }}>
          In the chart, blue is paid in error and ochre is exposure. Quantity includes invoices billed before the goods
          arrived: paid early rather than lost, and still not payable under a three-way match.
        </p>
      </Card>

      <SectionTitle>Controls that stop work being created</SectionTitle>
      <Card hint="Nothing is mispaid without these. Instead, invoices that are perfectly fine get held and someone has to clear each one.">
        <Table columns={[
          { key: "control", label: "Control switched off", render: (r) => <b>{CONTROL_LABEL[r.control]}</b> },
          { key: "extra_holds", label: "Invoices held for nothing", align: "right", render: (r) => fmtInt(r.extra_holds) },
          { key: "hours", label: "Hours to clear them", align: "right", render: (r) => fmtNum((r.extra_holds * a.resolve_exception_today) / 60, 1) },
          { key: "why", label: "What it does", wrap: true, render: (r) => r.control === "uom_normalise"
            ? "Reads an invoice billed in drums, reels or boxes against an order in metres or each, using the pack size on the item master."
            : "Accepts freight that is not on the order when it is inside policy, instead of sending every one to a buyer." },
        ]} rows={work} />
      </Card>

      {pending && (
        <>
          <SectionTitle>The thing the data found that nobody asked about</SectionTitle>
          <Callout tone="ai" title={pending.title}>
            {pending.evidence.invoices_held} of the held invoices share one cause: a price notice received on{" "}
            {pending.evidence.notice_received_on.split("-").reverse().join("/")} and never loaded. Approving it releases{" "}
            {fmtAud(pending.preview.invoice_value_released_aud)} of invoices and takes the queue from{" "}
            {pending.preview.exceptions_before} to {pending.preview.exceptions_after}. It also means accepting{" "}
            {fmtAud(pending.preview.price_rise_cost_this_quarter_aud)} of price rise this quarter - which is why it is a buyer's
            decision, on the <Link to="/exceptions" style={{ color: t.accent2, fontWeight: 650 }}>exception queue</Link>, and not automatic.
          </Callout>
        </>
      )}

      <SectionTitle>What was deliberately not built</SectionTitle>
      <Card>
        <Table columns={[
          { key: 0, label: "Not built", render: (r) => <b>{r[0]}</b> },
          { key: 1, label: "Why not", wrap: true, render: (r) => r[1] },
          { key: 2, label: "What would change that", wrap: true, render: (r) => r[2] },
        ]} rows={[
          ["A model reading every invoice", "Most invoices agree with their order. Rules clear those for nothing, the same way every time.", "Suppliers whose layouts change often enough that parsers cost more to keep than a model costs to run."],
          ["Reading image-only invoices", `${h.unreadable} documents this quarter. Asking those suppliers for a text PDF is cheaper.`, "Volume in the hundreds, or a supplier who will not change."],
          ["Automatic approval above a confidence", "The agent's hard-case pass rate does not justify it, and a wrong payment is expensive to recover.", "Months of shadow-run evidence, and a category where a mistake is cheap."],
          ["A streaming pipeline", "Invoices are paid in periodic runs, so a batch is simpler to prove and to re-run.", "Same-day payment terms, or early-payment discounts worth chasing."],
        ]} />
      </Card>
    </>
  );
}
