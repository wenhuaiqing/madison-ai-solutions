// The delivery record: requirements traced to the tests that prove them,
// acceptance scenarios with the number each query returned, and the RAID log.

import { useTheme } from "../../context/ThemeContext.jsx";
import { useApi } from "../../lib/api.js";
import { Badge, Card, ErrorNote, Grid, Loading, Mono, PageHeader, SectionTitle, Stat, Table } from "../../lib/ui.jsx";

export default function Delivery() {
  const { t } = useTheme();
  const { data, error } = useApi("/api/delivery");
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const passed = data.uat.filter((u) => u.passed).length;
  const musts = data.requirements.filter((r) => r.priority === "Must").length;

  return (
    <>
      <PageHeader
        title="Delivery log & UAT"
        brief="Project delivery discipline. You've run work to a recognised delivery framework, you keep scope, risks, issues and decisions documented as you go."
        subtitle="Scope, risks, assumptions, issues and decisions for the accounts payable initiative, kept as files in the repository so a change to any of them is a reviewed commit. Requirements are not prose that drifts from the build: each names the test that proves it, and the test suite fails if that test does not exist. Acceptance scenarios are written the way the people signing off would say them, and each one runs as a query on every build."
      />
      <Grid cols={4} min={200}>
        <Stat label="Acceptance scenarios passing" value={`${passed} / ${data.uat.length}`} sub="re-run on every build and reprocess" emphasis tone={passed < data.uat.length ? "critical" : undefined} />
        <Stat label="Requirements" value={data.requirements.length} sub={`${musts} must-haves; every one traced to a test`} />
        <Stat label="Open risks and issues" value={data.risks.filter((r) => r.status.startsWith("Open")).length + data.issues.filter((i) => i.status.startsWith("Open")).length} sub="each with an owner or an action" tone="warning" />
        <Stat label="Decisions recorded" value={data.decisions.length} sub="with the reason and what was not chosen" />
      </Grid>

      <SectionTitle>Requirements, traced</SectionTitle>
      <Card>
        <Table maxHeight={620} columns={[
          { key: "id", label: "Id", render: (r) => <Mono>{r.id}</Mono> },
          { key: "statement", label: "Requirement", wrap: true },
          { key: "source", label: "Asked for by" },
          { key: "priority", label: "Priority", render: (r) => <Badge tone={r.priority === "Must" ? "serious" : "neutral"}>{r.priority}</Badge> },
          { key: "proved_by", label: "Proved by", wrap: true, render: (r) => r.proved_by.map((p) => <div key={p}><Mono dim>{p.split("::")[1]}</Mono></div>) },
          { key: "uat", label: "Shown by", render: (r) => r.uat.join(", ") || "-" },
        ]} rows={data.requirements} />
      </Card>

      <SectionTitle>User acceptance scenarios</SectionTitle>
      <Card hint="The 'found' column is what the query returned against the tables on screen right now.">
        <Table maxHeight={620} columns={[
          { key: "id", label: "Id", render: (r) => <Mono>{r.id}</Mono> },
          { key: "scenario", label: "Scenario", wrap: true },
          { key: "owner", label: "Signs off" },
          { key: "measures", label: "Counts", wrap: true },
          { key: "actual", label: "Found", align: "right", render: (r) => r.actual },
          { key: "passed", label: "Result", render: (r) => <Badge tone={r.passed ? "good" : "critical"}>{r.passed ? "passes" : "fails"}</Badge> },
        ]} rows={data.uat} />
      </Card>

      <SectionTitle>Decisions</SectionTitle>
      <Card>
        <Table maxHeight={640} columns={[
          { key: "id", label: "Id", render: (r) => <Mono>{r.id}</Mono> },
          { key: "decision", label: "Decision", wrap: true, render: (r) => <b>{r.decision}</b> },
          { key: "why", label: "Why", wrap: true },
          { key: "alternatives", label: "Not chosen", wrap: true },
        ]} rows={data.decisions} />
      </Card>

      <Grid cols={2} min={420}>
        <div>
          <SectionTitle>Assumptions</SectionTitle>
          <Card>
            <Table columns={[
              { key: "id", label: "Id", render: (r) => <Mono>{r.id}</Mono> },
              { key: "assumption", label: "Assumed", wrap: true },
              { key: "test", label: "How it gets tested", wrap: true },
            ]} rows={data.assumptions} />
          </Card>
        </div>
        <div>
          <SectionTitle>Issues</SectionTitle>
          <Card>
            <Table columns={[
              { key: "id", label: "Id", render: (r) => <Mono>{r.id}</Mono> },
              { key: "issue", label: "Issue", wrap: true },
              { key: "action", label: "Action", wrap: true },
              { key: "status", label: "Status", wrap: true },
            ]} rows={data.issues} />
          </Card>
        </div>
      </Grid>
      <p style={{ fontSize: 12, color: t.textMuted, lineHeight: 1.5 }}>
        Risks are on the AI risk page with their mitigations. Source: delivery/requirements.yaml, delivery/uat.yaml and delivery/raid.yaml.
      </p>
    </>
  );
}
