"""The pipeline finds every seeded defect from the data, holds nothing clean,
loses nothing, and produces the same output from the same raw files."""

from __future__ import annotations

from collections import Counter

import pytest

from src.app.pipeline import reference as ref
from src.app.pipeline.ablation import run_ablation
from src.app.pipeline.parse import ParseError, normalise_number, parse_invoice
from src.app.pipeline.stages import run_pipeline
from tests.conftest import RAW

pytestmark = pytest.mark.needs_build

CHECK_FOR = {
    "duplicate": "duplicate", "price_variance": "price", "new_price_list": "price", "short_delivery": "quantity",
    "receipt_pending": "quantity", "unplanned_charge": "unplanned_charge", "tax_error": "tax",
    "arithmetic_error": "arithmetic", "currency_mismatch": "currency", "no_po": "po_reference",
    "po_reference_error": "po_reference", "bank_detail_change": "bank_details", "unreadable": "unreadable",
}


def _held(result):
    inv = result.tables["fact_invoice"]
    return dict(zip(inv.loc[inv["status"] == "held", "doc_id"], inv.loc[inv["status"] == "held", "check_id"]))


def test_every_document_is_accounted_for(governed):
    landed = int(governed.files.loc[governed.files["file"].str.startswith("ap_inbox/"), "rows"].sum())
    inv = governed.tables["fact_invoice"]
    assert len(inv) == landed
    assert inv["doc_id"].is_unique
    assert set(inv["status"]) == {"matched", "held"}
    assert (inv["status"] == "held").sum() == len(governed.tables["exceptions"])


def test_every_seeded_defect_is_found_from_the_data(governed, seeded_exceptions):
    held = _held(governed)
    missed = {doc: defect for doc, defect in seeded_exceptions.items() if held.get(doc) != CHECK_FOR[defect]}
    assert not missed
    seeded = Counter(seeded_exceptions.values())
    for defect, n in ref.DEFECTS.items():
        if n is not None and defect in CHECK_FOR:
            assert seeded[defect] == n, defect
    assert seeded["new_price_list"] >= 10


def test_nothing_clean_is_held(governed, seeded_exceptions):
    assert set(_held(governed)) == set(seeded_exceptions)


def test_resent_invoices_are_caught_under_any_formatting(governed, truth):
    assert normalise_number("QUO-004512") == normalise_number("quo 4512") == normalise_number("QUO004512") == "QUO4512"
    assert normalise_number("QUO-004512") != normalise_number("QUO-004513")
    dups = [doc for doc, (defect, _) in truth.items() if defect == "duplicate"]
    held = _held(governed)
    assert all(held[d] == "duplicate" for d in dups)
    rekeyed = [doc for doc, (defect, detail) in truth.items() if defect == "duplicate" and "new number" in detail]
    assert len(rekeyed) == ref.DUPLICATE_REKEYED


def test_pack_billing_matches_without_a_hold(governed, truth):
    inv = governed.tables["fact_invoice"].set_index("doc_id")
    packs = [doc for doc, (defect, _) in truth.items() if defect == "uom_pack_billing"]
    assert len(packs) == ref.DEFECTS["uom_pack_billing"]
    assert all(inv.loc[d, "status"] == "matched" and "uom_converted" in inv.loc[d, "flags"] for d in packs)
    # Without the conversion the same invoices are held: the control is doing the work.
    off = _held(run_pipeline(RAW, controls={"uom_normalise": False}, hash_files=False))
    assert all(off.get(d) == "price" for d in packs)


def test_freight_inside_policy_is_accepted(governed, truth):
    inv = governed.tables["fact_invoice"].set_index("doc_id")
    inside = [doc for doc, (defect, _) in truth.items() if defect == "charge_within_policy"]
    assert all(inv.loc[d, "status"] == "matched" and "charge_accepted" in inv.loc[d, "flags"] for d in inside)


def test_the_unloaded_price_list_is_one_supplier_at_one_percentage(governed, truth):
    docs = {doc for doc, (defect, _) in truth.items() if defect == "new_price_list"}
    lines = governed.tables["fact_invoice_line"]
    var = lines.loc[lines["doc_id"].isin(docs), "price_variance_pct"]
    assert ((var - ref.PRICE_LIST_UPLIFT_PCT / 100).abs() < 0.0006).all()
    after = _held(run_pipeline(RAW, approved_notices={ref.PRICE_LIST_NOTICE_ID}, hash_files=False))
    assert not docs & set(after)
    assert set(after) == set(_held(governed)) - docs


def test_rerun_from_raw_is_identical(governed):
    again = run_pipeline(RAW)
    a = dict(zip(governed.partition_hashes["partition"], governed.partition_hashes["sha256"]))
    b = dict(zip(again.partition_hashes["partition"], again.partition_hashes["sha256"]))
    assert a == b and len(a) == 13


def test_bank_accounts_are_masked_in_the_governed_tables(governed):
    full = {s["account"] for s in governed.suppliers.values()}
    for name, df in governed.tables.items():
        text = df.to_csv(index=False)
        assert not any(acct in text for acct in full), name


def test_each_control_off_releases_exactly_what_it_was_holding(governed):
    ab = run_ablation(RAW, governed).set_index("control")
    by_check = governed.tables["exceptions"].groupby("check_id").size()
    for check in ("duplicate", "price", "quantity", "tax", "arithmetic", "currency", "bank_details", "po_reference",
                  "unplanned_charge"):
        assert ab.loc[check, "released"] == by_check[check], check
        assert ab.loc[check, "extra_holds"] == 0
    assert ab.loc["uom_normalise", "extra_holds"] == ref.DEFECTS["uom_pack_billing"]
    assert ab.loc["charge_tolerance", "extra_holds"] == ref.DEFECTS["charge_within_policy"]
    assert ab.loc["duplicate", "amount_aud"] > 0


def test_the_parser_refuses_rather_than_guesses():
    with pytest.raises(ParseError):
        parse_invoice("[scanned image - no text layer]\n#%&@")
    with pytest.raises(ParseError):
        parse_invoice("DOCUMENT=INVOICE\nSUPPLIER=X\nINVOICE_NUMBER=1")
