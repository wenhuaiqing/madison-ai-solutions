// Self-serve: one definition of each number, the help desk log measured
// against those definitions, and read-only SQL over the governed tables.

import { useState } from "react";
import { Play } from "lucide-react";
import { useTheme } from "../../context/ThemeContext.jsx";
import { api, fmtAud, fmtInt, fmtMs, fmtNum, pct, useApi } from "../../lib/api.js";
import {
  Badge, Button, CTAButton, Callout, Card, ErrorNote, Grid, Loading, Mono, PageHeader, SectionTitle, SegmentedControl,
  Stat, Table,
} from "../../lib/ui.jsx";

const ROUTE = {
  measure: { tone: "good", label: "published measure" },
  query: { tone: "warning", label: "ad hoc query" },
  build: { tone: "neutral", label: "needs building" },
};

function fmtValue(m) {
  if (m.value == null) return "-";
  if (m.format === "aud") return fmtAud(m.value);
  if (m.format === "pct") return pct(m.value);
  if (m.format === "int") return fmtInt(m.value);
  return fmtNum(m.value, 0);
}

export default function SelfServe() {
  const { t } = useTheme();
  const { data, error } = useApi("/api/selfserve");
  const [lang, setLang] = useState("sql");
  const [sql, setSql] = useState("SELECT month, entity, count(*) AS invoices, round(sum(total_aud)) AS total_aud\nFROM fact_invoice\nWHERE entity IS NOT NULL\nGROUP BY 1, 2\nORDER BY 1, 2");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;

  const run = async (text = sql) => {
    setBusy(true);
    setErr(null);
    try { setRes(await api("/api/query", { method: "POST", body: { sql: text } })); } catch (e) { setRes(null); setErr(e); } finally { setBusy(false); }
  };
  const n = data.enquiries.length;
  const count = (route) => data.enquiries.filter((e) => e.route === route).length;

  return (
    <>
      <PageHeader
        title="Self-serve reporting"
        brief="Some BAU reporting/analytics, most is self-serve, ad hoc requests still occur."
        subtitle="Self-serve works when there is one definition of each number and people can find it. Each measure below is defined once, with the SQL that runs here and the DAX for the Power BI model over the same star schema. The help desk log is then scored against those definitions: what share of last quarter's questions a published measure already answers, what needed a one-off query, and what cannot be answered until something is built."
      />
      <Grid cols={4} min={200}>
        <Stat label="Answered by a published measure" value={pct(count("measure") / n, 0)} sub={`${count("measure")} of ${n} enquiries last quarter`} emphasis />
        <Stat label="Needed an ad hoc query" value={count("query")} sub="a recurring one is a measure waiting to be published" />
        <Stat label="Needs building" value={count("build")} sub="data that is not landed yet" tone="warning" />
        <Stat label="Published measures" value={data.measures.length} sub="each with SQL and DAX" />
      </Grid>

      <SectionTitle right={<SegmentedControl label="Definition language" value={lang} onChange={setLang} options={[{ value: "sql", label: "SQL" }, { value: "dax", label: "DAX" }]} />}>
        Published measures
      </SectionTitle>
      <Card hint="The value is the SQL run against the governed tables just now. The DAX is the same definition written for the semantic model; it is not executed here.">
        <Table maxHeight={560} columns={[
          { key: "name", label: "Measure", render: (m) => <b>{m.name}</b> },
          { key: "value", label: "Value", align: "right", render: fmtValue },
          { key: "description", label: "Means", wrap: true },
          { key: "def", label: lang === "sql" ? "SQL" : "DAX", wrap: true, render: (m) => <Mono dim>{m[lang]}</Mono> },
        ]} rows={data.measures} />
      </Card>

      <SectionTitle>The help desk log, scored</SectionTitle>
      <Card hint="An invented quarter of enquiries. Select an ad hoc one to run its query below.">
        <Table maxHeight={460} onRowClick={(e) => { if (e.route === "query") { setSql(e.answer); run(e.answer); } }} columns={[
          { key: "id", label: "Ticket", render: (e) => <Mono>{e.id}</Mono> },
          { key: "team", label: "Team" },
          { key: "asked", label: "Asked", wrap: true },
          { key: "route", label: "Answered by", render: (e) => <Badge tone={ROUTE[e.route].tone}>{ROUTE[e.route].label}</Badge> },
          { key: "answer", label: "How", wrap: true, render: (e) => e.route === "measure" ? e.measure_name : e.route === "query" ? "select to run" : e.answer },
        ]} rows={data.enquiries} />
      </Card>

      <SectionTitle>Ask the governed tables</SectionTitle>
      <Grid cols={2} min={420}>
        <Card title="SQL" hint="SELECT only, against an allowlist of tables, with a row limit and a five-second ceiling. The connection itself cannot read files or URLs.">
          <textarea value={sql} onChange={(e) => setSql(e.target.value)} spellCheck={false} aria-label="SQL" style={{
            width: "100%", minHeight: 170, fontFamily: "'JetBrains Mono', ui-monospace, monospace", fontSize: 12.5,
            background: t.code, color: t.text, border: `1px solid ${t.border}`, borderRadius: 10, padding: 12, resize: "vertical", lineHeight: 1.5,
          }} />
          <div style={{ marginTop: 10, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
            <CTAButton icon={Play} onClick={() => run()} disabled={busy}>{busy ? "Running..." : "Run"}</CTAButton>
            <Button onClick={() => { const q = "SELECT * FROM read_csv('/etc/passwd')"; setSql(q); run(q); }}>Try something it refuses</Button>
            {res && <span style={{ fontSize: 12, color: t.textMuted }}>{res.rows.length} rows in {fmtMs(res.ms)}</span>}
          </div>
        </Card>
        <Card title="Tables and columns">
          <Table maxHeight={300} columns={[
            { key: "table_name", label: "Table", render: (r) => <Mono>{r.table_name}</Mono> },
            { key: "columns", label: "Columns", wrap: true, render: (r) => <span style={{ fontSize: 12, color: t.textMuted }}>{r.columns}</span> },
          ]} rows={data.schema} />
        </Card>
      </Grid>
      {err && <Callout tone="critical" title="Refused">{err.message}</Callout>}
      {res && (
        <Card title="Result" hint={`Ran as: ${res.sql.replace(/\s+/g, " ").slice(0, 220)}`}>
          <Table maxHeight={420} columns={res.columns.map((c) => ({ key: c, label: c, render: (r) => r[c] === null ? "null" : typeof r[c] === "object" ? JSON.stringify(r[c]) : String(r[c]) }))} rows={res.rows} empty="No rows." />
        </Card>
      )}
    </>
  );
}
