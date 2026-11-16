"""Read models, one per page. SQL lives here; routers stay thin."""

from __future__ import annotations

import json

from src.app.pipeline import delivery
from src.app.pipeline import reference as ref
from src.app.pipeline.cases import TOOL_NAMES
from src.app.services import db, llm
from src.settings import REPO_ROOT, settings

EVAL_STATUS = REPO_ROOT / "evals" / "status.json"

CHECKS = [
    {"id": "unreadable", "label": "Readable", "what": "The document parses into typed fields in one of the known layouts.", "held": "Keyed by a person. Never guessed."},
    {"id": "bank_details", "label": "Bank details", "what": "The remittance account on the invoice is the one on the supplier master.", "held": "Escalated. Cannot be released from the queue."},
    {"id": "duplicate", "label": "Duplicate", "what": "No earlier invoice from the supplier has the same number (ignoring punctuation, case and leading zeros), or the same order and total within 45 days.", "held": "Rejected unless the first was reversed."},
    {"id": "po_reference", "label": "Order reference", "what": "The invoice quotes a purchase order that exists, belongs to the supplier and carries every line billed.", "held": "To the budget owner, or a proposed match to the one order that fits."},
    {"id": "currency", "label": "Currency", "what": "The invoice is in the order's currency.", "held": "Returned to the supplier."},
    {"id": "arithmetic", "label": "Arithmetic", "what": "Lines add to the subtotal; subtotal, charges and tax add to the total.", "held": "Returned to the supplier."},
    {"id": "tax", "label": "Tax", "what": "Tax matches the rate the supplier's tax code implies.", "held": "Returned to the supplier."},
    {"id": "price", "label": "Price", "what": "Each unit price is within 2% of the order price, or within $5.00 on the line.", "held": "Short-paid at the order price and queried, or a price list proposed."},
    {"id": "quantity", "label": "Quantity", "what": "Nothing is billed beyond what was received.", "held": "Paid as received, or held until the goods arrive."},
    {"id": "unplanned_charge", "label": "Unplanned charge", "what": "Freight not on the order is within $60.00 and 5% of the subtotal.", "held": "To the buyer."},
]

TABLES = [
    {"name": "raw_files", "layer": "Bronze", "what": "Every file as landed: rows, bytes and SHA-256."},
    {"name": "dim_supplier", "layer": "Gold", "what": "Supplier master. Bank accounts masked."},
    {"name": "dim_item", "layer": "Gold", "what": "Item master with base unit and pack size."},
    {"name": "fact_po_line", "layer": "Gold", "what": "Purchase order lines with what has been received."},
    {"name": "fact_receipt", "layer": "Gold", "what": "Goods receipts by order line."},
    {"name": "fact_invoice", "layer": "Gold", "what": "One row per document that arrived: matched or held, and why."},
    {"name": "fact_invoice_line", "layer": "Gold", "what": "Invoice lines in the order's units, beside the order line they matched."},
    {"name": "exceptions", "layer": "Gold", "what": "Held invoices with reason and money at risk."},
    {"name": "partition_hashes", "layer": "Control", "what": "SHA-256 of every governed partition, by run."},
    {"name": "runs", "layer": "Control", "what": "Every build and reprocess: trigger, time, cost, output digest."},
    {"name": "run_stages", "layer": "Control", "what": "Rows in, out and held for each stage of each run."},
    {"name": "ablation", "layer": "Control", "what": "Each control switched off and the quarter re-run."},
    {"name": "uat_results", "layer": "Control", "what": "Acceptance scenarios and what each query returned."},
]


def eval_status() -> dict | None:
    return json.loads(EVAL_STATUS.read_text(encoding="utf-8")) if EVAL_STATUS.exists() else None


def headline() -> dict:
    r = db.rows("""SELECT count(*) AS documents, count(*) FILTER (WHERE status = 'matched') AS matched,
                          count(*) FILTER (WHERE status = 'held') AS held, sum(total_aud) AS value_aud,
                          sum(at_risk_aud) FILTER (WHERE status = 'held') AS at_risk_aud,
                          count(DISTINCT supplier_id) AS suppliers,
                          count(*) FILTER (WHERE flags LIKE '%uom_converted%') AS uom_converted,
                          count(*) FILTER (WHERE flags LIKE '%charge_accepted%') AS charge_accepted,
                          count(*) FILTER (WHERE check_id = 'unreadable') AS unreadable,
                          count(*) FILTER (WHERE po_number IS NOT NULL) AS with_order
                   FROM fact_invoice""")[0]
    r["straight_through"] = r["matched"] / r["documents"]
    r["decided"] = db.scalar("SELECT count(*) FROM exception_decisions d JOIN exceptions e USING (exception_id)")
    return r


def by_check() -> list[dict]:
    return db.rows("""SELECT check_id, count(*) AS held, round(sum(at_risk_aud), 2) AS at_risk_aud,
                             round(sum(total_aud), 2) AS invoice_value_aud FROM exceptions GROUP BY 1 ORDER BY 2 DESC""")


def proposals() -> list[dict]:
    out = db.rows("SELECT * FROM proposals ORDER BY proposal_id")
    for p in out:
        p["evidence"], p["preview"] = json.loads(p["evidence"]), json.loads(p["preview"])
    return out


def overview() -> dict:
    ev = eval_status()
    uat = db.rows("SELECT count(*) AS n, count(*) FILTER (WHERE passed) AS passed FROM uat_results")[0]
    return {
        "headline": headline(), "by_check": by_check(),
        "by_month": db.rows("""SELECT month, count(*) AS received, count(*) FILTER (WHERE status = 'matched') AS matched,
                                      count(*) FILTER (WHERE status = 'held') AS held, round(sum(total_aud)) AS value_aud
                               FROM fact_invoice GROUP BY 1 ORDER BY 1"""),
        "roadmap": delivery.load("delivery/roadmap.yaml")["initiatives"],
        "proposals": [{k: p[k] for k in ("proposal_id", "title", "status")} for p in proposals()],
        "uat": uat, "eval": ev["summary"] if ev else None, "period": ref.PERIOD_LABEL,
    }


def process() -> dict:
    return {
        "headline": headline(), "by_check": by_check(),
        "channels": db.rows("SELECT channel, layout, count(*) AS documents FROM fact_invoice GROUP BY 1, 2 ORDER BY 3 DESC"),
        "assumptions": ref.TIME_ASSUMPTIONS, "policy": ref.POLICY, "rules": ref.POLICY_RULES,
    }


def lakehouse() -> dict:
    counts = {t["name"]: db.scalar(f"SELECT count(*) FROM {t['name']}") for t in TABLES}
    latest = db.scalar("SELECT max(run_id) FROM runs")
    return {
        "files": db.rows("SELECT * FROM raw_files ORDER BY file"),
        "tables": [{**t, "rows": counts[t["name"]]} for t in TABLES],
        "stages": db.rows("SELECT * FROM run_stages WHERE run_id = ? ORDER BY seq", [latest]),
        "run": db.rows("SELECT * FROM runs WHERE run_id = ?", [latest])[0],
        "partitions": db.rows("SELECT * FROM partition_hashes ORDER BY partition"),
        "checks": CHECKS, "by_check": by_check(),
        "sample_docs": db.rows("""SELECT doc_id, supplier_name, status, check_id FROM fact_invoice
                                  WHERE doc_id IN (SELECT min(doc_id) FROM fact_invoice GROUP BY coalesce(check_id, flags))
                                  ORDER BY doc_id"""),
    }


def lineage(doc_id: str) -> dict:
    inv = db.rows("SELECT * FROM fact_invoice WHERE doc_id = ?", [doc_id])
    if not inv:
        raise ValueError(f"No document {doc_id}.")
    doc = db.rows("SELECT file, raw_row, sender, text_masked FROM documents WHERE doc_id = ?", [doc_id])[0]
    file = db.rows("SELECT * FROM raw_files WHERE file = ?", [doc["file"]])[0]
    return {"invoice": inv[0], "document": doc, "file": file,
            "lines": db.rows("SELECT * FROM fact_invoice_line WHERE doc_id = ? ORDER BY line_no", [doc_id]),
            "exception": (db.rows("SELECT * FROM exceptions WHERE doc_id = ?", [doc_id]) or [None])[0]}


def exceptions() -> dict:
    return {
        "headline": headline(), "by_check": by_check(), "checks": CHECKS, "proposals": proposals(),
        "rows": db.rows("""SELECT e.*, c.label_category, d.action AS decided_action, d.actor AS decided_by, d.decided_at
                           FROM exceptions e JOIN cases c USING (exception_id)
                           LEFT JOIN exception_decisions d USING (exception_id) ORDER BY e.at_risk_aud DESC, e.exception_id"""),
    }


def exception_detail(exception_id: str) -> dict:
    rows = db.rows("""SELECT e.*, c.world, c.label_category, c.label_action, c.label_detail
                      FROM exceptions e JOIN cases c USING (exception_id) WHERE exception_id = ?""", [exception_id])
    if not rows:
        raise ValueError(f"No held invoice {exception_id}.")
    e = rows[0]
    e["world"] = json.loads(e["world"])
    return {**lineage(e["doc_id"]), "exception": e,
            "decision": (db.rows("SELECT * FROM exception_decisions WHERE exception_id = ?", [exception_id]) or [None])[0]}


def triage_page() -> dict:
    return {
        "cases": db.rows("""SELECT e.exception_id, e.check_id, e.supplier_name, e.invoice_number, e.reason, e.at_risk_aud,
                                   c.label_category, c.label_action
                            FROM exceptions e JOIN cases c USING (exception_id) ORDER BY e.check_id, e.exception_id"""),
        "eval": eval_status(), "llm_configured": llm.configured(), "model": settings.llm_chat_model, "tools": TOOL_NAMES,
        "recent": db.rows("SELECT run_id, ts, exception_id, engine, model, ms, steps, grade FROM triage_runs ORDER BY ts DESC LIMIT 20"),
    }


def selfserve() -> dict:
    con = db.connection().cursor()
    try:
        measures = delivery.run_measures(con)
    finally:
        con.close()
    enquiries = delivery.load("semantic/enquiries.yaml")["enquiries"]
    names = {m["id"]: m["name"] for m in measures}
    schema = db.rows("""SELECT table_name, string_agg(column_name, ', ' ORDER BY ordinal_position) AS columns
                        FROM information_schema.columns WHERE table_name IN (SELECT unnest(?)) GROUP BY 1 ORDER BY 1""",
                     [[t["name"] for t in TABLES]])
    return {"measures": measures, "schema": schema,
            "enquiries": [{**e, "measure_name": names.get(e["answer"]) if e["route"] == "measure" else None} for e in enquiries],
            "by_supplier": db.rows("""SELECT supplier_name, count(*) AS invoices, round(sum(total_aud)) AS value_aud,
                                             count(*) FILTER (WHERE status = 'held') AS held
                                      FROM fact_invoice WHERE supplier_name IS NOT NULL GROUP BY 1 ORDER BY 3 DESC LIMIT 12""")}


def value() -> dict:
    return {"headline": headline(), "by_check": by_check(), "ablation": db.rows("SELECT * FROM ablation"),
            "assumptions": ref.TIME_ASSUMPTIONS, "proposals": proposals(), "eval": (eval_status() or {}).get("summary")}


def risk() -> dict:
    sample = db.rows("""SELECT c.world FROM cases c JOIN exceptions e USING (exception_id)
                        WHERE e.check_id = 'bank_details' ORDER BY exception_id LIMIT 1""")
    world = json.loads(sample[0]["world"]) if sample else {}
    ev = eval_status()
    adversarial = [r for r in (ev or {}).get("results", []) if r["kind"] == "adversarial"]
    return {
        "risks": delivery.load("delivery/raid.yaml")["risks"],
        "decisions": [d for d in delivery.load("delivery/raid.yaml")["decisions"] if d["id"] in ("D-01", "D-02", "D-03", "D-05")],
        "sent_to_model": {k: sorted(v.keys()) if isinstance(v, dict) else None for k, v in world.items()},
        "masked_example": {"invoice_shows": world.get("get_invoice", {}).get("remittance_account_masked"),
                           "on_file": world.get("get_supplier", {}).get("bank_on_file_masked"),
                           "matches": world.get("get_invoice", {}).get("remittance_account_matches_master")},
        "snapshots": db.scalar("SELECT count(*) FROM cases"),
        "snapshots_with_account_numbers": db.scalar("SELECT count(*) FROM cases WHERE regexp_matches(world, '[0-9]{8}')"),
        "adversarial": adversarial, "eval_summary": ev["summary"] if ev else None,
        "limits": {"per_address": settings.triage_rate_limit_per_ip, "global": settings.triage_rate_limit_global,
                   "window_seconds": settings.rate_limit_window_seconds, "timeout_seconds": settings.llm_timeout_seconds},
        "llm_configured": llm.configured(), "model": settings.llm_chat_model if llm.configured() else None,
    }


def delivery_page() -> dict:
    raid = delivery.load("delivery/raid.yaml")
    return {"requirements": delivery.load("delivery/requirements.yaml")["requirements"],
            "uat": db.rows("SELECT * FROM uat_results ORDER BY id"), **raid}


def operations(timings: list[dict]) -> dict:
    return {
        "runs": db.rows("SELECT * FROM runs ORDER BY run_id DESC"),
        "audit": db.rows("SELECT * FROM audit_log ORDER BY ts DESC LIMIT 50"),
        "timings": timings,
        "usage": {"decisions": db.scalar("SELECT count(*) FROM exception_decisions"),
                  "triage_runs": db.scalar("SELECT count(*) FROM triage_runs"),
                  "refused_writes": db.scalar("SELECT count(*) FROM audit_log WHERE outcome = 'refused'"),
                  "audit_entries": db.scalar("SELECT count(*) FROM audit_log")},
        "build_seconds": db.kv("build_seconds"), "uat": db.rows("SELECT id, passed FROM uat_results ORDER BY id"),
        "eval": {k: (eval_status() or {}).get(k) for k in ("run_at", "model", "cases")},
    }


def meta_counts() -> dict:
    h = headline()
    return {"documents": h["documents"], "held": h["held"], "tables": len(TABLES)}
