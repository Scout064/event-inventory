import io
import os
from PIL import Image, ImageDraw, ImageFont
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from inventory_app.db import get_db, load_config


def generate_qr_with_logo(data_text, logo_path=None, box_size=10, border=4):
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=box_size,
        border=border
    )
    qr.add_data(data_text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    if logo_path and os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA")
        qr_w, qr_h = img.size
        logo_size = int(min(qr_w, qr_h) * 0.22)
        logo.thumbnail((logo_size, logo_size), Image.LANCZOS)
        lx = (qr_w - logo.size[0]) // 2
        ly = (qr_h - logo.size[1]) // 2
        img.paste(logo, (lx, ly), logo)

    return img


def create_label_image(inventory_id_val, name, category, serial, manufacturer, model):
    """Generates the PNG bytes for a label."""
    cfg = load_config()
    qr = generate_qr_with_logo(inventory_id_val, cfg.get("logo_path"))

    dpi = 300
    width_px = int((100 / 25.4) * dpi)
    height_px = int((54 / 25.4) * dpi)
    label = Image.new("RGB", (width_px, height_px), "white")

    qr_size = int(height_px * 0.9)
    qr = qr.resize((qr_size, qr_size), Image.LANCZOS)
    label.paste(qr, (int(height_px * 0.05), int(height_px * 0.05)))

    draw = ImageDraw.Draw(label)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    lines = []
    if inventory_id_val:
        lines.append(inventory_id_val)
    if name or category:
        lines.append(f"{name} ({category})" if category else name)
    if serial:
        lines.append(f"SN: {serial}")
    if manufacturer or model:
        lines.append(f"{manufacturer} {model}".strip())

    x = qr_size + int(height_px * 0.1)
    y_start = int(height_px * 0.12)
    max_text_width = width_px - x - int(height_px * 0.05)
    max_text_height = height_px - y_start - int(height_px * 0.05)

    base_font_size = int(height_px * 0.08)
    min_font_size = 10

    def compute_block_height(f_size):
        return len(lines) * f_size + (len(lines) - 1) * int(f_size * 0.5)

    font_size = base_font_size
    while compute_block_height(font_size) > max_text_height and font_size > min_font_size:
        font_size -= 1

    y = y_start
    for text in lines:
        size = font_size
        font = ImageFont.truetype(font_path, size)
        while draw.textlength(text, font=font) > max_text_width and size > min_font_size:
            size -= 1
            font = ImageFont.truetype(font_path, size)
        draw.text((x, y), text, font=font, fill="black")
        y += size + int(size * 0.5)

    bio = io.BytesIO()
    label.save(bio, format="PNG")
    bio.seek(0)
    return bio


def create_items_pdf():
    """Generates the bytes for the items report PDF."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT inventory_id, name, category, serial_number, manufacturer, model FROM items ORDER BY name")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    bio = io.BytesIO()
    c = canvas.Canvas(bio, pagesize=A4, pageCompression=1)
    width, height = A4
    y = height - 20 * mm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, y, "Item Inventory Report")
    y -= 10 * mm
    c.setFont("Helvetica", 10)
    for r in rows:
        line = f"{r[0]} | {r[1]} | {r[2] or ''} | SN:{r[3] or ''} | {r[4] or ''} {r[5] or ''}"
        if y < 20 * mm:
            c.showPage()
            y = height - 20 * mm
            c.setFont("Helvetica", 10)
        c.drawString(15 * mm, y, line[:120])
        y -= 6 * mm
    c.showPage()
    c.save()
    bio.seek(0)
    return bio


def create_production_pdf(pid):
    """Generates the bytes for a production BOM PDF."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, date, notes FROM productions WHERE id=%s", (pid,))
    prod = cur.fetchone()
    if not prod:
        return None

    cur.execute("""SELECT i.inventory_id, i.name, i.category, i.serial_number, i.manufacturer, i.model
                   FROM production_items pi
                   JOIN items i ON i.inventory_id = pi.inventory_id
                   WHERE pi.production_id=%s
                   ORDER BY i.name""", (pid,))
    items = cur.fetchall()
    cur.close()
    conn.close()

    bio = io.BytesIO()
    c = canvas.Canvas(bio, pagesize=A4, pageCompression=1)
    width, height = A4
    margin_left = 20 * mm
    max_width = width - (margin_left * 2)
    y = height - 20 * mm

    c.setFont("Helvetica-Bold", 14)
    c.drawString(margin_left, y, f"BOM – {prod[1]}")
    y -= 8 * mm
    c.setFont("Helvetica", 10)
    c.drawString(margin_left, y, f"Date: {prod[2] or 'TBD'}")
    y -= 8 * mm

    if prod[3]:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(margin_left, y, "Notes:")
        c.setFont("Helvetica", 10)
        note_lines = simpleSplit(prod[3], "Helvetica", 10, max_width)
        for line in note_lines:
            y -= 5 * mm
            if y < 20 * mm:
                c.showPage()
                y = height - 20 * mm
            c.drawString(margin_left, y, line)
        y -= 10 * mm

    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin_left, y, "Inventory ID | Item Name | Category | Details")
    y -= 2 * mm
    c.line(margin_left, y, width - margin_left, y)
    y -= 6 * mm

    for r in items:
        details = f"SN:{r[3] or 'N/A'} | {r[4] or ''} {r[5] or ''}"
        item_text = f"{r[0]} | {r[1]} | {r[2] or ''} | {details}"
        wrapped_item = simpleSplit(item_text, "Helvetica", 10, max_width)
        for i, line in enumerate(wrapped_item):
            if y < 20 * mm:
                c.showPage()
                y = height - 20 * mm
                c.setFont("Helvetica", 10)
            current_x = margin_left if i == 0 else margin_left + 4 * mm
            c.drawString(current_x, y, line)
            y -= 5 * mm
        y -= 3 * mm

    c.showPage()
    c.save()
    bio.seek(0)
    return bio, prod[1]
