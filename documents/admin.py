import csv
from decimal import Decimal
from . import stock
from django.contrib import admin, messages
from django.db.models import Count, Max
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from .models import (BusinessProfile, Client, DeliveryItem, DeliveryNote,
                     Document, DocumentItem, Product, ProductSerial, StockMovement)

admin.site.site_header = "Gikuru Billing"
admin.site.site_title = "Gikuru Billing"
admin.site.index_title = "Business overview"


# ---------------------------------------------------------------- helpers
def money(value):
    return f"{value:,.2f}"


def pill(text, bg, fg="#fff"):
    return format_html(
        '<span style="display:inline-block;padding:.2rem .65rem;border-radius:999px;'
        'font-size:.72rem;font-weight:600;white-space:nowrap;background:{};color:{}">{}</span>',
        bg, fg, text)


TYPE_PILL = {"quotation": ("#1B2FA8", "#fff"), "invoice": ("#15803D", "#fff"),
             "receipt": ("#F5B301", "#0F172A")}
STATUS_PILL = {
    "draft": ("#E2E8F0", "#475569"), "sent": ("#DBEAFE", "#1B2FA8"),
    "accepted": ("#DCFCE7", "#15803D"), "paid": ("#DCFCE7", "#15803D"),
    "void": ("#FEE2E2", "#B91C1C"), "overdue": ("#FEF3C7", "#92400E"),
}


# ---------------------------------------------------------------- business profile
@admin.register(BusinessProfile)
class BusinessProfileAdmin(admin.ModelAdmin):
    """Singleton: one profile, edited in place. Changes apply to NEW documents only."""
    readonly_fields = ("logo_preview", "signature_preview", "stamp_preview")
    fieldsets = (
        ("Identity", {
            "description": "Edits apply to documents created from now on. Existing documents keep "
                           "the details they were issued with.",
            "fields": ("name", "tagline", "kra_pin"),
        }),
        ("Contact", {"fields": ("address", ("phone", "email"))}),
        ("Branding", {"fields": (
            ("logo", "logo_preview"), ("signature", "signature_preview"), ("stamp", "stamp_preview"))}),
        ("Payments and tax", {"fields": ("vat_rate", "payment_details")}),
        ("Document wording", {"fields": ("default_terms", "receipt_footer", "delivery_terms")}),
    )

    def has_add_permission(self, request):
        return not BusinessProfile.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = BusinessProfile.get()
        if obj:
            return redirect(reverse("admin:documents_businessprofile_change", args=[obj.pk]))
        return super().changelist_view(request, extra_context)

    def _preview(self, field):
        if not field:
            return "No file uploaded"
        return format_html(
            '<img src="{}" style="max-height:70px;max-width:180px;background:#fff;padding:6px;'
            'border:1px solid #E2E8F0;border-radius:8px">', field.url)

    @admin.display(description="Logo preview")
    def logo_preview(self, obj):
        return self._preview(obj.logo)

    @admin.display(description="Signature preview")
    def signature_preview(self, obj):
        return self._preview(obj.signature)

    @admin.display(description="Stamp preview")
    def stamp_preview(self, obj):
        return self._preview(obj.stamp)


# ---------------------------------------------------------------- clients
class ClientDocumentInline(admin.TabularInline):
    model = Document
    fk_name = "client"
    extra = 0
    max_num = 0
    can_delete = False
    show_change_link = True
    verbose_name_plural = "Documents for this client"
    fields = ("number", "doc_type", "issue_date", "status", "total_col")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Total (KSh)")
    def total_col(self, obj):
        return money(obj.total)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email", "kra_pin", "docs_col", "last_col")
    search_fields = ("name", "phone", "email", "kra_pin")
    ordering = ("name",)
    list_per_page = 25
    inlines = [ClientDocumentInline]
    fieldsets = (
        (None, {"fields": ("name",)}),
        ("Contact", {"fields": (("phone", "email"), "address")}),
        ("Tax", {"fields": ("kra_pin",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _docs=Count("document", distinct=True), _last=Max("document__issue_date"))

    @admin.display(description="Documents", ordering="_docs")
    def docs_col(self, obj):
        url = f'{reverse("admin:documents_document_changelist")}?client__id__exact={obj.pk}'
        return format_html('<a href="{}">{} document(s)</a>', url, obj._docs)

    @admin.display(description="Last activity", ordering="_last")
    def last_col(self, obj):
        return obj._last.strftime("%d %b %Y") if obj._last else "-"


# ---------------------------------------------------------------- documents
class PaymentFilter(admin.SimpleListFilter):
    title = "payment"
    parameter_name = "payment"

    def lookups(self, request, model_admin):
        return [("overdue", "Overdue invoices"), ("unpaid", "Unpaid invoices"),
                ("paid", "Paid and receipted")]

    def queryset(self, request, queryset):
        if self.value() == "overdue":
            return queryset.filter(doc_type="invoice", status="sent",
                                   due_date__lt=timezone.localdate())
        if self.value() == "unpaid":
            return queryset.filter(doc_type="invoice", status__in=["draft", "sent"])
        if self.value() == "paid":
            return queryset.filter(status="paid")
        return queryset


class ItemInline(admin.TabularInline):
    model = DocumentItem
    extra = 1
    fields = ("Product", "description", "serial_numbers", "quantity", "unit_price", "line_total_col")
    autocomplete_fields = ("product",)
    readonly_fields = ("line_total_col",)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "serial_numbers":
            field.widget.attrs.update({"rows": 2, "cols": 26, "placeholder": "One per line"})
        if db_field.name == "description":
            field.widget.attrs.update({"style": "min-width:280px"})
        return field

    @admin.display(description="Line total")
    def line_total_col(self, obj):
        return money(obj.line_total) if obj.pk else "-"


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("number_col", "type_col", "client_col", "issue_date", "due_col",
                    "status_col", "total_col", "links_col")
    list_display_links = ("number_col",)
    list_filter = (
        "doc_type", "status", PaymentFilter,
        ("issue_date", admin.DateFieldListFilter),
        ("client", admin.RelatedOnlyFieldListFilter),
        "vat_mode", "payment_method",
    )
    search_fields = ("number", "client__name", "client_name", "payment_reference",
                     "items__description", "items__serial_numbers")
    search_help_text = "Search by number, client, item, serial number or payment reference"
    date_hierarchy = "issue_date"
    ordering = ("-created_at",)
    list_per_page = 25
    save_on_top = True
    autocomplete_fields = ("client",)
    inlines = [ItemInline]
    actions = ["mark_sent", "mark_accepted", "mark_paid", "mark_void", "export_csv"]

    fieldsets = (
        ("Document", {"fields": (("doc_type", "number"), ("status", "vat_mode"),
                                 ("issue_date", "due_date"))}),
        ("Client", {"fields": ("client", "client_name")}),
        ("Payment and service", {"fields": (("payment_method", "payment_reference"),
                                            ("served_by", "discount"))}),
        ("eTIMS (KRA)", {"fields": ("buyer_pin", "etims_invoice_no", "etims_qr"), "classes": ("collapse",)}),
        ("Notes and terms", {"fields": ("notes", "terms"), "classes": ("collapse",)}),
        ("Summary", {"fields": ("totals_summary", "source_link", "issuer_details", "created_at")}),
    )

    # ---- queryset, defaults, saving
    def get_queryset(self, request):
        return super().get_queryset(request).select_related("client").prefetch_related("items")

    def get_readonly_fields(self, request, obj=None):
        base = ["number", "totals_summary", "source_link", "issuer_details", "created_at"]
        return base + (["doc_type"] if obj else [])

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        profile = BusinessProfile.get()
        if profile:
            initial.setdefault("terms", profile.default_terms)
        if request.GET.get("doc_type") == Document.RECEIPT:
            initial.update({"status": "paid", "payment_method": "cash", "terms": ""})
            initial.setdefault("served_by", request.user.get_full_name() or request.user.get_username())
        return initial

    def save_model(self, request, obj, form, change):
        if not change and obj.doc_type == Document.RECEIPT and not obj.served_by:
            obj.served_by = request.user.get_full_name() or request.user.get_username()
        super().save_model(request, obj, form, change)

    # ---- KPI strip above the list (respects the active filters)
    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        try:
            qs = response.context_data["cl"].queryset
        except (AttributeError, KeyError):
            return response
        docs = list(qs[:2000])  # plenty for an SME; keeps the page fast
        open_inv = [d for d in docs if d.doc_type == "invoice" and d.status in ("draft", "sent")]
        response.context_data["kpis"] = {
            "count": len(docs),
            "total": money(sum((d.total for d in docs), Decimal("0"))),
            "outstanding": money(sum((d.total for d in open_inv), Decimal("0"))),
            "overdue": sum(1 for d in open_inv if d.is_overdue),
        }
        return response

    # ---- list columns
    @admin.display(description="Number", ordering="number")
    def number_col(self, obj):
        return format_html("<b>{}</b>", obj.number)

    @admin.display(description="Type", ordering="doc_type")
    def type_col(self, obj):
        bg, fg = TYPE_PILL[obj.doc_type]
        return pill(obj.get_doc_type_display(), bg, fg)

    @admin.display(description="Client", ordering="client__name")
    def client_col(self, obj):
        return obj.display_client

    @admin.display(description="Due", ordering="due_date")
    def due_col(self, obj):
        if not obj.due_date:
            return "-"
        text = obj.due_date.strftime("%d %b %Y")
        if obj.is_overdue:
            return format_html('<span style="color:#B91C1C;font-weight:600">{}</span>', text)
        return text

    @admin.display(description="Status", ordering="status")
    def status_col(self, obj):
        bg, fg = STATUS_PILL["overdue" if obj.is_overdue else obj.status]
        return pill(obj.status_label, bg, fg)

    @admin.display(description="Total (KSh)")
    def total_col(self, obj):
        return format_html('<b style="font-variant-numeric:tabular-nums">{}</b>', money(obj.total))

    @admin.display(description="")
    def links_col(self, obj):
        return format_html(
            '<a href="{}" target="_blank" class="btn btn-xs btn-outline-success mr-1">PDF</a>'
            '<a href="{}" target="_blank" class="btn btn-xs btn-outline-secondary">Open</a>',
            reverse("documents:pdf", args=[obj.pk]), reverse("documents:detail", args=[obj.pk]))

    # ---- read-only blocks on the form
    @admin.display(description="Totals")
    def totals_summary(self, obj):
        if not obj.pk:
            return "Save the document to see totals."
        rows = [("Items total", obj.items_total)]
        if obj.discount:
            rows.append(("Discount", -obj.discount))
        rows.append(("Subtotal", obj.net_amount))
        if obj.vat_mode != "none":
            rows.append((f"VAT ({obj.vat_rate:.0f}%)", obj.vat_amount))
        body = format_html_join(
            "", '<tr><td style="padding:.2rem 1.5rem .2rem 0;color:#64748B">{}</td>'
                '<td style="text-align:right;font-variant-numeric:tabular-nums">{}</td></tr>',
            ((label, money(val)) for label, val in rows))
        return format_html(
            '<table>{}<tr><td style="padding-top:.4rem;font-weight:700">Total (KSh)</td>'
            '<td style="padding-top:.4rem;text-align:right;font-weight:700;font-size:1.1rem">{}</td>'
            '</tr></table>', body, money(obj.total))

    @admin.display(description="Created from")
    def source_link(self, obj):
        if not obj.source_id:
            return "-"
        url = reverse("admin:documents_document_change", args=[obj.source_id])
        return format_html('<a href="{}">{}</a>', url, obj.source.number)

    @admin.display(description="Issued under (frozen)")
    def issuer_details(self, obj):
        if not obj.pk:
            return "-"
        b = obj.biz
        return format_html("{}<br>{}<br>KRA PIN: {}<br>VAT rate: {}%",
                           b.name, b.phone, b.kra_pin or "-", obj.vat_rate)

    # ---- bulk actions
    @admin.action(description="Mark selected as Sent", permissions=["change"])
    def mark_sent(self, request, queryset):
        n = queryset.filter(status="draft", doc_type__in=["quotation", "invoice"]).update(status="sent")
        self.message_user(request, f"{n} document(s) marked sent.", messages.SUCCESS)

    @admin.action(description="Mark selected quotations as Accepted", permissions=["change"])
    def mark_accepted(self, request, queryset):
        n = queryset.filter(doc_type="quotation", status__in=["draft", "sent"]).update(status="accepted")
        self.message_user(request, f"{n} quotation(s) accepted.", messages.SUCCESS)

    @admin.action(description="Mark selected invoices as Paid", permissions=["change"])
    def mark_paid(self, request, queryset):
        n = queryset.filter(doc_type="invoice", status__in=["draft", "sent"]).update(status="paid")
        self.message_user(
            request, f"{n} invoice(s) marked paid. Use Issue Receipt in the app to also print a receipt.",
            messages.SUCCESS)

    @admin.action(description="Void selected documents", permissions=["change"])
    def mark_void(self, request, queryset):
        n = queryset.exclude(status="void").update(status="void")
        self.message_user(request, f"{n} document(s) voided.", messages.WARNING)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        for w in stock.sync_document(form.instance):
            messages.warning(request, w)

    def _resync(self, queryset):
        for d in queryset:
            stock.sync_document(d)
            
    @admin.action(description="Export selected to CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="documents.csv"'
        response.write("\ufeff")  # lets Excel read UTF-8 correctly
        w = csv.writer(response)
        w.writerow(["Number", "Type", "Client", "Issue date", "Due date", "Status", "VAT mode",
                    "Subtotal", "VAT", "Total", "Payment method", "Reference"])
        for d in queryset.select_related("client").prefetch_related("items"):
            w.writerow([d.number, d.get_doc_type_display(), d.display_client, d.issue_date,
                        d.due_date or "", d.status_label, d.get_vat_mode_display(),
                        d.net_amount, d.vat_amount, d.total,
                        d.get_payment_method_display(), d.payment_reference])
        return response


# ---------------------------------------------------------------- delivery notes
class SignatureFilter(admin.SimpleListFilter):
    title = "signature"
    parameter_name = "signature"

    def lookups(self, request, model_admin):
        return [("pending", "Awaiting signed copy"), ("signed", "Signed")]

    def queryset(self, request, queryset):
        if self.value() == "pending":
            return queryset.filter(signed_copy="")
        if self.value() == "signed":
            return queryset.exclude(signed_copy="")
        return queryset


class DeliveryItemInline(admin.TabularInline):
    model = DeliveryItem
    extra = 0
    fields = ("description", "category", "quantity", "serial_numbers", "checks_col")
    readonly_fields = ("checks_col",)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "serial_numbers":
            field.widget.attrs.update({"rows": 2, "cols": 26})
        return field

    @admin.display(description="Checklist")
    def checks_col(self, obj):
        return f"{len(obj.check_list)} checks" if obj.pk else "-"


@admin.register(DeliveryNote)
class DeliveryNoteAdmin(admin.ModelAdmin):
    list_display = ("number_col", "sale_col", "client_col", "delivery_date",
                    "signature_col", "received_by", "links_col")
    list_display_links = ("number_col",)
    list_filter = (SignatureFilter, ("delivery_date", admin.DateFieldListFilter), "delivered_by")
    search_fields = ("number", "document__number", "document__client__name",
                     "document__client_name", "received_by", "items__serial_numbers")
    search_help_text = "Search by delivery note, sale number, client, receiver or serial number"
    date_hierarchy = "delivery_date"
    ordering = ("-created_at",)
    list_per_page = 25
    save_on_top = True
    autocomplete_fields = ("document",)
    inlines = [DeliveryItemInline]
    readonly_fields = ("number", "created_at", "signed_preview")

    fieldsets = (
        ("Delivery", {"fields": ("number", "document", ("delivery_date", "delivered_by"),
                                 "delivery_location", "notes")}),
        ("Customer signature", {"fields": ("signed_copy", "signed_preview", "received_by", "signed_at")}),
        ("Record", {"fields": ("created_at",), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("document", "document__client")

    def save_model(self, request, obj, form, change):
        if obj.signed_copy and not obj.signed_at:
            obj.signed_at = timezone.now()
        super().save_model(request, obj, form, change)

    @admin.display(description="Delivery note", ordering="number")
    def number_col(self, obj):
        return format_html("<b>{}</b>", obj.number)

    @admin.display(description="Sale", ordering="document__number")
    def sale_col(self, obj):
        url = reverse("admin:documents_document_change", args=[obj.document_id])
        return format_html('<a href="{}">{}</a>', url, obj.document.number)

    @admin.display(description="Client", ordering="document__client__name")
    def client_col(self, obj):
        return obj.document.display_client

    @admin.display(description="Signature")
    def signature_col(self, obj):
        if obj.is_signed:
            return pill("Signed", *STATUS_PILL["paid"])
        return pill("Awaiting copy", *STATUS_PILL["overdue"])

    @admin.display(description="")
    def links_col(self, obj):
        return format_html(
            '<a href="{}" target="_blank" class="btn btn-xs btn-outline-success mr-1">Form</a>'
            '<a href="{}" target="_blank" class="btn btn-xs btn-outline-secondary">Open</a>',
            reverse("documents:delivery_pdf", args=[obj.pk]),
            reverse("documents:delivery_detail", args=[obj.pk]))

    @admin.display(description="Signed copy preview")
    def signed_preview(self, obj):
        if not obj.pk or not obj.is_signed:
            return "No signed copy uploaded yet"
        url = reverse("documents:delivery_signed", args=[obj.pk])
        if obj.signed_is_image:
            return format_html(
                '<a href="{0}" target="_blank"><img src="{0}" style="max-height:220px;max-width:100%;'
                'border:1px solid #E2E8F0;border-radius:8px"></a>', url)
        return format_html('<a href="{}" target="_blank" class="btn btn-sm btn-outline-success">'
                           'Open signed PDF</a>', url)
        
        
class SerialInline(admin.TabularInline):
    model = ProductSerial
    extra = 0
    fields = ("serial", "status", "document")
    readonly_fields = ("document",)


class MovementInline(admin.TabularInline):
    model = StockMovement
    extra = 0
    can_delete = False
    fields = ("created_at", "qty", "reason", "document", "note")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "unit_price", "stock_col", "tracking_col", "active")
    list_filter = ("category", "active", "track_stock", "track_serials")
    search_fields = ("name", "sku")
    list_editable = ("active",)
    inlines = [SerialInline, MovementInline]

    def get_queryset(self, request):
        return super().get_queryset(request).with_stock()

    @admin.display(description="On hand", ordering="on_hand")
    def stock_col(self, obj):
        if not obj.track_stock:
            return "-"
        low = obj.on_hand <= obj.reorder_level
        return format_html('<b style="color:{}">{}</b>', "#B91C1C" if low else "#15803D", f"{obj.on_hand:,.0f}")

    @admin.display(description="Tracking")
    def tracking_col(self, obj):
        return "Stock + serials" if obj.track_serials else ("Stock" if obj.track_stock else "-")
    
