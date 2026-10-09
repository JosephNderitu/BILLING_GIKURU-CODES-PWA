from django import forms
from django.forms import inlineformset_factory

from .models import Document, DocumentItem, Product, ProductSerial

INPUT = ("w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none "
         "focus:border-brand-green focus:ring-2 focus:ring-brand-green/20")

STATUS_CHOICES = {
    "quotation": [("draft", "Draft"), ("sent", "Sent"), ("accepted", "Accepted"), ("void", "Void")],
    "invoice": [("draft", "Draft"), ("sent", "Sent"), ("paid", "Paid"), ("void", "Void")],
    "receipt": [("paid", "Paid"), ("void", "Void")],
}


class StyledMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            if not isinstance(f.widget, forms.CheckboxInput):
                f.widget.attrs.setdefault("class", INPUT)

class DocumentForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Document
        fields = ["client", "client_name", "issue_date", "due_date", "status", "vat_mode",
                  "discount", "payment_method", "payment_reference", "served_by",
                  "buyer_pin", "etims_invoice_no", "etims_qr", "notes", "terms"]
        widgets = {
            "issue_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "discount": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
            "terms": forms.Textarea(attrs={"rows": 5}),
        }
        labels = {"client_name": "Walk-in name (if no client)"}

    def __init__(self, *args, doc_type, **kwargs):
        super().__init__(*args, **kwargs)
        drop = {
            "quotation": ["payment_method", "payment_reference", "served_by",
                          "buyer_pin", "etims_invoice_no", "etims_qr"],
            "invoice": ["payment_method", "payment_reference", "served_by"],
            "receipt": ["due_date", "terms"],
        }[doc_type]
        for name in drop:
            del self.fields[name]
        self.fields["status"].choices = STATUS_CHOICES[doc_type]
        if doc_type == Document.QUOTATION:
            self.fields["due_date"].label = "Valid until"


class ItemForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = DocumentItem
        fields = ["product", "description", "serial_numbers", "quantity", "unit_price"]
        widgets = {
            "product": forms.HiddenInput(),
            "description": forms.TextInput(attrs={
                "placeholder": "Type or pick a product", "list": "products-dl", "autocomplete": "off"}),
            "serial_numbers": forms.Textarea(attrs={"rows": 1, "placeholder": "Serial numbers (optional)"}),
            "quantity": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "unit_price": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }


class ProductForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "sku", "category", "unit_price", "track_stock", "track_serials",
                  "reorder_level", "active"]
        widgets = {"unit_price": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
                   "reorder_level": forms.NumberInput(attrs={"step": "1", "min": "0"})}


class ReceiveStockForm(StyledMixin, forms.Form):
    reason = forms.ChoiceField(choices=[("purchase", "Stock received"), ("adjustment", "Adjustment (can be negative)")])
    qty = forms.DecimalField(required=False, max_digits=12, decimal_places=2, label="Quantity")
    serials = forms.CharField(required=False, label="Serial numbers (one per line)",
                              widget=forms.Textarea(attrs={"rows": 4}))
    note = forms.CharField(required=False, max_length=120, label="Note (supplier, invoice no.)")

ItemFormSet = inlineformset_factory(
    Document, DocumentItem, form=ItemForm, extra=1, can_delete=True)

from pathlib import Path
from django.core.exceptions import ValidationError

from .models import DeliveryItem, DeliveryNote


class DeliveryForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = DeliveryNote
        fields = ["delivery_date", "delivery_location", "delivered_by", "notes"]
        widgets = {
            "delivery_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class DeliveryItemForm(StyledMixin, forms.ModelForm):
    checks_text = forms.CharField(
        required=False, label="Checklist (one per line, end a line with : for a fill-in blank)",
        widget=forms.Textarea(attrs={"rows": 7}))

    class Meta:
        model = DeliveryItem
        fields = ["description", "category", "quantity", "serial_numbers"]
        widgets = {
            "quantity": forms.NumberInput(attrs={"step": "1", "min": "0"}),
            "serial_numbers": forms.Textarea(attrs={"rows": 4, "placeholder": "One per line (optional)"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["checks_text"].initial = "\n".join(self.instance.check_list)

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.checks = [ln.strip() for ln in self.cleaned_data.get("checks_text", "").splitlines() if ln.strip()]
        if commit:
            obj.save()
        return obj


DeliveryItemFormSet = inlineformset_factory(
    DeliveryNote, DeliveryItem, form=DeliveryItemForm, extra=1, can_delete=True)


class SignedCopyForm(forms.Form):
    received_by = forms.CharField(required=False, max_length=120, label="Received by (name on form)")
    signed_copy = forms.FileField(label="Signed copy (PDF or photo)")

    def clean_signed_copy(self):
        f = self.cleaned_data["signed_copy"]
        if Path(f.name).suffix.lower() not in {".pdf", ".jpg", ".jpeg", ".png", ".webp"}:
            raise ValidationError("Upload a PDF, JPG, PNG or WEBP scan.")
        if f.size > 10 * 1024 * 1024:
            raise ValidationError("File is larger than 10 MB.")
        return f