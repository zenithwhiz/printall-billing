from flask import Flask, render_template, request, redirect, url_for, flash, send_file, abort
import sqlite3
from pathlib import Path
from datetime import datetime
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as PDFImage

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "printall.db"
app = Flask(__name__)
app.secret_key = "change-this-local-secret-before-production"

def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with connect_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_no TEXT UNIQUE,
            customer_name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            address TEXT DEFAULT '',
            bill_date TEXT NOT NULL,
            notes TEXT DEFAULT '',
            subtotal REAL NOT NULL DEFAULT 0,
            discount REAL NOT NULL DEFAULT 0,
            total REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS invoice_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
            description TEXT NOT NULL,
            quantity REAL NOT NULL,
            rate REAL NOT NULL,
            amount REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)
        defaults = {
            "business_name": "Print All",
            "business_line_1": "Offset & Flex Printing",
            "business_line_2": "",
            "phone": "",
            "address": "",
            "invoice_prefix": "PA"
        }
        for key, value in defaults.items():
            db.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value))
        # Convert any invoices created by the previous PA-YYYY-NNNN format.
        # Use temporary unique values first to avoid collisions during migration.
        rows = db.execute("SELECT id FROM invoices ORDER BY id").fetchall()
        for row in rows:
            db.execute("UPDATE invoices SET invoice_no = ? WHERE id = ?", (f"MIGRATING-{row['id']}", row["id"]))
        for row in rows:
            db.execute("UPDATE invoices SET invoice_no = ? WHERE id = ?", (str(3000 + row["id"]), row["id"]))

def get_settings():
    with connect_db() as db:
        return {r["key"]: r["value"] for r in db.execute("SELECT key, value FROM settings")}

def invoice_number(invoice_id, bill_date):
    # Plain, continuous invoice numbers: first bill is 3001, then 3002, etc.
    return str(3000 + invoice_id)

def get_invoice(invoice_id):
    with connect_db() as db:
        invoice = db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if not invoice:
            return None, []
        items = db.execute("SELECT * FROM invoice_items WHERE invoice_id = ? ORDER BY id", (invoice_id,)).fetchall()
        return invoice, items

@app.route("/")
def index():
    with connect_db() as db:
        count = db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
        total = db.execute("SELECT COALESCE(SUM(total), 0) FROM invoices").fetchone()[0]
        recent = db.execute("SELECT * FROM invoices ORDER BY id DESC LIMIT 8").fetchall()
    return render_template("index.html", count=count, total=total, recent=recent)

@app.route("/new", methods=["GET", "POST"])
def new_invoice():
    if request.method == "POST":
        customer = request.form.get("customer_name", "").strip()
        if not customer:
            flash("Please enter the customer's name.", "error")
            return redirect(url_for("new_invoice"))
        descriptions = request.form.getlist("description[]")
        quantities = request.form.getlist("quantity[]")
        amounts = request.form.getlist("amount[]")
        bill_date = request.form.get("bill_date") or datetime.now().strftime("%Y-%m-%d")
        try:
            discount = max(0.0, float(request.form.get("discount", "0") or 0))
            items = []
            subtotal = 0.0
            for desc, qty_raw, amount_raw in zip(descriptions, quantities, amounts):
                desc = desc.strip()
                if not desc:
                    continue
                qty = float(qty_raw)
                amount = round(float(amount_raw), 2)
                if qty <= 0 or amount < 0:
                    raise ValueError
                # Keep the legacy rate column in SQLite for compatibility; it is no longer shown.
                rate = round(amount / qty, 2) if qty else 0
                subtotal += amount
                items.append((desc, qty, rate, amount))
            if not items:
                flash("Add at least one item before saving.", "error")
                return redirect(url_for("new_invoice"))
            subtotal = round(subtotal, 2)
            discount = min(discount, subtotal)
            total = round(subtotal - discount, 2)
        except (ValueError, TypeError):
            flash("Check quantities, amounts and discount. Quantities must be above zero and amounts cannot be negative.", "error")
            return redirect(url_for("new_invoice"))

        with connect_db() as db:
            cur = db.execute(
                """INSERT INTO invoices(customer_name, phone, address, bill_date, notes, subtotal, discount, total, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (customer, request.form.get("phone", "").strip(), request.form.get("address", "").strip(),
                 bill_date, request.form.get("notes", "").strip(), subtotal, discount, total,
                 datetime.now().isoformat(timespec="seconds"))
            )
            invoice_id = cur.lastrowid
            inv_no = invoice_number(invoice_id, bill_date)
            db.execute("UPDATE invoices SET invoice_no = ? WHERE id = ?", (inv_no, invoice_id))
            db.executemany(
                "INSERT INTO invoice_items(invoice_id, description, quantity, rate, amount) VALUES (?, ?, ?, ?, ?)",
                [(invoice_id, *item) for item in items]
            )
        flash(f"Invoice {inv_no} saved successfully.", "success")
        return redirect(url_for("view_invoice", invoice_id=invoice_id))
    return render_template("new_invoice.html", today=datetime.now().strftime("%Y-%m-%d"))

@app.route("/invoices")
def invoices():
    q = request.args.get("q", "").strip()
    with connect_db() as db:
        if q:
            rows = db.execute("""SELECT * FROM invoices
                WHERE invoice_no LIKE ? OR customer_name LIKE ? OR phone LIKE ? OR bill_date LIKE ?
                ORDER BY id DESC""", tuple([f"%{q}%"] * 4)).fetchall()
        else:
            rows = db.execute("SELECT * FROM invoices ORDER BY id DESC").fetchall()
    return render_template("invoices.html", invoices=rows, q=q)

@app.route("/invoice/<int:invoice_id>")
def view_invoice(invoice_id):
    invoice, items = get_invoice(invoice_id)
    if invoice is None:
        abort(404)
    return render_template("invoice.html", invoice=invoice, items=items, settings=get_settings())

@app.route("/invoice/<int:invoice_id>/pdf")
def invoice_pdf(invoice_id):
    invoice, items = get_invoice(invoice_id)
    if invoice is None:
        abort(404)
    settings = get_settings()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A5, rightMargin=10*mm, leftMargin=10*mm, topMargin=8*mm, bottomMargin=8*mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Business", parent=styles["Title"], fontSize=21, leading=24, textColor=colors.HexColor("#17324d"), alignment=TA_CENTER, spaceAfter=4))
    styles.add(ParagraphStyle(name="SmallCenter", parent=styles["Normal"], fontSize=9, leading=12, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="Right", parent=styles["Normal"], alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name="CashBill", parent=styles["Heading2"], alignment=TA_CENTER, fontSize=14, leading=17))
    story = []
    story.extend([
        Paragraph(settings.get("business_name", "Print All"), styles["Business"]),
        Paragraph(settings.get("business_line_1", "Offset & Flex Printing"), styles["SmallCenter"]),
    ])
    extra = " · ".join(x for x in [settings.get("business_line_2", ""), settings.get("address", ""), settings.get("phone", "")] if x.strip())
    if extra:
        story.append(Paragraph(extra.replace("&", "&amp;"), styles["SmallCenter"]))
    story += [Spacer(1, 2*mm), Paragraph("CASH BILL", styles["CashBill"]), Spacer(1, 2*mm)]
    info = [
        [Paragraph(f"<b>Invoice No:</b> {invoice['invoice_no']}", styles["Normal"]),
         Paragraph(f"<b>Date:</b> {invoice['bill_date']}", styles["Right"])],
        [Paragraph(f"<b>Customer:</b> {invoice['customer_name']}", styles["Normal"]), ""],
    ]
    if invoice["phone"]:
        info.append([Paragraph(f"<b>Phone:</b> {invoice['phone']}", styles["Normal"]), ""])
    if invoice["address"]:
        info.append([Paragraph(f"<b>Address:</b> {invoice['address'].replace('&', '&amp;')}", styles["Normal"]), ""])
    info_table = Table(info, colWidths=[72*mm, 56*mm])
    info_table.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    story += [info_table, Spacer(1, 6*mm)]
    data = [["#", "Description", "Qty", "Amount (Rs.)"]]
    for idx, item in enumerate(items, 1):
        data.append([str(idx), Paragraph(item["description"].replace("&", "&amp;"), styles["Normal"]),
                     f"{item['quantity']:g}", f"{item['amount']:,.2f}"])
    table = Table(data, colWidths=[8*mm, 67*mm, 15*mm, 22*mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#17324d")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#cbd5e1")),
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("ALIGN",(2,1),(-1,-1),"RIGHT"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f5f7fa")]),
        ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),
    ]))
    story += [table, Spacer(1, 5*mm)]
    totals = [
        ["Subtotal", f"Rs. {invoice['subtotal']:,.2f}"],
        ["Discount", f"Rs. {invoice['discount']:,.2f}"],
        ["TOTAL", f"Rs. {invoice['total']:,.2f}"],
    ]
    totals_table = Table(totals, colWidths=[42*mm, 38*mm], hAlign="RIGHT")
    totals_table.setStyle(TableStyle([
        ("ALIGN",(1,0),(1,-1),"RIGHT"),
        ("LINEABOVE",(0,2),(-1,2),1,colors.HexColor("#17324d")),
        ("FONTNAME",(0,2),(-1,2),"Helvetica-Bold"),
        ("FONTSIZE",(0,2),(-1,2),12),
        ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
    ]))
    story += [totals_table]
    qr_placeholder = Table(
        [[Paragraph("<b>GPay / UPI QR</b><br/><br/>Insert QR code here", styles["SmallCenter"])]],
        colWidths=[53*mm], rowHeights=[27*mm], hAlign="LEFT"
    )
    qr_placeholder.setStyle(TableStyle([
        ("BOX",(0,0),(-1,-1),0.7,colors.HexColor("#b8c1cc")),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("ALIGN",(0,0),(-1,-1),"CENTER"),
        ("LEFTPADDING",(0,0),(-1,-1),2),("RIGHTPADDING",(0,0),(-1,-1),2)
    ]))
    qr_content = qr_placeholder
    seal_signature = Table([
        [Paragraph(" ", styles["Normal"]), Paragraph(" ", styles["Normal"])],
        [Paragraph("Business Seal", styles["SmallCenter"]), Paragraph("Authorized Signature", styles["SmallCenter"])]
    ], colWidths=[35*mm, 35*mm], rowHeights=[10*mm, 5*mm])
    seal_signature.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "BOTTOM"),
        ("LINEABOVE", (0,1), (-1,1), 0.5, colors.HexColor("#b8c1cc")),
    ]))
    payment_seal_row = Table([[qr_content, seal_signature]], colWidths=[58*mm, 70*mm], hAlign="LEFT")
    payment_seal_row.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),2)]))
    story += [Spacer(1, 2*mm), payment_seal_row]
    if invoice["notes"]:
        story += [Spacer(1, 4*mm), Paragraph(f"<b>Notes:</b> {invoice['notes'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')}", styles["Normal"])]
    doc.build(story)
    buffer.seek(0)
    return send_file(buffer, mimetype="application/pdf", as_attachment=True,
                     download_name=f"{invoice['invoice_no']}.pdf")

@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        keys = ["business_name", "business_line_1", "business_line_2", "phone", "address"]
        with connect_db() as db:
            for key in keys:
                value = request.form.get(key, "").strip()
                db.execute("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        flash("Business details updated.", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html", settings=get_settings())

@app.route("/backup")
def backup():
    if not DB_PATH.exists():
        abort(404)
    return send_file(DB_PATH, as_attachment=True, download_name=f"printall-backup-{datetime.now().strftime('%Y%m%d-%H%M')}.db")

if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=False)
