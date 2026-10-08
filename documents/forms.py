from django import forms
from django.forms import inlineformset_factory

from .models import Document, DocumentItem

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
                  "discount", "payment_method", "payment_reference", "served_by", "notes", "terms"]
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
        drop = ["due_date", "terms"] if doc_type == Document.RECEIPT else \
               ["payment_method", "payment_reference", "served_by"]
        for name in drop:
            del self.fields[name]
        self.fields["status"].choices = STATUS_CHOICES[doc_type]
        if doc_type == Document.QUOTATION:
            self.fields["due_date"].label = "Valid until"


class ItemForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = DocumentItem
        fields = ["description", "serial_numbers", "quantity", "unit_price"]
        widgets = {
            "description": forms.TextInput(attrs={"placeholder": "Item or service"}),
            "serial_numbers": forms.Textarea(attrs={"rows": 1, "placeholder": "Serial numbers (optional)"}),
            "quantity": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "unit_price": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }


ItemFormSet = inlineformset_factory(
    Document, DocumentItem, form=ItemForm, extra=1, can_delete=True)