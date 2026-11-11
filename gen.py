# Generates test data: vendor master, PO dataset, 10 sample invoice PDFs
import csv, os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from PIL import Image, ImageDraw
os.makedirs("samples", exist_ok=True); os.makedirs("data", exist_ok=True)
csv.writer(open("data/vendors.csv","w",newline="")).writerows([("name","status"),("Acme Industrial Supplies","approved"),("Globex Logistics","approved"),("Initech Software","approved"),("Hooli Cloud","approved"),("Umbrella Traders","blocked")])
csv.writer(open("data/pos.csv","w",newline="")).writerows([("po","vendor","amount"),("PO-1001","Acme Industrial Supplies",10000),("PO-1002","Globex Logistics",24000),("PO-1003","Initech Software",5000),("PO-1004","Hooli Cloud",8000)])
def inv(fn, vendor, no, date, po, items, tax=.10, L="A"):
    c = canvas.Canvas("samples/"+fn, pagesize=A4); y = [800]
    def line(t, s=11):
        c.setFont("Helvetica", s); c.drawString(50, y[0], t); y[0] -= 18
    line(vendor, 16); line("12 Market Street, Springfield", 9); y[0] -= 10
    line("INVOICE" if L=="A" else "TAX INVOICE", 14)
    if no: line(f"Invoice No: {no}" if L=="A" else f"Inv # {no}")
    if date: line(f"Date: {date}")
    if po: line(f"Customer PO: {po}" if L=="A" else f"Your ref {po}")
    y[0] -= 10
    for d, q, p in items: line(f"{d}    {q} x {p:,.2f}")
    sub = sum(q*p for _, q, p in items); t = round(sub*tax, 2); tot = sub+t; y[0] -= 10
    if L=="A": line(f"Subtotal: ${sub:,.2f}"); line(f"Tax ({int(tax*100)}%): ${t:,.2f}"); line(f"Total: ${tot:,.2f}", 13)
    else: line(f"Net amount {sub:,.2f}"); line(f"VAT {t:,.2f}"); line(f"Amount Due {tot:,.2f}", 13)
    c.save()
inv("01_happy_acme.pdf","Acme Industrial Supplies","INV-A-501","2026-10-05","PO-1001",[("Hydraulic pump",2,1500),("Fittings kit",10,100)])
inv("02_tolerance_globex.pdf","Globex Logistics","GL-8841","2026-10-07","PO-1002",[("Freight - October",1,22000)],L="B")
inv("03_split_initech_1.pdf","Initech Software","IN-2001","2026-10-08","PO-1003",[("Licences phase 1",1,3000)],tax=0,L="B")
inv("04_split_initech_2.pdf","Initech Software","IN-2002","2026-10-20","PO-1003",[("Licences phase 2",1,2000)],tax=0,L="B")
inv("05_duplicate_acme.pdf","Acme Industrial Supplies","INV-A-501","2026-10-12","PO-1001",[("Hydraulic pump",2,1500),("Fittings kit",10,100)],L="B")
inv("06_missing_fields.pdf","Globex Logistics",None,None,"PO-1002",[("Consulting",1,1000)])
inv("07_blocked_umbrella.pdf","Umbrella Traders","UM-77","2026-10-09",None,[("Misc goods",1,900)])
inv("08_over_po_acme.pdf","Acme Industrial Supplies","INV-A-777","2026-10-15","PO-1001",[("Bulk order",1,12000)])
inv("09_implied_po_hooli.pdf","Hooli Cloud","HL-310","2026-10-11",None,[("Cloud hosting Oct",1,2000)],tax=0,L="B")

im = Image.new("RGB", (600, 300), "white")
d = ImageDraw.Draw(im)

for i, t in enumerate([
    "Globex Logistics",
    "Invoice No: GL-9000",
    "Total: $500.00"
]):
    d.text((30, 30 + 30*i), t, fill="black")

# Save image as PNG first
im.save("samples/10_scanned_image.png")

# Create image-only PDF using ReportLab
c = canvas.Canvas(
    "samples/10_scanned_image.pdf",
    pagesize=(600, 300)
)
c.drawImage(
    "samples/10_scanned_image.png",
    0, 0,
    width=600,
    height=300
)
c.save()

print("generated")

