// The work queue: every held invoice with its reason, the document itself,
// and the decision - which the server refuses when the rule says no.

import { useState } from "react";
import { Check, X } from "lucide-react";
import { Link } from "react-router-dom";
import { actorName, setActorName, writeToken } from "../../config.js";
import { useTheme } from "../../context/ThemeContext.jsx";
import { ACTION_LABEL, CHECK_LABEL, apiWrite, fmtAud, fmtDate, fmtDateTime, fmtInt, fmtMs, pct, useApi } from "../../lib/api.js";
import {
  Badge, Button, CTAButton, Callout, Card, ErrorNote, Grid, KeyValues, Loading, Mono, PageHeader, SectionTitle, Select,
  Stat, Table,
} from "../../lib/ui.jsx";

function Actor({ value, onChange }) {
  const { t } = useTheme();
  return (
    <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: t.textMuted }}>
      Acting as
      <input value={value} onChange={(e) => { onChange(e.target.value); setActorName(e.target.value); }} aria-label="Acting as"
        style={{ background: t.surface, color: t.text, border: `1px solid ${t.border}`, borderRadius: 8, padding: "5px 8px", fontSize: 12.5, fontFamily: "inherit", width: 150 }} />
    </label>
  );
}

function Proposal({ p, onDone }) {
  const [actor, setActor] = useState(actorName());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [res, setRes] = useState(null);
  const e = p.evidence;
  const v = p.preview;
  const decide = async (verb) => {
    setBusy(true);
    setErr(null);
    try {
      setRes(await apiWrite(`/api/proposals/${p.proposal_id}/${verb}`, {}));
      onDone();
    } catch (x) { setErr(x); } finally { setBusy(false); }
  };
  return (
    <Card title={`${p.proposal_id}: ${p.title}`} right={<Badge tone={p.status === "pending" ? "ai" : p.status === "approved" ? "good" : "neutral"}>{p.status}</Badge>}
      hint={`Proposed by ${p.proposed_by}. The notice was received on ${fmtDate(e.notice_received_on)} and its ERP status is "${e.erp_status}". Holding each invoice is correct; clearing ${e.invoices_held} of them one at a time for the same reason is waste.`}>
      <Grid cols={2} min={340}>
        <div>
          <SectionTitle>Evidence, computed from the data</SectionTitle>
          <KeyValues items={[
            ["Lines billed since the effective date", fmtInt(e.lines_since_effective)],
            [`At exactly ${e.uplift_pct}% over the order`, `${fmtInt(e.lines_at_exactly_the_uplift)} of ${fmtInt(e.lines_since_effective)}`],
            ["Lines in the 30 days before", fmtInt(e.lines_in_the_30_days_before)],
            ["Of those, at the order price", `${fmtInt(e.lines_before_at_order_price)} of ${fmtInt(e.lines_in_the_30_days_before)}`],
            ["Invoices held for price", `${e.invoices_held}, worth ${fmtAud(e.invoices_held_aud)}`],
          ]} />
        </div>
        <div>
          <SectionTitle>If approved</SectionTitle>
          <KeyValues items={[
            ["Invoices released", `${v.invoices_released}, worth ${fmtAud(v.invoice_value_released_aud)}`],
            ["Held invoices", `${v.exceptions_before} to ${v.exceptions_after}`],
            ["New holds", v.new_holds],
            ["Cost of the price rise this quarter", fmtAud(v.price_rise_cost_this_quarter_aud)],
          ]} />
        </div>
      </Grid>
      {p.status === "pending" ? (
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 14, flexWrap: "wrap" }}>
          <Actor value={actor} onChange={setActor} />
          <CTAButton icon={Check} onClick={() => decide("approve")} disabled={busy}>{busy ? "Reprocessing..." : "Approve and reprocess"}</CTAButton>
          <Button icon={X} onClick={() => decide("reject")} disabled={busy}>Reject</Button>
        </div>
      ) : (
        <p style={{ fontSize: 12.5, margin: "12px 0 0" }}>Decided by {p.decided_by} on {fmtDateTime(p.decided_at, { seconds: false })}.</p>
      )}
      {!writeToken() && p.status === "pending" && (
        <p style={{ fontSize: 12, margin: "10px 0 0", opacity: 0.7 }}>This is the read-only link: try it, and the server will say why it refuses. Accepting a price rise is procurement's decision, not accounts payable's and not a model's.</p>
      )}
      {err && <div style={{ marginTop: 12 }}><Callout tone="critical" title="Refused">{err.message}</Callout></div>}
      {res?.after && (
        <div style={{ marginTop: 12 }}>
          <Callout tone="good" title={`Reprocessed from raw in ${fmtMs(res.wall_ms)} (${res.run_id})`}>
            Held invoices {res.before.held} to {res.after.held}; matched with nobody touching them {pct(res.before.straight_through)} to {pct(res.after.straight_through)}. Every page now reads the new tables.
          </Callout>
        </div>
      )}
    </Card>
  );
}

function Detail({ id, onDone }) {
  const { t } = useTheme();
  const { data, error, reload } = useApi(`/api/exceptions/${id}`);
  const [action, setAction] = useState("");
  const [actor, setActor] = useState(actorName());
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const e = data.exception;
  const chosen = action || e.label_action;
  const decide = async () => {
    setBusy(true);
    setErr(null);
    try {
      await apiWrite(`/api/exceptions/${id}/decide`, { action: chosen });
      reload();
      onDone();
    } catch (x) { setErr(x); } finally { setBusy(false); }
  };
  return (
    <Card title={`${e.exception_id}: ${e.supplier_name || "unreadable document"}`} right={<Badge tone="warning">{CHECK_LABEL[e.check_id]}</Badge>}>
      <Callout tone="warning" title="Why it is held">{e.reason}</Callout>
      <Grid cols={2} min={380}>
        <div>
          <KeyValues items={[
            ["Invoice", e.invoice_number || "-"],
            ["Received", fmtDateTime(e.received_at, { seconds: false })],
            ["Invoice value", fmtAud(e.total_aud, { decimals: 2 })],
            ["At risk", fmtAud(e.at_risk_aud, { decimals: 2 })],
            ["Read from", <Mono>{data.document.file} line {data.document.raw_row}</Mono>],
            ["Order", data.invoice.po_number || "none quoted"],
          ]} />
          {data.lines.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <Table maxHeight={220} columns={[
                { key: "item_id", label: "Item", render: (r) => r.item_id || r.description },
                { key: "qty_matched", label: "Billed", align: "right", render: (r) => Number(r.qty_matched).toLocaleString("en-AU") },
                { key: "received_qty", label: "Received", align: "right", render: (r) => r.received_qty == null ? "-" : Number(r.received_qty).toLocaleString("en-AU") },
                { key: "unit_price_matched", label: "Price", align: "right", render: (r) => Number(r.unit_price_matched).toFixed(4) },
                { key: "expected_unit_price", label: "Order price", align: "right", render: (r) => r.expected_unit_price == null ? "-" : Number(r.expected_unit_price).toFixed(4) },
              ]} rows={data.lines} />
            </div>
          )}
        </div>
        <pre style={{
          margin: 0, background: t.code, borderRadius: 10, padding: 12, fontSize: 11.5, lineHeight: 1.5, overflow: "auto", maxHeight: 330,
          fontFamily: "'JetBrains Mono', ui-monospace, monospace", color: t.text, whiteSpace: "pre-wrap", overflowWrap: "anywhere",
        }}>{data.document.text_masked}</pre>
      </Grid>
      {data.decision ? (
        <Callout tone="good" title="Decided">{ACTION_LABEL[data.decision.action]}, by {data.decision.actor} on {fmtDateTime(data.decision.decided_at, { seconds: false })}.</Callout>
      ) : (
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <Select label="Decision" value={chosen} onChange={setAction} options={Object.entries(ACTION_LABEL).filter(([k]) => k !== "propose_price_list_update").map(([value, label]) => ({ value, label }))} />
          <Actor value={actor} onChange={setActor} />
          <CTAButton icon={Check} onClick={decide} disabled={busy}>Record the decision</CTAButton>
          <Link to={`/triage?exception=${id}`} style={{ color: t.accent2, fontWeight: 650, fontSize: 12.5 }}>Ask the agent for a first read</Link>
        </div>
      )}
      {err && <div style={{ marginTop: 12 }}><Callout tone="critical" title="Refused">{err.message}</Callout></div>}
    </Card>
  );
}

export default function Exceptions() {
  const { data, error, reload } = useApi("/api/exceptions");
  const [check, setCheck] = useState("all");
  const [open, setOpen] = useState(null);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const h = data.headline;
  const rows = data.rows.filter((r) => check === "all" || r.check_id === check);

  return (
    <>
      <PageHeader
        title="Exception queue"
        brief="Owning the relationship with your stakeholders - demos, training, UAT, adoption. If nobody's using it, it doesn't count."
        subtitle="This is the screen the accounts payable team would work from: only the invoices the match could not clear, each with the reason, the document as it arrived, and the money at risk. A decision is recorded once, under a name, and the server refuses the ones policy forbids - try releasing a changed bank account, or deciding as the automation's own identity."
      />
      <Grid cols={4} min={200}>
        <Stat label="Held" value={fmtInt(h.held)} sub={`of ${fmtInt(h.documents)} received`} emphasis />
        <Stat label="At risk if paid as billed" value={fmtAud(h.at_risk_aud, { short: true })} sub="in error, or without approval" tone="warning" />
        <Stat label="Decided" value={fmtInt(h.decided)} sub="recorded on this deployment, each under a name" />
        <Stat label="Proposals waiting" value={data.proposals.filter((p) => p.status === "pending").length} sub="rule changes need a second person" />
      </Grid>

      {data.proposals.map((p) => <div key={p.proposal_id} style={{ marginBottom: 14 }}><Proposal p={p} onDone={reload} /></div>)}

      <SectionTitle right={<Select label="Check" value={check} onChange={(v) => { setCheck(v); setOpen(null); }}
        options={[{ value: "all", label: "All checks" }, ...data.by_check.map((c) => ({ value: c.check_id, label: `${CHECK_LABEL[c.check_id]} (${c.held})` }))]} />}>
        Held invoices, largest risk first
      </SectionTitle>
      {open && <div style={{ marginBottom: 14 }}><Detail key={open} id={open} onDone={reload} /></div>}
      <Card hint="Select a row to open the invoice.">
        <Table maxHeight={520} onRowClick={(r) => setOpen(r.exception_id)} columns={[
          { key: "exception_id", label: "Exception", render: (r) => <Mono>{r.exception_id}</Mono> },
          { key: "supplier_name", label: "Supplier", render: (r) => r.supplier_name || "Unreadable" },
          { key: "check_id", label: "Held by", render: (r) => <Badge tone="warning">{CHECK_LABEL[r.check_id]}</Badge> },
          { key: "received_at", label: "Received", render: (r) => fmtDate(r.received_at) },
          { key: "total_aud", label: "Invoice", align: "right", render: (r) => fmtAud(r.total_aud) },
          { key: "at_risk_aud", label: "At risk", align: "right", render: (r) => fmtAud(r.at_risk_aud) },
          { key: "decided_action", label: "Decision", render: (r) => r.decided_action ? <Badge tone="good">{ACTION_LABEL[r.decided_action]}</Badge> : "open" },
        ]} rows={rows} />
      </Card>
    </>
  );
}
