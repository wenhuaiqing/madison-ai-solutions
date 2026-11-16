// The advertisement's own list, mapped to where each point is shown working,
// then the first ninety days - as a plan that starts by listening.

import { Link } from "react-router-dom";
import { useTheme } from "../../context/ThemeContext.jsx";
import { Callout, Card, Grid, PageHeader, SectionTitle, Table } from "../../lib/ui.jsx";

const ASKED = [
  ["Embedding with business teams to document how things really work today and designing how they should work tomorrow.",
   "One process mapped twice, with volumes counted from the data and handling times stated as assumptions a time study replaces.",
   [["Process, today and after", "/process"]]],
  ["Turning business requirements into solution designs that are clear enough for anyone to build from.",
   "Eleven requirements, each traced to the test that proves it and the acceptance scenario that shows it. The policy is written once and enforced, displayed and handed to the agent from the same place.",
   [["Delivery log & UAT", "/delivery"]]],
  ["Building solutions using tools like Claude, Power BI, Azure, Databricks, and Foundry.",
   "A working build on Azure: a medallion pipeline, a star schema with SQL and DAX measures, and a tool-calling agent behind a provider-neutral interface. Written with Claude Code.",
   [["Lakehouse & lineage", "/lakehouse"], ["Self-serve reporting", "/selfserve"], ["AI triage", "/triage"]]],
  ["Owning the relationship with your stakeholders - demos, training, UAT, adoption. If nobody's using it, it doesn't count.",
   "The screen the team would actually work from, acceptance scenarios in their words, and adoption counted from the audit log rather than asserted.",
   [["Exception queue", "/exceptions"], ["Operations & adoption", "/operations"]]],
  ["Some BAU reporting/analytics, most is self-serve, ad hoc requests still occur.",
   "Published measures with one definition each, and a help desk log scored against them: what self-serve already answers, and what it cannot yet.",
   [["Self-serve reporting", "/selfserve"]]],
  ["AI assisted work - bulk processing, bespoke analytics, work only a capable AI operator with a well-maintained suite of AI capabilities can do.",
   "Every held invoice in the quarter read by an agent with tools, graded against the procedure a person would follow, failures listed one by one.",
   [["AI triage", "/triage"]]],
  ["Project delivery discipline... you keep scope, risks, issues and decisions documented as you go.",
   "A RAID log kept in the repository as the work went: seven decisions with reasons and the alternatives not chosen.",
   [["Delivery log & UAT", "/delivery"]]],
  ["A pragmatic streak. We'd rather ship something useful this week than chase a perfect solution for a month.",
   "Rules do the matching because rules are enough. The model is used only where rules run out, and four things were deliberately not built, each with the reason.",
   [["What it is worth", "/value"]]],
  ["Good instincts on AI risk.",
   "The agent cannot write, never sees a bank account, is tested against invoices that argue back, and is replaced by the runbook when it is unavailable.",
   [["AI risk", "/risk"]]],
];

const PLAN = [
  {
    when: "Days 1-30: listen, and learn what is there",
    items: [
      "Sit with finance, sales and procurement. For each team: the three tasks that eat the week, and the one they dread.",
      "Learn the existing roadmap, lakehouse and reporting estate before proposing anything; take a share of the help desk queue from the first week.",
      "Pick one process with the AI Delivery Manager. Map it as it is really done, and time it with the people who do it.",
      "Agree with its owner what better means, as a number, before anything is built.",
    ],
  },
  {
    when: "Days 31-60: ship one thing people use",
    items: [
      "A solution design short enough to be read, with requirements traced to acceptance scenarios in the team's own words.",
      "Build the smallest version that changes someone's day. Rules where rules are enough; a model where they run out.",
      "UAT with the people who will use it. Fix what they find before adding anything.",
      "Start the RAID log on day one of the build and keep it where the team can see it.",
    ],
  },
  {
    when: "Days 61-90: make it stick, then choose the next",
    items: [
      "Training in the room, a one-page guide, and a named person in the team who owns it day to day.",
      "Adoption measured weekly from usage, not from a survey. If it is not being used, find out why before building more.",
      "Turn the help desk questions that keep coming back into published measures.",
      "Bring the next two candidates to the roadmap with evidence: volume, time, risk, and what would make each not worth doing.",
    ],
  },
];

export default function Brief() {
  const { t } = useTheme();
  return (
    <>
      <PageHeader
        title="First 90 days"
        subtitle="The advertisement's own list, mapped to where each point is shown working here. Then a plan for the first ninety days - which starts by listening, because the right first initiative is the one the teams actually need, and that is not something a demo can know."
      />
      <Callout tone="neutral" title="What this is and is not">
        Built for this application, on invented data, and named for the business it was built for. It is not affiliated
        with or endorsed by Madison Group Enterprises. The distributor, its suppliers, items and invoices are synthetic;
        accounts payable was chosen because every distributor has it, not because of anything known about how Madison
        works. That is the first thing to learn.
      </Callout>
      <SectionTitle>What the role asks for, and where it is shown</SectionTitle>
      <Card>
        <Table maxHeight={900} columns={[
          { key: 0, label: "From the advertisement", wrap: true, render: (r) => <i style={{ color: t.textMuted }}>"{r[0]}"</i> },
          { key: 1, label: "Here", wrap: true, render: (r) => r[1] },
          { key: 2, label: "Open", render: (r) => (
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {r[2].map(([label, to]) => <Link key={to} to={to} style={{ color: t.accent, fontWeight: 650, fontSize: 12.5 }}>{label}</Link>)}
            </div>
          ) },
        ]} rows={ASKED} />
      </Card>

      <SectionTitle>The first ninety days</SectionTitle>
      <Grid cols={3} min={300}>
        {PLAN.map((p) => (
          <Card key={p.when} title={p.when}>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.6 }}>
              {p.items.map((i) => <li key={i} style={{ marginBottom: 6 }}>{i}</li>)}
            </ul>
          </Card>
        ))}
      </Grid>

      <SectionTitle>Questions I would ask first</SectionTitle>
      <Card>
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.7 }}>
          <li>Which initiative on the roadmap matters most to the business this quarter, and who is waiting for it?</li>
          <li>Where has an AI tool been tried already and not stuck, and what did people say about why?</li>
          <li>Which help desk questions come back every month?</li>
          <li>What is the rule today on which data may be sent to which model?</li>
          <li>What work goes to consultants now that the team would rather own?</li>
        </ul>
      </Card>
    </>
  );
}
