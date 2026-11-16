// The process as it is done today and as it would be done after, with the
// volumes from the data and the handling times stated as what they are:
// assumptions, editable here, to be replaced by a time study.

import { useState } from "react";
import { useTheme } from "../../context/ThemeContext.jsx";
import { CHECK_LABEL, fmtAud, fmtInt, fmtNum, timeModel, useApi } from "../../lib/api.js";
import { Callout, Card, ErrorNote, Grid, Loading, PageHeader, SectionTitle, Stat, Table } from "../../lib/ui.jsx";

const ASSUMPTION_LABEL = {
  open_and_key: "Open and key an invoice (min)",
  find_order_and_match: "Find the order and match it (min)",
  check_receipt: "Check the goods receipt (min)",
  resolve_exception_today: "Resolve an exception today (min)",
  resolve_exception_with_proposal: "Decide an exception with a drafted proposal (min)",
  sample_review_share: "Share of matched invoices spot-checked",
  sample_review: "Spot-check one matched invoice (min)",
  loaded_cost_per_hour_aud: "Loaded cost per hour (AUD)",
};

export default function Process() {
  const { t } = useTheme();
  const { data, error } = useApi("/api/process");
  const [edits, setEdits] = useState({});
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const h = data.headline;
  const a = { ...data.assumptions, ...edits };
  const m = timeModel(h, a);
  const mins = (n, each) => `${fmtNum((n * each) / 60, 1)} h`;

  const today = [
    { step: "1. Open the email, portal or EDI message and key the invoice into the ERP", who: "AP officer", volume: h.documents, hours: mins(h.documents, a.open_and_key) },
    { step: "2. Find the purchase order and compare lines and prices", who: "AP officer", volume: h.with_order, hours: mins(h.with_order, a.find_order_and_match) },
    { step: "3. Check the goods receipt", who: "AP officer", volume: h.with_order, hours: mins(h.with_order, a.check_receipt) },
    { step: "4. Chase and resolve anything that does not agree", who: "AP officer, buyer, supplier", volume: h.held, hours: mins(h.held, a.resolve_exception_today) },
  ];
  const after = [
    { step: "1. Documents are read into typed fields; one that cannot be read is held, not guessed", who: "Pipeline", volume: h.documents, hours: "-" },
    { step: "2. Three-way match: order, receipt and price within policy", who: "Pipeline", volume: h.matched, hours: "-" },
    { step: "3. Key the documents that could not be read", who: "AP officer", volume: h.unreadable, hours: mins(h.unreadable, a.open_and_key) },
    { step: "4. Spot-check a sample of matched invoices", who: "AP officer", volume: Math.round(h.matched * a.sample_review_share), hours: mins(h.matched * a.sample_review_share, a.sample_review) },
    { step: "5. Decide each held invoice, starting from the agent's drafted read and evidence", who: "AP officer, buyer", volume: h.held, hours: mins(h.held, a.resolve_exception_with_proposal) },
  ];
  const cols = [
    { key: "step", label: "Step", wrap: true },
    { key: "who", label: "Who" },
    { key: "volume", label: "Invoices", align: "right", render: (r) => fmtInt(r.volume) },
    { key: "hours", label: "Hours a quarter", align: "right" },
  ];

  return (
    <>
      <PageHeader
        title="Process, today and after"
        brief="Embedding with business teams to document how things really work today and designing how they should work tomorrow."
        subtitle="Accounts payable for one quarter, mapped twice. The volumes at each step are counted from the data. The minutes are assumptions - the kind a first conversation gives you - and they are editable below, because the honest state of a business case before a time study is a range, not a number."
      />
      <Grid cols={4} min={200}>
        <Stat label="Hours a quarter, today" value={fmtNum(m.today, 0)} sub="every invoice keyed and matched by hand" />
        <Stat label="Hours a quarter, after" value={fmtNum(m.after, 0)} sub="people only on what the match holds" emphasis />
        <Stat label="Hours returned" value={fmtNum(m.saved, 0)} sub={`${fmtAud(m.savedAud)} a quarter at ${fmtAud(a.loaded_cost_per_hour_aud)} an hour`} tone="good" />
        <Stat label="Absorbed by policy" value={fmtInt(h.uom_converted + h.charge_accepted)} sub={`${h.uom_converted} unit conversions, ${h.charge_accepted} freight charges inside tolerance`} />
      </Grid>
      <Callout tone="warning" title="Assumptions, not measurements">
        The handling times are placeholders until someone sits with the team and times the work. Change any of them
        and every hour on this page and on What it is worth moves with it. The invoice counts are not assumptions.
      </Callout>

      <Grid cols={2} min={420}>
        <Card title="Today" hint="Every invoice takes the same path, whether or not anything is wrong with it.">
          <Table columns={cols} rows={today} />
        </Card>
        <Card title="After" hint="The match clears what agrees. People spend their time where judgement is needed.">
          <Table columns={cols} rows={after} />
        </Card>
      </Grid>

      <SectionTitle>Handling times</SectionTitle>
      <Card>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 300px), 1fr))", gap: "10px 22px" }}>
          {Object.keys(ASSUMPTION_LABEL).map((k) => (
            <label key={k} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, fontSize: 12.5, color: t.textMuted }}>
              {ASSUMPTION_LABEL[k]}
              <input type="number" step="0.5" min="0" value={a[k]} aria-label={ASSUMPTION_LABEL[k]}
                onChange={(e) => setEdits({ ...edits, [k]: Math.max(0, Number(e.target.value) || 0) })}
                style={{ width: 84, background: t.surface, color: t.text, border: `1px solid ${t.border}`, borderRadius: 8, padding: "5px 8px", fontSize: 12.5, fontFamily: "inherit", textAlign: "right" }} />
            </label>
          ))}
        </div>
      </Card>

      <SectionTitle>What arrives, and how</SectionTitle>
      <Grid cols={2} min={420}>
        <Card title="Channels and layouts" hint="Three layouts, three channels. Each supplier keeps its own.">
          <Table columns={[
            { key: "channel", label: "Channel", render: (r) => ({ email: "Email", portal: "Supplier portal", edi: "EDI" }[r.channel]) },
            { key: "layout", label: "Layout", render: (r) => r.layout ? `Layout ${r.layout}` : "Unreadable" },
            { key: "documents", label: "Documents", align: "right", render: (r) => fmtInt(r.documents) },
          ]} rows={data.channels} />
        </Card>
        <Card title="Where the held invoices are" hint="Step 5 of the new process, by the check that held them.">
          <Table columns={[
            { key: "check_id", label: "Check", render: (r) => CHECK_LABEL[r.check_id] },
            { key: "held", label: "Held", align: "right", render: (r) => fmtInt(r.held) },
            { key: "invoice_value_aud", label: "Invoice value", align: "right", render: (r) => fmtAud(r.invoice_value_aud) },
          ]} rows={data.by_check} maxHeight={300} />
        </Card>
      </Grid>

      <SectionTitle>The policy the match applies</SectionTitle>
      <Card hint="Written once, shown here, enforced by the checks and handed to the agent as a tool - so the policy people read is the policy that runs.">
        <ol style={{ margin: 0, paddingLeft: 20, fontSize: 13, lineHeight: 1.7 }}>
          {data.rules.map((r) => <li key={r}>{r}</li>)}
        </ol>
      </Card>
    </>
  );
}
