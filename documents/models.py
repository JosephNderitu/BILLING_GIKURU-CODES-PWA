# documents/models.py
from decimal import Decimal
from django.db import models
from django.utils import timezone
import hashlib, hmac
from functools import cached_property
from django.conf import settings
from .meta import STATUS_STYLES
from types import SimpleNamespace
import uuid
from pathlib import Path
import secrets
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce

class BusinessProfile(models.Model):
    name = models.CharField(max_length=150)
    tagline = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    kra_pin = models.CharField("KRA PIN", max_length=30, blank=True)
    logo = models.ImageField(upload_to="brand/", blank=True)
    signature = models.ImageField(upload_to="brand/", blank=True)
    stamp = models.ImageField(upload_to="brand/", blank=True)
    payment_details = models.TextField(blank=True, help_text="Bank, Paybill, Till, etc.")
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("16.00"))
    default_terms = models.TextField(blank=True)
    receipt_footer = models.TextField(blank=True)
    delivery_terms = models.TextField(blank=True, help_text="Acceptance wording on delivery notes")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.pk = 1  # singleton
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        return cls.objects.first()
    
    def snapshot(self):
        return {
            "name": self.name, "tagline": self.tagline, "address": self.address,
            "phone": self.phone, "email": self.email, "kra_pin": self.kra_pin,
            "payment_details": self.payment_details, "receipt_footer": self.receipt_footer,
            "vat_rate": str(self.vat_rate),
            "logo": self.logo.name or "", "signature": self.signature.name or "",
            "stamp": self.stamp.name or "",
            "delivery_terms": self.delivery_terms,
        }


class Client(models.Model):
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    kra_pin = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Document(models.Model):
    QUOTATION, INVOICE, RECEIPT = "quotation", "invoice", "receipt"
    TYPES = [(QUOTATION, "Quotation"), (INVOICE, "Invoice"), (RECEIPT, "Receipt")]
    PREFIX = {QUOTATION: "QUO", INVOICE: "INV", RECEIPT: "RCP"}

    STATUSES = [
        ("draft", "Draft"), ("sent", "Sent"), ("accepted", "Accepted"),
        ("paid", "Paid"), ("void", "Void"),
    ]
    PAYMENT_METHODS = [
        ("cash", "Cash"), ("mpesa", "M-Pesa"), ("bank", "Bank Transfer"), ("card", "Card"),
    ]
    VAT_MODES = [
        ("exclusive", "VAT exclusive (add VAT on top)"),
        ("inclusive", "VAT inclusive (prices include VAT)"),
        ("none", "No VAT"),
    ]

    doc_type = models.CharField(max_length=10, choices=TYPES)
    number = models.CharField(max_length=30, unique=True, editable=False)
    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.SET_NULL)
    client_name = models.CharField(max_length=150, blank=True, help_text="Walk-in name if no client")
    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default="draft")
    vat_mode = models.CharField(max_length=10, choices=VAT_MODES, default="exclusive")
    served_by = models.CharField(max_length=80, blank=True)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHODS, blank=True)
    payment_reference = models.CharField(max_length=60, blank=True)
    notes = models.TextField(blank=True)
    terms = models.TextField(blank=True)
    buyer_pin = models.CharField("Buyer KRA PIN", max_length=20, blank=True)
    etims_invoice_no = models.CharField("eTIMS invoice no.", max_length=60, blank=True)
    etims_qr = models.CharField("eTIMS QR data or link", max_length=500, blank=True,
                                help_text="Paste the QR link or data KRA gives you for this invoice")
    share_token = models.CharField(max_length=32, unique=True, null=True, blank=True, editable=False)
    share_viewed_at = models.DateTimeField(null=True, blank=True, editable=False)
    business = models.JSONField(default=dict, blank=True, editable=False)
    source = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="converted")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.number

    @property
    def display_client(self):
        return self.client.name if self.client else (self.client_name or "Walk-in Customer")

    # replace subtotal / taxable / vat_amount / total with these
    @cached_property
    def biz(self):
        """Business details frozen at creation. Falls back to the live profile only if empty."""
        data = dict(self.business or {})
        if not data:
            p = BusinessProfile.get()
            data = p.snapshot() if p else {}
        for key in ("name", "tagline", "address", "phone", "email", "kra_pin",
                    "payment_details", "receipt_footer", "logo", "signature", "stamp"):
            data.setdefault(key, "")
        data.setdefault("vat_rate", "16.00")
        return SimpleNamespace(**data)

    @cached_property
    def vat_rate(self):
        return Decimal(str(self.biz.vat_rate))

    @property
    def items_total(self):
        return sum((i.line_total for i in self.items.all()), Decimal("0"))

    @property
    def gross(self):
        return max(self.items_total - self.discount, Decimal("0"))

    @property
    def net_amount(self):
        if self.vat_mode == "inclusive":
            return (self.gross / (1 + self.vat_rate / 100)).quantize(Decimal("0.01"))
        return self.gross

    @property
    def vat_amount(self):
        if self.vat_mode == "exclusive":
            return (self.gross * self.vat_rate / 100).quantize(Decimal("0.01"))
        if self.vat_mode == "inclusive":
            return self.gross - self.net_amount
        return Decimal("0")

    @property
    def total(self):
        return self.gross + self.vat_amount if self.vat_mode == "exclusive" else self.gross
    
    @property
    def total_qty(self):
        return sum((i.quantity for i in self.items.all()), Decimal("0"))

    @property
    def verify_code(self):
        """Unguessable, stateless code used in the receipt QR."""
        return hmac.new(settings.SECRET_KEY.encode(), self.number.encode(),
                        hashlib.sha256).hexdigest()[:12]

    @property
    def is_overdue(self):
        return bool(self.doc_type == self.INVOICE and self.due_date
                    and self.status == "sent" and self.due_date < timezone.localdate())

    @property
    def status_label(self):
        return "Overdue" if self.is_overdue else self.get_status_display()

    @property
    def status_style(self):
        return STATUS_STYLES["overdue" if self.is_overdue else self.status]

    @property
    def buyer_pin_display(self):
        return self.buyer_pin or (self.client.kra_pin if self.client else "")

    @property
    def is_sale(self):
        """Counts as a sale (reports and stock). A receipt issued from an invoice is not counted twice."""
        if self.doc_type == self.INVOICE:
            return self.status in ("sent", "paid")
        if self.doc_type == self.RECEIPT:
            return self.status == "paid" and not (self.source_id and self.source.doc_type == self.INVOICE)
        return False

    def ensure_share_token(self, regenerate=False):
        if regenerate or not self.share_token:
            self.share_token = secrets.token_urlsafe(18)
            if regenerate:
                self.share_viewed_at = None
            self.save(update_fields=["share_token", "share_viewed_at"])
        return self.share_token
    
    def save(self, *args, **kwargs):
        if not self.number:
            year = timezone.localdate().year
            prefix = f"{self.PREFIX[self.doc_type]}-{year}-"
            last = (Document.objects.filter(number__startswith=prefix)
                    .order_by("-number").first())
            seq = int(last.number.split("-")[-1]) + 1 if last else 1
            self.number = f"{prefix}{seq:04d}"
        if not self.business:                      # frozen once, on first save
            p = BusinessProfile.get()
            if p:
                self.business = p.snapshot()
                self.__dict__.pop("biz", None)
                self.__dict__.pop("vat_rate", None)
        super().save(*args, **kwargs)

class DocumentItem(models.Model):
    document = models.ForeignKey(Document, related_name="items", on_delete=models.CASCADE)
    description = models.CharField(max_length=255)
    serial_numbers = models.TextField(blank=True, help_text="Optional, one per line")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    product = models.ForeignKey("Product", null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="sold_items")

    @property
    def serials(self):
        return [s.strip() for s in self.serial_numbers.splitlines() if s.strip()]
    
    @property
    def line_total(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return self.description
    
BIZ_KEYS = ("name", "tagline", "address", "phone", "email", "kra_pin", "payment_details",
            "receipt_footer", "delivery_terms", "logo", "signature", "stamp")


def make_biz(data):
    data = dict(data or {})
    if not data:
        p = BusinessProfile.get()
        data = p.snapshot() if p else {}
    for key in BIZ_KEYS:
        data.setdefault(key, "")
    data.setdefault("vat_rate", "16.00")
    return SimpleNamespace(**data)


def signed_path(instance, filename):
    ext = Path(filename).suffix.lower()
    return f"signed/{timezone.localdate():%Y/%m}/{uuid.uuid4().hex}{ext}"


class DeliveryNote(models.Model):
    document = models.ForeignKey(Document, related_name="deliveries", on_delete=models.CASCADE)
    number = models.CharField(max_length=30, unique=True, editable=False)
    delivery_date = models.DateField(default=timezone.localdate)
    delivery_location = models.CharField(max_length=200, blank=True)
    delivered_by = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    received_by = models.CharField(max_length=120, blank=True)
    signed_copy = models.FileField(upload_to=signed_path, blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)
    business = models.JSONField(default=dict, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            prefix = f"DN-{timezone.localdate().year}-"
            last = DeliveryNote.objects.filter(number__startswith=prefix).order_by("-number").first()
            seq = int(last.number.split("-")[-1]) + 1 if last else 1
            self.number = f"{prefix}{seq:04d}"
        if not self.business:
            p = BusinessProfile.get()
            if p:
                self.business = p.snapshot()
                self.__dict__.pop("biz", None)
        super().save(*args, **kwargs)

    @cached_property
    def biz(self):
        return make_biz(self.business)

    @property
    def is_signed(self):
        return bool(self.signed_copy)

    @property
    def signed_is_image(self):
        return self.signed_copy.name.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))


class DeliveryItem(models.Model):
    CATEGORIES = [("computer", "Computer"), ("monitor", "Monitor"), ("keyboard", "Keyboard"),
                  ("mouse", "Mouse"), ("cable", "Cable / adapter"), ("other", "Other")]

    note = models.ForeignKey(DeliveryNote, related_name="items", on_delete=models.CASCADE)
    description = models.CharField(max_length=255)
    category = models.CharField(max_length=10, choices=CATEGORIES, default="other")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    serial_numbers = models.TextField(blank=True)
    checks = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.description

    @property
    def serials(self):
        return [s.strip() for s in self.serial_numbers.splitlines() if s.strip()]

    @property
    def check_list(self):
        return list(self.checks or [])

    @property
    def boxes(self):
        """One tick column per unit for computers and monitors (2 to 8 units), else a single column."""
        qty = int(self.quantity)
        if self.category in ("computer", "monitor") and 1 < qty <= 8:
            s = self.serials
            return [s[i] if i < len(s) else f"Unit {i + 1}" for i in range(qty)]
        return [""]

    @property
    def colspan(self):
        return len(self.boxes) + 1
    
class ProductQuerySet(models.QuerySet):
    def with_stock(self):
        return self.annotate(on_hand=Coalesce(
            Sum("movements__qty"), Value(Decimal("0")),
            output_field=models.DecimalField(max_digits=12, decimal_places=2)))


class Product(models.Model):
    name = models.CharField(max_length=200)
    sku = models.CharField("SKU", max_length=40, blank=True)
    category = models.CharField(max_length=10, choices=DeliveryItem.CATEGORIES, default="other",
                                help_text="Sets the delivery checklist used for this item")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    track_stock = models.BooleanField(default=False)
    track_serials = models.BooleanField("Track serial numbers", default=False,
                                        help_text="Registers each unit's serial (turns on stock tracking)")
    reorder_level = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    active = models.BooleanField(default=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.track_serials:
            self.track_stock = True
        super().save(*args, **kwargs)

    @property
    def stock(self):
        return self.movements.aggregate(s=Sum("qty"))["s"] or Decimal("0")


class StockMovement(models.Model):
    PURCHASE, SALE, ADJUST = "purchase", "sale", "adjustment"
    REASONS = [(PURCHASE, "Stock received"), (SALE, "Sale"), (ADJUST, "Adjustment")]

    product = models.ForeignKey(Product, related_name="movements", on_delete=models.CASCADE)
    qty = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=10, choices=REASONS)
    document = models.ForeignKey(Document, null=True, blank=True, related_name="stock_movements",
                                 on_delete=models.CASCADE)
    note = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class ProductSerial(models.Model):
    IN_STOCK, SOLD = "in_stock", "sold"
    STATUSES = [(IN_STOCK, "In stock"), (SOLD, "Sold")]

    product = models.ForeignKey(Product, related_name="serials", on_delete=models.CASCADE)
    serial = models.CharField(max_length=80)
    status = models.CharField(max_length=10, choices=STATUSES, default=IN_STOCK)
    document = models.ForeignKey(Document, null=True, blank=True, related_name="sold_serials",
                                 on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["serial"]
        constraints = [models.UniqueConstraint(fields=["product", "serial"], name="uniq_product_serial")]