# madison-ai-solutions

Portfolio demo: one business process taken from discovery to adoption for a
distributor - accounts payable, mapped as it is done today, rebuilt as a
three-way match over a small lakehouse, with an AI agent drafting the first
read of every invoice the match holds, graded against the AP runbook. Built
for an application to Madison Group Enterprises (AI Solutions Analyst) and
named for it. **Not affiliated with or endorsed by Madison Group Enterprises.
All data is synthetic.**

## Layout

```
madison-ai-solutions/
├── backend/           FastAPI + Python 3.12 (uv)
│   └── src/app/
│       ├── pipeline/  reference, generate, parse, stages, cases, ablation,
│       │              registry, delivery, persist (the build and reprocessing)
│       ├── services/  analytics (reads), workflow (governed writes), replay, triage,
│       │              triage_cases, llm, db, auth, rate_limit, sql_validator, timings
│       └── routers/   pages (reads), workflow (token-gated), actions (re-run, triage, query)
├── delivery/          roadmap, requirements, RAID log, UAT scenarios (YAML, rendered and executed)
├── semantic/          published measures (SQL + DAX) and the help desk enquiry log
├── scripts/           build_platform.py - everything from nothing
├── evals/             run_triage_eval.py -> status.json (shown on the AI triage page)
├── frontend/          React 18 + Vite; pages/<Section>/<Page>.jsx auto-discovered
└── infra-azure/       Terraform; build.sha256 is the pinned manifest
```

## How to run

```bash
cd backend && uv sync && uv run python ../scripts/build_platform.py && uv run uvicorn src.main:app --port 8051
cd frontend && npm install && npm run dev     # :5251
```

Tests: `cd backend && uv run pytest`. Pages: `cd frontend && node evals/check-pages.mjs`.
Operator path: `TOKEN=<DEMO_WRITE_TOKEN> node evals/flow.mjs`.

## Conventions

- **No emojis in code or output.** Australian English; dates DD/MM/YYYY on screen;
  straight quotes and hyphens only (the page check fails on typographic ones).
- **Personal identity only.** Commits, CI, registry, README and infrastructure use
  the author's personal accounts. No employer name, work e-mail, work machine path
  or internal system appears anywhere in this repository.
- Every defect the generator seeds is declared once in `pipeline/reference.py`;
  tests assert each is found from the data. The pipeline never reads the truth file.
- Hold, never guess: a check that cannot decide holds the invoice and records why.
  Every document that arrives is in `fact_invoice`.
- Every write is token-gated, audit-logged, and refused - not warned - when the
  rule says no. The proposer of a change cannot approve it. The agent proposes;
  it cannot write, and it never sees a bank account number.
- Numbers on screen come from the data. Handling times are assumptions and are
  labelled as such wherever they appear.
- A requirement names the test that proves it; `tests/test_delivery.py` fails if
  that test does not exist. A UAT scenario is a query, run on every build.
- Changing the generator or the pipeline changes the output: rebuild with
  `--write-manifest` and commit `infra-azure/build.sha256`, or CI and the image
  build fail.
- Azure: one resource group, scale to zero, no registry, no vault, no database.
  Do not add a resource that costs money at rest.
- Named for the business it was built for, and says so: the not-affiliated line
  stays in the sidebar, the First 90 days page and the README. It uses Madison
  Group's public logo, favicon and palette (Owen's call, 17/11/2026), so that
  line must never be removed or made less visible. Nothing claims to know how
  they operate.
