# Madison - AI solutions workbench

**One business process, taken from discovery to adoption.** A distributor's
accounts payable: mapped as it is done today, rebuilt as a three-way match
over a small lakehouse, with an AI agent drafting the first read of every
invoice the match holds - and that agent graded against the procedure a
person would follow, including on invoices written to fool it.

> **Built for a job application to Madison Group Enterprises (AI Solutions
> Analyst). Not affiliated with or endorsed by Madison Group Enterprises.**
> **All data is synthetic.** The distributor, its suppliers, items, orders and
> invoices are invented and generated from a seed by
> `backend/src/app/pipeline/generate.py`. Accounts payable was chosen because
> every distributor has it, not because of anything known about how Madison
> works. The logo, favicon and colours are Madison Group's own, taken from
> their public website, and are used only to show what the work would look
> like in their hands.

## What it shows

| | |
|---|---|
| **Discovery** | The process mapped twice, today and after, with the volume at each step counted from the data. Handling times are stated as what they are - assumptions - and are editable on the page. |
| **Design** | Eleven requirements, each naming the test that proves it; the suite fails if that test does not exist. Ten acceptance scenarios in the words of the people who would sign off, each run as a query on every build. A RAID log with seven decisions, their reasons and what was not chosen. |
| **Build: data** | ERP extracts and an invoice inbox in three supplier layouts: 1,353 invoices worth $26.0M from 36 suppliers in one quarter. Seven timed stages to a star schema; every row traceable to its file and line; a re-run from raw proved identical by digests. |
| **Build: the match** | Ten checks in a fixed order. 86.7% of invoices match with nobody touching them; 180 are held, each with its reason and the money at risk. Hold, never guess; nothing is dropped. |
| **Build: AI** | A tool-calling agent (seven tools over a frozen snapshot) that submits a typed proposal with evidence. Graded against the AP runbook on 35 labelled cases: 26 ordinary, six where the check's name points at the wrong answer, three where the invoice text tries to talk its way to payment. It proposes; it cannot write. |
| **Self-serve** | Nine published measures, each with the SQL that runs here and the DAX for a Power BI model over the same tables. A help desk log scored against them, and read-only SQL behind a validator. |
| **What it is worth** | Every control switched off in turn and the quarter re-run: $540,465 that would have been paid in error, $199,824 released without approval, 85 false holds avoided. One finding nobody asked for: a supplier price notice never loaded, behind 31 of the held invoices. |
| **AI risk** | The agent cannot write, never sees a bank account number, treats invoice text as data, and is replaced by the runbook when the model is unavailable - each one a control with a test or a query behind it. |
| **Adoption** | The queue the team would work from, with decisions recorded once under a name and refused when policy says no. Usage counted from the audit log. |

## Pages

AI roadmap · Process, today and after · Lakehouse & lineage · Exception queue ·
AI triage · Self-serve reporting · What it is worth · AI risk ·
Delivery log & UAT · Operations & adoption · First 90 days.

## Architecture

```
  raw/ erp/*.csv   ap_inbox/*.jsonl          scripts/build_platform.py (in the image build)
        │ hashed on landing (bronze)          generate -> match -> ablation -> proposals
        ▼                                     -> acceptance scenarios -> verify against
  ┌────────────── pipeline ───────────────┐      infra-azure/build.sha256
  │ land · parse · conform · units ·      │
  │ match · checks · publish              │──► exceptions (every hold, with its reason
  └──────────────┬────────────────────────┘    and the money at risk)
                 ▼                          ──► partition digests (the re-run contract)
  star schema: dim_supplier, dim_item, fact_po_line,
  fact_receipt, fact_invoice, fact_invoice_line (gold)
                 ▼
  DuckDB (one file) ◄── FastAPI ◄── nginx ◄── React SPA
     ▲                     │
     │ an approved rule    │ triage agent ──► any OpenAI-protocol model, a fallback
     └─ change reprocesses ┘                  model, then the runbook - said on screen
        from raw
```

The match is deterministic rules; the model only reads exceptions. Most
invoices agree with their order, and rules clear those for nothing, the same
way every time. `delivery/raid.yaml` records that decision and six others.

At this size the lakehouse is DuckDB in one file. The same stages are a
medallion pipeline in Databricks when the data stops fitting in memory, and
with real supplier data the model would be one deployed in the organisation's
own tenancy (Azure AI Foundry) rather than a public endpoint. The agent code
depends on the protocol, not the provider.

## Run it

Needs [uv](https://docs.astral.sh/uv/) and Node 20.

```bash
cd backend
uv sync
uv run python ../scripts/build_platform.py     # about 2 s; verifies against the pinned manifest
cp ../.env.example ../.env                      # model key optional; DEMO_WRITE_TOKEN for decisions
uv run uvicorn src.main:app --port 8051

cd ../frontend
npm install
npm run dev                                     # http://localhost:5251
```

Open `http://localhost:5251/?write_token=<DEMO_WRITE_TOKEN>` once to unlock
decisions and approvals in that browser session. The plain link is read-only,
and the server says why it refuses.

## Checks

```bash
cd backend
uv run pytest                                   # pipeline, workflow rules, guards, delivery record
uv run python ../evals/run_triage_eval.py       # agent + runbook, graded; writes evals/status.json
uv run python ../evals/run_triage_eval.py --rules     # runbook only, no model key needed

cd ../frontend
npx playwright install chromium                 # once
node evals/check-pages.mjs                      # every page, desktop and phone
TOKEN=<DEMO_WRITE_TOKEN> node evals/flow.mjs    # the operator's path, end to end
```

The committed `evals/status.json` holds the runbook's results. The agent's
column on the AI triage page fills in when the eval is run with a model key;
until then the page says the agent has not been graded, rather than implying
it has.

Changing the generator or the pipeline changes the output: rebuild with
`--write-manifest` and commit `infra-azure/build.sha256`.

## Deploy

Every push to `main` runs the checks, then builds both images and publishes
them to GitHub Container Registry (`.github/workflows/ci.yml`), tagged with
the short commit SHA. A commit whose build does not match the pinned manifest
fails there and is never published. After the first run, set both packages to
public in the repository's package settings; the app then pulls with no
credential. CI holds no cloud credential: deploying is a separate, deliberate
step.

```bash
cd infra-azure
cp terraform.tfvars.example terraform.tfvars    # subscription, alert e-mail, model key (gitignored)
terraform init
terraform apply -var "image_tag=$(git rev-parse --short HEAD)"
terraform output                                # the URL; -raw demo_write_token for the unlock link
```

Terraform runs wherever you are signed in to Azure: a laptop, or Azure Cloud
Shell with the repository cloned. State is local, so keep the state file.

### What it costs

Built to cost nothing while nobody is looking at it.

| Resource | Why it is free at rest |
|---|---|
| Resource group `rg-madison-ai` | Holds everything and nothing else. Deleting it removes the deployment. |
| Container Apps, consumption plan | Scales to zero; the monthly free grant covers a demo's traffic. One replica at most. |
| Log Analytics workspace | Daily cap of 0.05 GB, inside the free allowance. |
| Budget alert | A tripwire at $3 a month. Budgets are free. |

There is no database server, no storage account, no private registry and no
vault. The data is built inside the image; the images are public on GitHub;
the two secrets are Container Apps secrets.

To remove everything: `terraform destroy`, or delete the resource group.

A subscription may allow only two Container Apps environments in total. When
both are taken, set `existing_environment_id` in `terraform.tfvars` to one of
them: the app, its secrets and its budget still live in `rg-madison-ai` and
are removed with it, and no workspace is created (the shared environment logs
to its own). The live demo runs this way.
