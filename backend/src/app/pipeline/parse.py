"""Read a supplier invoice out of its text, whichever of the three layouts it
arrived in. Deterministic and strict: a document that does not parse cleanly
raises, and the pipeline holds it for a person. It never guesses a field.
"""

from __future__ import annotations

import re
from datetime import date, datetime


class ParseError(ValueError):
    pass


def _money(s: str) -> float:
    return round(float(s), 2)


def _line(parts: list[str]) -> dict:
    if len(parts) != 7:
        raise ParseError(f"line has {len(parts)} fields, expected 7")
    return {"line_no": int(parts[0]), "item_id": "" if parts[1] in ("-", "") else parts[1], "description": parts[2],
            "qty": float(parts[3]), "uom": parts[4], "unit_price": float(parts[5]), "amount": _money(parts[6])}


def _layout_a(rows: list[str]) -> dict:
    out: dict = {"layout": "A", "lines": [], "charge": 0.0, "notes": ""}
    out["supplier_name"] = rows[1].split("  ABN ")[0].strip()
    m = re.match(r"Invoice No: (.+?)\s{2,}Invoice Date: (\d{2})/(\d{2})/(\d{4})$", rows[2])
    if not m:
        raise ParseError("no invoice number and date")
    out["invoice_number"] = m.group(1).strip()
    out["invoice_date"] = date(int(m.group(4)), int(m.group(3)), int(m.group(2)))
    in_table = False
    for row in rows[3:]:
        if row.startswith("Ln  Item"):
            in_table = True
        elif row.startswith("Subtotal:"):
            in_table = False
            out["subtotal"] = _money(row.split(":", 1)[1])
        elif in_table and row.strip():
            out["lines"].append(_line(re.split(r"\s{2,}", row.strip())))
        elif row.startswith("PO Ref:"):
            m = re.match(r"PO Ref:\s*(.*?)\s{2,}Terms:", row)
            out["po_number"] = m.group(1).strip() if m else ""
        elif row.startswith("Currency:"):
            out["currency"] = row.split(":", 1)[1].strip()
        elif row.startswith("Freight:"):
            out["charge"] = _money(row.split(":", 1)[1])
        elif row.startswith("GST:"):
            out["tax"] = _money(row.split(":", 1)[1])
        elif row.startswith("Total:"):
            out["total"] = _money(row.split(":", 1)[1])
        elif row.startswith("Remit To:"):
            m = re.match(r"Remit To: BSB (\S+)\s+Account (\S+)$", row)
            if m:
                out["bsb"], out["account"] = m.group(1), m.group(2)
        elif row.startswith("Notes:"):
            out["notes"] = row.split(":", 1)[1].strip()
    return out


def _layout_b(rows: list[str]) -> dict:
    out: dict = {"layout": "B", "lines": [], "charge": 0.0, "notes": ""}
    for row in rows:
        key, _, val = row.partition("=")
        if key == "SUPPLIER":
            out["supplier_name"] = val
        elif key == "INVOICE_NUMBER":
            out["invoice_number"] = val
        elif key == "INVOICE_DATE":
            out["invoice_date"] = date.fromisoformat(val)
        elif key == "PURCHASE_ORDER":
            out["po_number"] = val
        elif key == "CURRENCY":
            out["currency"] = val
        elif key == "LINE":
            out["lines"].append(_line(val.split(";")))
        elif key == "SUBTOTAL":
            out["subtotal"] = _money(val)
        elif key == "CHARGE":
            out["charge"] = _money(val.split(";")[1])
        elif key == "TAX":
            out["tax"] = _money(val)
        elif key == "TOTAL":
            out["total"] = _money(val)
        elif key == "BANK":
            out["bsb"], _, out["account"] = val.partition("/")
        elif key == "NOTE":
            out["notes"] = val
    return out


def _layout_c(rows: list[str]) -> dict:
    out: dict = {"layout": "C", "lines": [], "charge": 0.0, "notes": ""}
    for row in rows:
        seg = row.split("|")
        if seg[0] == "HDR":
            out["invoice_number"], out["po_number"], out["currency"] = seg[2], seg[4], seg[5]
            out["invoice_date"] = datetime.strptime(seg[3], "%Y%m%d").date()
        elif seg[0] == "SUP":
            out["supplier_name"] = seg[2]
        elif seg[0] == "LIN":
            out["lines"].append(_line(seg[1:]))
        elif seg[0] == "CHG":
            out["charge"] = _money(seg[2])
        elif seg[0] == "TAX":
            out["tax"] = _money(seg[1])
        elif seg[0] == "TOT":
            out["subtotal"], out["total"] = _money(seg[1]), _money(seg[2])
        elif seg[0] == "PAY":
            out["bsb"], out["account"] = seg[1], seg[2]
        elif seg[0] == "TXT":
            out["notes"] = "|".join(seg[1:])
    return out


REQUIRED = ("supplier_name", "invoice_number", "invoice_date", "currency", "subtotal", "tax", "total", "bsb", "account")


def parse_invoice(text: str) -> dict:
    rows = text.split("\n")
    try:
        if rows[0] == "TAX INVOICE":
            out = _layout_a(rows)
        elif rows[0] == "DOCUMENT=INVOICE":
            out = _layout_b(rows)
        elif rows[0].startswith("HDR|INV|"):
            out = _layout_c(rows)
        else:
            raise ParseError("no text layer, or a layout this parser does not know")
    except (IndexError, ValueError) as exc:
        if isinstance(exc, ParseError):
            raise
        raise ParseError(f"malformed document: {exc}") from exc
    missing = [k for k in REQUIRED if k not in out]
    if missing or not out["lines"]:
        raise ParseError(f"missing {', '.join(missing) or 'line items'}")
    out["po_number"] = out.get("po_number") or None
    return out


def normalise_number(number: str) -> str:
    """Invoice numbers compared the way a person would: case, punctuation and
    leading zeros do not make a different invoice."""
    s = re.sub(r"[^A-Z0-9]", "", number.upper())
    return re.sub(r"(?<![0-9])0+(?=[0-9])", "", s)
