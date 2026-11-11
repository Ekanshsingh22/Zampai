import os, re, io, json, sqlite3, time, csv, difflib
from datetime import datetime
from flask import Flask, request, Response, jsonify, send_file
import pdfplumber
app = Flask(__name__); TOL = 0.02  # 2% tolerance on PO amount
def db():
    c = sqlite3.connect("runs.db"); c.row_factory = sqlite3.Row
    c.execute("create table if not exists runs(id integer primary key autoincrement,ts text,file text,vendor text,inv_no text,total real,po text,decision text,reason text,stages text)")
    return c
load = lambda f: list(csv.DictReader(open(f)))
def read_pdf(b):
    with pdfplumber.open(io.BytesIO(b)) as p: return "\n".join((pg.extract_text() or "") for pg in p.pages)
M = r'\$?\s*([\d,]+\.\d{2})'
def money(L, pat):
    for ln in L:
        m = re.match(rf'\s*(?:{pat})\b[^\n]*?{M}', ln, re.I)
        if m: return float(m.group(1).replace(',', ''))
def parse(t):
    L = [x for x in t.splitlines() if x.strip()]
    g = lambda p: (lambda m: m.group(1).strip() if m else None)(re.search(p, t, re.I))
    return dict(vendor_raw=L[0].strip() if L else None,
        inv_no=g(r'(?:invoice\s*(?:no\.?|number|#)|inv\s*#)[ \t]*[:\-]?[ \t]*([A-Z0-9][A-Z0-9\-/]{2,})'),
        date=g(r'\bdate[ \t]*[:\-]?[ \t]*(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})'),
        po=g(r'\b(PO-\d+)\b'), sub=money(L, 'subtotal|net amount'), tax=money(L, 'tax|vat|gst'),
        total=money(L, 'grand total|total due|amount due|total'))
def llm_fill(text, f):  # optional AI fallback for messy layouts (only if API key set)
    import requests
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=30,
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
        json={"model": "claude-sonnet-5-5", "max_tokens": 300, "messages": [{"role": "user", "content":
        "Extract from this invoice as JSON with keys inv_no,date,total(number). Use null if absent; never guess.\n" + text}]})
    j = json.loads(re.search(r'\{.*\}', r.json()["content"][0]["text"], re.S).group(0))
    for k in ("inv_no", "date", "total"): f[k] = f[k] or j.get(k)
    return f
def run(fname, data):
    st, ctx = [], {}
    def S(n, s, d):
        st.append(dict(stage=n, status=s, detail=d)); time.sleep(.45); return json.dumps(st[-1]) + "\n"
    def F(dec, reason):
        c = db(); c.execute("insert into runs(ts,file,vendor,inv_no,total,po,decision,reason,stages) values(?,?,?,?,?,?,?,?,?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), fname, ctx.get('vendor'), ctx.get('inv_no'), ctx.get('total'), ctx.get('po'), dec, reason, json.dumps(st))); c.commit()
        return json.dumps(dict(done=True, decision=dec, reason=reason, fields=ctx)) + "\n"
    yield S("1. Ingest", "ok", f"{fname} ({len(data)//1024+1} KB)")
    try: text = read_pdf(data)
    except Exception as e: yield S("2. Extract text", "fail", str(e)); yield F("REVIEW", "Unreadable file."); return
    if len(text.strip()) < 20:
        yield S("2. Extract text", "warn", "No text layer - scanned image, OCR required")
        yield F("REVIEW", "Scanned invoice with no machine-readable text; routed to manual review / OCR queue."); return
    yield S("2. Extract text", "ok", f"{len(text)} characters read")
    f = parse(text)
    if os.getenv("ANTHROPIC_API_KEY") and not all(f[k] for k in ("inv_no", "date", "total")):
        try: f = llm_fill(text, f); yield S("2b. AI fallback", "ok", "LLM attempted to fill missing fields")
        except Exception as e: yield S("2b. AI fallback", "warn", f"skipped: {e}")
    V, P = load("data/vendors.csv"), load("data/pos.csv")
    m = difflib.get_close_matches(f['vendor_raw'] or "", [v['name'] for v in V], 1, .8)
    vendor = m[0] if m else f['vendor_raw']
    ctx.update(vendor=vendor, inv_no=f['inv_no'], total=f['total'], po=f['po'], date=f['date'])
    yield S("3. Parse fields", "ok", f"vendor={vendor} | invoice#={f['inv_no']} | date={f['date']} | PO={f['po']} | total={f['total']}")
    miss = [k for k in ("inv_no", "date", "total") if not f[k]]
    if miss:
        yield S("4. Completeness", "fail", "Missing: " + ", ".join(miss))
        yield F("HOLD", "Missing " + ", ".join(miss) + ". Returned to vendor for a corrected invoice; not payable as-is."); return
    yield S("4. Completeness", "ok", "Invoice number, date and total present")
    if f['sub'] is not None and f['tax'] is not None and abs(f['sub'] + f['tax'] - f['total']) > .01:
        yield S("5. Arithmetic", "fail", f"{f['sub']} + {f['tax']} != {f['total']}"); yield F("REVIEW", "Subtotal + tax does not equal total."); return
    yield S("5. Arithmetic", "ok", "Subtotal + tax = total")
    v = next((x for x in V if x['name'] == vendor), None)
    if not v: yield S("6. Vendor check", "fail", f"'{vendor}' not in vendor master"); yield F("REVIEW", "Unknown vendor - needs onboarding check."); return
    if v['status'] != 'approved': yield S("6. Vendor check", "fail", f"{vendor} is {v['status']}"); yield F("REJECTED", f"Vendor is {v['status']}; invoice rejected."); return
    yield S("6. Vendor check", "ok", f"{vendor} is an approved vendor")
    c = db(); d = c.execute("select id,ts from runs where vendor=? and inv_no=? and decision in('APPROVED','REVIEW')", (vendor, f['inv_no'])).fetchone()
    if d: yield S("7. Duplicate check", "fail", f"Invoice {f['inv_no']} already processed in run #{d['id']} ({d['ts']})"); yield F("REJECTED", f"Duplicate of run #{d['id']}."); return
    yield S("7. Duplicate check", "ok", "No prior invoice with same vendor + number")
    note = ""
    if f['po']:
        row = next((p for p in P if p['po'] == f['po']), None)
        if not row: yield S("8. PO match", "fail", f"{f['po']} not found"); yield F("REVIEW", "Referenced PO does not exist."); return
        if row['vendor'] != vendor: yield S("8. PO match", "fail", f"{f['po']} belongs to {row['vendor']}"); yield F("REVIEW", "PO belongs to a different vendor."); return
    else:
        cand = [p for p in P if p['vendor'] == vendor]
        if len(cand) != 1: yield S("8. PO match", "fail", f"No PO ref and {len(cand)} candidate POs"); yield F("REVIEW", "Cannot determine PO."); return
        row = cand[0]; note = " (PO inferred - only open PO for vendor)"
    ctx['po'] = row['po']; amt = float(row['amount'])
    billed = c.execute("select coalesce(sum(total),0) from runs where po=? and decision='APPROVED'", (row['po'],)).fetchone()[0]
    yield S("8. PO match", "ok", f"{row['po']} (amount {amt:,.2f}, already billed {billed:,.2f}){note}")
    over = billed + f['total'] - amt
    if over <= 0.005:
        kind = "partial billing" if billed + f['total'] < amt - .005 else "PO fully billed"
        yield S("9. Amount check", "ok", f"{f['total']:,.2f} fits remaining {amt-billed:,.2f} ({kind})")
        yield F("APPROVED", f"Matches {row['po']}; {kind}. Cumulative {billed+f['total']:,.2f} of {amt:,.2f}.{note}")
    elif over / amt <= TOL:
        yield S("9. Amount check", "warn", f"Over PO by {over:,.2f} ({over/amt:.2%}) - within {TOL:.0%} tolerance")
        yield F("APPROVED", f"Approved within tolerance: {over/amt:.2%} over {row['po']}.{note}")
    else:
        yield S("9. Amount check", "fail", f"Over PO by {over:,.2f} ({over/amt:.1%}) - exceeds {TOL:.0%} tolerance")
        yield F("REVIEW", f"Cumulative billing exceeds {row['po']} by {over:,.2f} ({over/amt:.1%}); escalated to buyer.")
@app.route("/")
def index(): return send_file("index.html")
@app.route("/samples")
def samples(): return jsonify(sorted(os.listdir("samples")))
@app.route("/run", methods=["POST"])
def run_():
    if request.form.get("sample"):
        n = os.path.basename(request.form["sample"]); data = open("samples/" + n, "rb").read()
    else:
        fl = request.files["file"]; n, data = fl.filename, fl.read()
    return Response(run(n, data), mimetype="application/x-ndjson")
@app.route("/api/runs")
def runs(): return jsonify([dict(r) for r in db().execute("select * from runs order by id desc")])
@app.route("/api/pos")
def pos():
    c = db(); return jsonify([dict(p, billed=c.execute("select coalesce(sum(total),0) from runs where po=? and decision='APPROVED'", (p['po'],)).fetchone()[0]) for p in load("data/pos.csv")])
@app.route("/api/reset", methods=["POST"])
def reset(): c = db(); c.execute("delete from runs"); c.commit(); return "ok"
if __name__ == "__main__": app.run(port=5000, threaded=True)
