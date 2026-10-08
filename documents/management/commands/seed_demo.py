# documents/management/commands/seed_demo.py
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image, ImageChops

from documents.models import BusinessProfile, Client, Document, DocumentItem

TERMS = """1. Payment is due within 14 days of the invoice date unless agreed otherwise in writing.
2. Quotations are valid for the period stated and prices may change after expiry.
3. Goods remain the property of Gikuru Codes Tech Solutions until paid in full.
4. Refurbished equipment carries a 6 month warranty and new equipment carries a 1 year warranty.
5. Warranty does not cover power surges, liquid damage, misuse or unauthorised repair.
6. Custom software is billed per agreed milestone. Deposits are non-refundable once work has started."""

RECEIPT_FOOTER = """6 months warranty on refurbished items, 1 year on new items.
No warranty on power related issues, RAM, HDDs, laptop or keyboard screens and software.
Goods once sold cannot be returned. Money once received is not refundable.
Thank you for your business."""


def process(src, dst, transparent):
    im = Image.open(src).convert("RGBA")
    r, g, b, _ = im.split()
    mn = ImageChops.darker(ImageChops.darker(r, g), b)
    if transparent:
        alpha = mn.point(lambda v: 255 if v <= 200 else (0 if v >= 245 else int((245 - v) / 45 * 255)))
        im.putalpha(alpha)
    else:
        alpha = mn.point(lambda v: 0 if v >= 248 else 255)
    bbox = alpha.getbbox()
    if bbox:
        im = im.crop(bbox)
    im.thumbnail((900, 900))
    im.save(dst)


class Command(BaseCommand):
    help = "Load brand assets, default terms, receipt footer and demo documents"

    def handle(self, *args, **opts):
        src_dir = Path(settings.BASE_DIR) / "seed_assets"
        out_dir = Path(settings.MEDIA_ROOT) / "brand"
        out_dir.mkdir(parents=True, exist_ok=True)

        keywords = {
            "logo": ("logo", False),
            "signature": ("sign", True),
            "stamp": ("stamp", True),
        }
        candidates = [f for f in src_dir.glob("*")
                      if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")]
        names = {}
        for field, (kw, transparent) in keywords.items():
            match = next((f for f in candidates if kw in f.name.lower()), None)
            if match:
                process(match, out_dir / f"{field}.png", transparent)
                names[field] = f"brand/{field}.png"
                self.stdout.write(f"{field}: {match.name}")
            else:
                self.stdout.write(self.style.WARNING(f"No file containing '{kw}' in {src_dir}"))

        profile, _ = BusinessProfile.objects.update_or_create(pk=1, defaults=dict(
            name="Gikuru Codes Tech Solutions",
            tagline="Smart Solutions, Smarter Code",
            address="Nairobi, Kenya",
            phone="+254 700 000 000",
            email="hello@example.com",
            kra_pin="P000000000X",
            payment_details="M-Pesa Paybill: 000000\nAccount: Document number\nBank: Sample Bank, A/C 0000000000",
            vat_rate=Decimal("16.00"),
            default_terms=TERMS,
            receipt_footer=RECEIPT_FOOTER,
        ))
        for field, name in names.items():
            setattr(profile, field, name)
        profile.save()

        if Document.objects.exists():
            self.stdout.write("Documents already exist, skipping demo documents.")
            return

        client = Client.objects.create(
            name="Test Client Ltd", phone="+254 711 000 000",
            email="accounts@testclient.example", address="Moi Avenue, Nairobi", kra_pin="P111111111A")

        def make(doc_type, items, **kw):
            doc = Document.objects.create(doc_type=doc_type, **kw)
            for desc, qty, price, sn in items:
                DocumentItem.objects.create(document=doc, description=desc, quantity=qty,
                                            unit_price=Decimal(price), serial_numbers=sn)
            return doc

        make("quotation", [
            ("Custom POS system setup (Django)", 1, "85000", ""),
            ("Hosting setup and deployment", 1, "15000", ""),
            ("Staff training (2 days)", 2, "5000", ""),
        ], client=client, status="sent", discount=Decimal("5000"), terms=TERMS)

        make("invoice", [
            ("Dell Optiplex 3050 (8GB, no HDD, i3-6100)", 4, "12000", "SN-DT0001\nSN-DT0002\nSN-DT0003\nSN-DT0004"),
            ("Acer 18\" monitor", 4, "2500", ""),
            ("Power cables", 10, "100", ""),
        ], client=client, status="sent", terms=TERMS)

        make("receipt", [
            ("Dell Optiplex 3050 i5-8400 (8GB, no HDD)", 1, "12000", "SN-DT0101"),
            ("Dell Optiplex 3050 i3-6100 (8GB, no HDD)", 4, "12000", "SN-DT0102\nSN-DT0103\nSN-DT0104\nSN-DT0105"),
            ("Acer X1B3H", 4, "2500", ""),
            ("Acer 18\" monitor", 1, "2500", ""),
            ("EX UK keyboards", 5, "350", ""),
            ("Power cables", 10, "100", ""),
            ("VGA cables", 5, "200", ""),
            ("Lenovo D new mouse", 5, "400", ""),
        ], client_name="Walk-in Customer", status="paid", vat_mode="inclusive",
           payment_method="mpesa", payment_reference="QWE123ABC4", served_by="Joseph")

        self.stdout.write(self.style.SUCCESS("Seeded profile, assets and 3 demo documents."))