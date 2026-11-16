// The data layer: what landed, what each stage did to it, what was published,
// and proof that the same raw files give the same tables.

import { useState } from "react";
import { RotateCcw } from "lucide-react";
import { useTheme } from "../../context/ThemeContext.jsx";
import { CHECK_LABEL, api, fmtAud, fmtDateTime, fmtInt, fmtMs, useApi } from "../../lib/api.js";
import {
  Badge, CTAButton, Callout, Card, ErrorNote, Grid, KeyValues, Loading, Mono, PageHeader, SectionTitle, Select, Stat, Table,
} from "../../lib/ui.jsx";

const LAYER_TONE = { Bronze: "serious", Gold: "warning", Control: "neutral" };

function Lineage({ docs }) {
  const { t } = useTheme();
  const [docId, setDocId] = useState(docs[0]?.doc_id);
  const { data, error } = useApi(docId ? `/api/lineage?doc_id=${docId}` : null);
  return (
    <Card title="From a governed row back to the file it came from" right={
      <Select label="Document" value={docId} onChange={setDocId}
        options={docs.map((d) => ({ value: d.doc_id, label: `${d.doc_id}: ${d.check_id ? `held, ${CHECK_LABEL[d.check_id]}` : "matched"}` }))} />
    } hint="Every invoice row carries the file and line it was read from. Bank account numbers are masked before anything is shown or published.">
      <ErrorNote error={error} />
      {data && (
        <Grid cols={2} min={380}>
          <div>
            <KeyValues items={[
              ["File", <Mono>{data.document.file}</Mono>],
              ["Line in file", data.document.raw_row],
              ["File SHA-256", <Mono dim>{data.file.sha256.slice(0, 20)}...</Mono>],
              ["Sender", data.document.sender],
              ["Status", data.invoice.status === "held" ? `Held: ${CHECK_LABEL[data.invoice.check_id]}` : "Matched"],
              ["Total", data.invoice.total != null ? `${data.invoice.currency} ${Number(data.invoice.total).toLocaleString("en-AU", { minimumFractionDigits: 2 })}` : "-"],
            ]} />
            {data.exception && <p style={{ fontSize: 12.5, color: t.textMuted, lineHeight: 1.5, margin: "12px 0 0" }}>{data.exception.reason}</p>}
          </div>
          <pre style={{
            margin: 0, background: t.code, borderRadius: 10, padding: 12, fontSize: 11.5, lineHeight: 1.5, overflow: "auto",
            maxHeight: 260, fontFamily: "'JetBrains Mono', ui-monospace, monospace", color: t.text, whiteSpace: "pre-wrap", overflowWrap: "anywhere",
          }}>{data.document.text_masked}</pre>
        </Grid>
      )}
    </Card>
  );
}

function Rerun() {
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  const go = async () => {
    setBusy(true);
    setErr(null);
    try { setRes(await api("/api/replay", { method: "POST" })); } catch (e) { setErr(e); } finally { setBusy(false); }
  };
  return (
    <Card title="Re-run the quarter from raw" hint="Reads the raw files from disk, re-hashes them against the manifest pinned in the repository, re-runs the pipeline and compares every partition's digest with the one behind the tables on screen.">
      <div><CTAButton icon={RotateCcw} onClick={go} disabled={busy}>{busy ? "Running..." : "Re-run and compare"}</CTAButton></div>
      {err && <div style={{ marginTop: 12 }}><Callout tone="critical" title="Refused">{err.message}</Callout></div>}
      {res && (
        <div style={{ marginTop: 12 }}>
          <Callout tone={res.all_match ? "good" : "critical"} title={res.all_match ? "Identical" : "Different"}>
            {res.files.length} raw files and {res.partitions.length} governed partitions re-derived in {fmtMs(res.wall_ms)}.{" "}
            {res.all_match ? "Every digest matches." : "At least one digest differs."}
          </Callout>
          <Table maxHeight={240} columns={[
            { key: "partition", label: "Partition", render: (r) => <Mono>{r.partition}</Mono> },
            { key: "rows", label: "Rows", align: "right", render: (r) => fmtInt(r.rows) },
            { key: "sha256", label: "SHA-256", render: (r) => <Mono dim>{r.sha256.slice(0, 16)}</Mono> },
            { key: "match", label: "Recorded", render: (r) => <Badge tone={r.match ? "good" : "critical"}>{r.match ? "matches" : "differs"}</Badge> },
          ]} rows={res.partitions} />
        </div>
      )}
    </Card>
  );
}

export default function Lakehouse() {
  const { data, error } = useApi("/api/lakehouse");
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const rawRows = data.files.reduce((n, f) => n + f.rows, 0);
  const held = Object.fromEntries(data.by_check.map((c) => [c.check_id, c]));

  return (
    <>
      <PageHeader
        title="Lakehouse & lineage"
        brief="Help desk triage: a slice of day-to-day analytics/data enquiries land with you, Lakehouse ETL development/maintenance, reporting tasks."
        subtitle="ERP extracts and the invoice inbox land as files and are hashed. Seven timed stages turn them into a star schema the reports and the agent both read. Nothing is dropped on the way: a document that fails a check is held with its reason, and every row can be traced to the file and line it came from. Here it runs in DuckDB because the quarter fits in memory; the same stages are a medallion pipeline in Databricks when it does not."
      />
      <Grid cols={4} min={200}>
        <Stat label="Raw files" value={data.files.length} sub={`${fmtInt(rawRows)} rows, hashed on landing`} />
        <Stat label="Governed tables" value={data.tables.filter((x) => x.layer === "Gold").length} sub={`${data.partitions.length} partitions digested`} />
        <Stat label="Last run" value={fmtMs(data.run.wall_ms)} sub={`${data.run.run_id}, ${data.run.kind}; ${fmtAud(data.run.cost_aud, { decimals: 6 })} at list price`} emphasis />
        <Stat label="Triggered by" value={data.run.trigger} sub={fmtDateTime(data.run.started_at, { seconds: false })} />
      </Grid>

      <SectionTitle>Stages of the last run</SectionTitle>
      <Card>
        <Table columns={[
          { key: "stage", label: "Stage", render: (r) => <b>{r.stage}</b> },
          { key: "note", label: "What it did", wrap: true },
          { key: "rows_in", label: "In", align: "right", render: (r) => fmtInt(r.rows_in) },
          { key: "rows_out", label: "Out", align: "right", render: (r) => fmtInt(r.rows_out) },
          { key: "held", label: "Held", align: "right", render: (r) => r.held ? fmtInt(r.held) : "-" },
          { key: "wall_ms", label: "Time", align: "right", render: (r) => fmtMs(r.wall_ms) },
        ]} rows={data.stages} />
      </Card>

      <SectionTitle>The ten checks, in the order they run</SectionTitle>
      <Card hint="Hold, never guess: a check that cannot decide holds the invoice and records why.">
        <Table columns={[
          { key: "label", label: "Check", render: (r) => <b>{r.label}</b> },
          { key: "what", label: "Passes when", wrap: true },
          { key: "held", label: "If it fails", wrap: true },
          { key: "n", label: "Held", align: "right", render: (r) => fmtInt(held[r.id]?.held || 0) },
        ]} rows={data.checks} maxHeight={520} />
      </Card>

      <div style={{ marginTop: 14 }}><Lineage docs={data.sample_docs} /></div>
      <div style={{ marginTop: 14 }}><Rerun /></div>

      <SectionTitle>What is stored</SectionTitle>
      <Grid cols={2} min={420}>
        <Card title="Landed files (bronze)">
          <Table maxHeight={360} columns={[
            { key: "file", label: "File", render: (r) => <Mono>{r.file}</Mono> },
            { key: "rows", label: "Rows", align: "right", render: (r) => fmtInt(r.rows) },
            { key: "sha256", label: "SHA-256", render: (r) => <Mono dim>{r.sha256.slice(0, 12)}</Mono> },
          ]} rows={data.files} />
        </Card>
        <Card title="Tables">
          <Table maxHeight={360} columns={[
            { key: "name", label: "Table", render: (r) => <Mono>{r.name}</Mono> },
            { key: "layer", label: "Layer", render: (r) => <Badge tone={LAYER_TONE[r.layer]}>{r.layer}</Badge> },
            { key: "rows", label: "Rows", align: "right", render: (r) => fmtInt(r.rows) },
            { key: "what", label: "Holds", wrap: true },
          ]} rows={data.tables} />
        </Card>
      </Grid>
    </>
  );
}
