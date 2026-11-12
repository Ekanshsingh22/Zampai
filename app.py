
import os
import re
import io
import json
import time
import csv
import difflib
from pathlib import Path
from datetime import datetime

import psycopg
from psycopg.rows import dict_row
import pdfplumber

from flask import Flask, request, Response, jsonify, send_file

app = Flask(__name__)
TOL = 0.02

# Absolute path to the project folder
BASE_DIR = Path(__file__).resolve().parent


# ---------------- DATABASE ----------------

def db():
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is missing")

    c = psycopg.connect(database_url, row_factory=dict_row)

    c.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id BIGSERIAL PRIMARY KEY,
            ts TEXT,
            file TEXT,
            vendor TEXT,
            inv_no TEXT,
            total DOUBLE PRECISION,
            po TEXT,
            decision TEXT,
            reason TEXT,
            stages TEXT
        )
    """)

    c.commit()
    return c


# ---------------- FILE HELPERS ----------------

def load(filename):
    path = BASE_DIR / filename
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_pdf(data):
    with pdfplumber.open(io.BytesIO(data)) as p:
        return "\n".join(
            (page.extract_text() or "") for page in p.pages
        )


# ---------------- INVOICE PARSING ----------------

M = r'\$?\s*([\d,]+\.\d{2})'


def money(lines, pattern):
    for line in lines:
        match = re.match(
            rf'\s*(?:{pattern})\b[^\n]*?{M}',
            line,
            re.I
        )
        if match:
            return float(match.group(1).replace(",", ""))


def parse(text):
    lines = [x for x in text.splitlines() if x.strip()]

    def get(pattern):
        match = re.search(pattern, text, re.I)
        return match.group(1).strip() if match else None

    return {
        "vendor_raw": lines[0].strip() if lines else None,
        "inv_no": get(
            r'(?:invoice\s*(?:no\.?|number|#)|inv\s*#)[ \t]*[:\-]?[ \t]*([A-Z0-9][A-Z0-9\-/]{2,})'
        ),
        "date": get(
            r'\bdate[ \t]*[:\-]?[ \t]*(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})'
        ),
        "po": get(r'\b(PO-\d+)\b'),
        "sub": money(lines, 'subtotal|net amount'),
        "tax": money(lines, 'tax|vat|gst'),
        "total": money(lines, 'grand total|total due|amount due|total')
    }


# ---------------- OPTIONAL AI FALLBACK ----------------

def llm_fill(text, fields):
    import requests

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        timeout=30,
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01"
        },
        json={
            "model": "claude-sonnet-5-5",
            "max_tokens": 300,
            "messages": [{
                "role": "user",
                "content":
                "Extract invoice number, date and total as JSON. "
                "Use null if absent; never guess.\n" + text
            }]
        }
    )

    response.raise_for_status()

    result = json.loads(
        re.search(
            r'\{.*\}',
            response.json()["content"][0]["text"],
            re.S
        ).group(0)
    )

    for key in ("inv_no", "date", "total"):
        fields[key] = fields[key] or result.get(key)

    return fields


# ---------------- INVOICE PROCESSING ----------------

def run(filename, data):
    stages = []
    context = {}

    def S(name, status, detail):
        stages.append({
            "stage": name,
            "status": status,
            "detail": detail
        })
        time.sleep(0.45)
        return json.dumps(stages[-1]) + "\n"

    def F(decision, reason):
        with db() as c:
            c.execute(
                """
                INSERT INTO runs
                (ts, file, vendor, inv_no, total, po,
                 decision, reason, stages)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    filename,
                    context.get("vendor"),
                    context.get("inv_no"),
                    context.get("total"),
                    context.get("po"),
                    decision,
                    reason,
                    json.dumps(stages)
                )
            )

        return json.dumps({
            "done": True,
            "decision": decision,
            "reason": reason,
            "fields": context
        }) + "\n"

    yield S("1. Ingest", "ok",
            f"{filename} ({len(data)//1024+1} KB)")

    try:
        text = read_pdf(data)
    except Exception as e:
        yield S("2. Extract text", "fail", str(e))
        yield F("REVIEW", "Unreadable file.")
        return

    if len(text.strip()) < 20:
        yield S("2. Extract text", "warn",
                "No text layer - scanned image, OCR required")
        yield F(
            "REVIEW",
            "Scanned invoice with no machine-readable text; "
            "routed to manual review / OCR queue."
        )
        return

    yield S("2. Extract text", "ok",
            f"{len(text)} characters read")

    fields = parse(text)

    if os.getenv("ANTHROPIC_API_KEY") and not all(
        fields[k] for k in ("inv_no", "date", "total")
    ):
        try:
            fields = llm_fill(text, fields)
            yield S("2b. AI fallback", "ok",
                    "LLM attempted to fill missing fields")
        except Exception as e:
            yield S("2b. AI fallback", "warn", f"skipped: {e}")

    vendors = load("data/vendors.csv")
    purchase_orders = load("data/pos.csv")

    matches = difflib.get_close_matches(
        fields["vendor_raw"] or "",
        [v["name"] for v in vendors],
        1,
        0.8
    )

    vendor = matches[0] if matches else fields["vendor_raw"]

    context.update(
        vendor=vendor,
        inv_no=fields["inv_no"],
        total=fields["total"],
        po=fields["po"],
        date=fields["date"]
    )

    yield S(
        "3. Parse fields", "ok",
        f"vendor={vendor} | invoice#={fields['inv_no']} | "
        f"date={fields['date']} | PO={fields['po']} | "
        f"total={fields['total']}"
    )

    missing = [
        k for k in ("inv_no", "date", "total")
        if not fields[k]
    ]

    if missing:
        yield S("4. Completeness", "fail",
                "Missing: " + ", ".join(missing))
        yield F(
            "HOLD",
            "Missing " + ", ".join(missing) +
            ". Returned to vendor for a corrected invoice."
        )
        return

    yield S("4. Completeness", "ok",
            "Invoice number, date and total present")

    if (
        fields["sub"] is not None
        and fields["tax"] is not None
        and abs(fields["sub"] + fields["tax"] - fields["total"]) > 0.01
    ):
        yield S("5. Arithmetic", "fail",
                "Subtotal + tax != total")
        yield F("REVIEW", "Subtotal + tax does not equal total.")
        return

    yield S("5. Arithmetic", "ok",
            "Subtotal + tax = total")

    vendor_record = next(
        (v for v in vendors if v["name"] == vendor),
        None
    )

    if not vendor_record:
        yield S("6. Vendor check", "fail",
                f"'{vendor}' not in vendor master")
        yield F("REVIEW", "Unknown vendor - needs onboarding check.")
        return

    if vendor_record["status"] != "approved":
        yield S("6. Vendor check", "fail",
                f"{vendor} is {vendor_record['status']}")
        yield F(
            "REJECTED",
            f"Vendor is {vendor_record['status']}; invoice rejected."
        )
        return

    yield S("6. Vendor check", "ok",
            f"{vendor} is an approved vendor")

    with db() as c:
        duplicate = c.execute(
            """
            SELECT id, ts FROM runs
            WHERE vendor=%s AND inv_no=%s
            AND decision IN ('APPROVED','REVIEW')
            """,
            (vendor, fields["inv_no"])
        ).fetchone()

    if duplicate:
        yield S(
            "7. Duplicate check", "fail",
            f"Invoice {fields['inv_no']} already processed "
            f"in run #{duplicate['id']} ({duplicate['ts']})"
        )
        yield F("REJECTED", f"Duplicate of run #{duplicate['id']}.")
        return

    yield S("7. Duplicate check", "ok",
            "No prior invoice with same vendor + number")

    note = ""

    if fields["po"]:
        row = next(
            (p for p in purchase_orders if p["po"] == fields["po"]),
            None
        )

        if not row:
            yield S("8. PO match", "fail",
                    f"{fields['po']} not found")
            yield F("REVIEW", "Referenced PO does not exist.")
            return

        if row["vendor"] != vendor:
            yield S("8. PO match", "fail",
                    f"{fields['po']} belongs to {row['vendor']}")
            yield F("REVIEW", "PO belongs to a different vendor.")
            return

    else:
        candidates = [
            p for p in purchase_orders if p["vendor"] == vendor
        ]

        if len(candidates) != 1:
            yield S("8. PO match", "fail",
                    f"No PO ref and {len(candidates)} candidate POs")
            yield F("REVIEW", "Cannot determine PO.")
            return

        row = candidates[0]
        note = " (PO inferred - only open PO for vendor)"

    context["po"] = row["po"]
    amount = float(row["amount"])

    with db() as c:
        billed_result = c.execute(
            """
            SELECT COALESCE(SUM(total), 0) AS billed
            FROM runs
            WHERE po=%s AND decision='APPROVED'
            """,
            (row["po"],)
        ).fetchone()

    billed = float(billed_result["billed"] or 0)
    total = float(fields["total"])

    yield S(
        "8. PO match", "ok",
        f"{row['po']} (amount {amount:,.2f}, "
        f"already billed {billed:,.2f}){note}"
    )

    over = billed + total - amount

    if over <= 0.005:
        kind = (
            "partial billing"
            if billed + total < amount - 0.005
            else "PO fully billed"
        )

        yield S(
            "9. Amount check", "ok",
            f"{total:,.2f} fits remaining {amount-billed:,.2f} "
            f"({kind})"
        )

        yield F(
            "APPROVED",
            f"Matches {row['po']}; {kind}. "
            f"Cumulative {billed+total:,.2f} of {amount:,.2f}.{note}"
        )

    elif over / amount <= TOL:
        yield S(
            "9. Amount check", "warn",
            f"Over PO by {over:,.2f} ({over/amount:.2%}) "
            f"- within {TOL:.0%} tolerance"
        )

        yield F(
            "APPROVED",
            f"Approved within tolerance: "
            f"{over/amount:.2%} over {row['po']}.{note}"
        )

    else:
        yield S(
            "9. Amount check", "fail",
            f"Over PO by {over:,.2f} ({over/amount:.1%}) "
            f"- exceeds {TOL:.0%} tolerance"
        )

        yield F(
            "REVIEW",
            f"Cumulative billing exceeds {row['po']} "
            f"by {over:,.2f} ({over/amount:.1%}); "
            "escalated to buyer."
        )


# ---------------- FLASK ROUTES ----------------

@app.route("/")
def index():
    return send_file(str(BASE_DIR / "index.html"))


@app.route("/samples")
def samples():
    folder = BASE_DIR / "samples"
    return jsonify(sorted(
        p.name for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() == ".pdf"
    ))


@app.route("/run", methods=["POST"])
def run_():
    if request.form.get("sample"):
        filename = os.path.basename(request.form["sample"])
        path = BASE_DIR / "samples" / filename

        if not path.is_file():
            return jsonify(error="Sample not found"), 404

        data = path.read_bytes()

    else:
        uploaded = request.files.get("file")

        if not uploaded or not uploaded.filename:
            return jsonify(error="No invoice uploaded"), 400

        filename = os.path.basename(uploaded.filename)
        data = uploaded.read()

    return Response(
        run(filename, data),
        mimetype="application/x-ndjson"
    )


@app.route("/api/runs")
def runs():
    with db() as c:
        records = c.execute(
            "SELECT * FROM runs ORDER BY id DESC"
        ).fetchall()

    return jsonify(records)


@app.route("/api/pos")
def pos():
    purchase_orders = load("data/pos.csv")
    results = []

    with db() as c:
        for p in purchase_orders:
            result = c.execute(
                """
                SELECT COALESCE(SUM(total), 0) AS billed
                FROM runs
                WHERE po=%s AND decision='APPROVED'
                """,
                (p["po"],)
            ).fetchone()

            results.append({
                **p,
                "billed": float(result["billed"] or 0)
            })

    return jsonify(results)


@app.route("/api/reset", methods=["POST"])
def reset():
    # Protect destructive reset operation
    token = os.getenv("ADMIN_TOKEN")

    if not token or request.headers.get("X-Admin-Token") != token:
        return jsonify(error="Not authorized"), 403

    with db() as c:
        c.execute("TRUNCATE TABLE runs RESTART IDENTITY")

    return "ok"


if __name__ == "__main__":
    app.run(port=5000, threaded=True)
