import base64
import html as html_lib
import io
import mimetypes
from functools import lru_cache
from pathlib import Path

import segno
from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

from .meta import TYPE_META
from .models import Document
from .meta import DEFAULT_DELIVERY_TERMS, TYPE_META

MM = 96 / 25.4  # CSS pixels per mm


def _media(name, for_pdf):
    """Resolve a stored media filename to a URL (preview) or data URI (PDF)."""
    if not name:
        return ""
    if not for_pdf:
        return settings.MEDIA_URL + name
    path = Path(settings.MEDIA_ROOT) / name
    if not path.exists():
        return ""
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def receipt_dims():
    """(paper width, printable width) in mm. Standard thermal rolls."""
    paper = int(getattr(settings, "RECEIPT_PAPER_MM", 80))
    return paper, (72 if paper >= 80 else 48)


def template_for(doc):
    return "documents/print/receipt.html" if doc.doc_type == Document.RECEIPT \
        else "documents/print/a4.html"


@lru_cache(maxsize=4)
def _receipt_logo(path, mtime):
    """Logo mark as crisp black-on-white PNG for thermal printing (wordmark cropped off)."""
    im = Image.open(path).convert("RGBA")
    base = Image.new("RGBA", im.size, "white")
    base.alpha_composite(im)
    r, g, b = base.convert("RGB").split()
    ink = ImageChops.darker(ImageChops.darker(r, g), b).point(lambda v: 255 if v < 200 else 0)

    w, h = ink.size
    rows = [ink.crop((0, y, w, y + 1)).getbbox() is not None for y in range(h)]
    start = next((y for y, v in enumerate(rows) if v), 0)
    gap, blank, end = max(8, h // 40), 0, h
    for y in range(start, h):          # the mark ends at the first clear gap above the wordmark
        if rows[y]:
            blank = 0
        else:
            blank += 1
            if blank >= gap:
                end = y - blank + 1
                break
    mark = ink.crop((0, start, w, end))
    mark = mark.crop(mark.getbbox() or (0, 0, w, end - start))
    mark.thumbnail((360, 360), Image.LANCZOS)
    mark = ImageChops.invert(mark.point(lambda v: 255 if v > 110 else 0))
    buf = io.BytesIO()
    mark.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def receipt_logo_uri(name):
    if not name:
        return ""
    path = Path(settings.MEDIA_ROOT) / name
    if not path.exists():
        return ""
    return _receipt_logo(str(path), path.stat().st_mtime)


def qr_data_uri(doc):
    p = doc.biz
    base = getattr(settings, "SITE_URL", "").rstrip("/")
    if base:
        payload = base + reverse("documents:verify", args=[doc.number, doc.verify_code])
    else:
        payload = (f"{p.name} | {doc.number} | {doc.issue_date:%d/%m/%Y} | "
                   f"KSh {doc.total:,.2f} | {doc.verify_code}")
    return segno.make(payload, error="m").svg_data_uri(
        scale=4, border=1, dark="#000000", light="#FFFFFF")


def build_context(doc, for_pdf=False, **extra):
    biz = doc.biz                      # frozen at creation, not the live profile
    meta = TYPE_META[doc.doc_type]
    paper, printable = receipt_dims()

    ctx = {
        "doc": doc, "p": biz, "items": doc.items.all(), "for_pdf": for_pdf,
        "accent": meta["accent"], "title": meta["label"].upper(),
        "logo": _media(biz.logo, for_pdf), "signature": _media(biz.signature, for_pdf),
        "stamp": _media(biz.stamp, for_pdf),
        "paper_mm": paper, "print_mm": printable,
        "page_size": f"{paper}mm auto", "toolbar": False,
    }

    if doc.doc_type == Document.RECEIPT:
        ctx["receipt_logo"] = receipt_logo_uri(biz.logo)
        ctx["qr"] = qr_data_uri(doc)

    ctx["etims_qr_img"] = (
        segno.make(doc.etims_qr, error="m").svg_data_uri(scale=4, border=1, dark="#000000", light="#FFFFFF")
        if doc.etims_qr else "")
    ctx.update(extra)
    return ctx


def build_pdf(doc, request):
    ctx = build_context(doc, True, page_size="")
    html = render_to_string(template_for(doc), ctx, request)
    zero = {"top": "0", "right": "0", "bottom": "0", "left": "0"}

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            if doc.doc_type == Document.RECEIPT:
                paper, _ = receipt_dims()
                page = browser.new_page(viewport={"width": round(paper * MM), "height": 800})
                page.set_content(html, wait_until="load")
                # Roll length = exact content height, so the PDF has no blank tail
                h = page.evaluate("Math.ceil(document.body.getBoundingClientRect().height)")
                return page.pdf(width=f"{paper}mm", height=f"{h + 2}px",
                                margin=zero, print_background=True)

            biz = doc.biz   # frozen business details, attribute access only
            footer = (
                '<div style="width:100%;font-size:8px;color:#64748B;text-align:center;'
                'font-family:Helvetica,Arial,sans-serif;">'
                f'{html_lib.escape(biz.name)} | {html_lib.escape(biz.tagline)} | '
                'Page <span class="pageNumber"></span> of <span class="totalPages"></span></div>'
            )
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            return page.pdf(
                format="A4", print_background=True, display_header_footer=True,
                header_template="<span></span>", footer_template=footer,
                margin={"top": "0", "right": "0", "bottom": "16mm", "left": "0"})
        finally:
            browser.close()
            

def build_delivery_context(note, for_pdf=False, **extra):
    biz = note.biz
    doc = note.document
    ctx = {
        "note": note, "doc": doc, "client": doc.client, "p": biz,
        "items": note.items.all(), "for_pdf": for_pdf, "accent": "#16A34A",
        "logo": _media(biz.logo, for_pdf), "signature": _media(biz.signature, for_pdf),
        "stamp": _media(biz.stamp, for_pdf),
        "delivery_terms": biz.delivery_terms or DEFAULT_DELIVERY_TERMS,
        "copies": ["PREVIEW"],
    }
    ctx.update(extra)
    return ctx


def build_delivery_pdf(note, request):
    ctx = build_delivery_context(note, True, copies=["SELLER COPY", "CUSTOMER COPY"])
    html = render_to_string("documents/print/delivery.html", ctx, request)
    biz = note.biz
    footer = (
        '<div style="width:100%;font-size:8px;color:#64748B;text-align:center;'
        'font-family:Helvetica,Arial,sans-serif;">'
        f'{html_lib.escape(biz.name)} | {html_lib.escape(note.number)} | '
        'Page <span class="pageNumber"></span> of <span class="totalPages"></span></div>'
    )
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            return page.pdf(
                format="A4", print_background=True, display_header_footer=True,
                header_template="<span></span>", footer_template=footer,
                margin={"top": "0", "right": "0", "bottom": "16mm", "left": "0"})
        finally:
            browser.close()