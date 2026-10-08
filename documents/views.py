from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string

from .forms import DocumentForm, ItemFormSet
from .meta import TYPE_META
from .models import BusinessProfile, Document
from .pdf import build_context, build_pdf, template_for
import hmac
from datetime import timedelta

from django.core.paginator import Paginator
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from .forms import DocumentForm, ItemFormSet, STATUS_CHOICES
from .models import BusinessProfile, Document, DocumentItem


def _check(doc_type):
    if doc_type not in TYPE_META:
        raise Http404

CONVERT = {("quotation", "invoice"), ("invoice", "receipt")}
PER_PAGE = 15


def paginate(request, qs, per_page=PER_PAGE):
    """Reusable: returns page_obj, page_range and a querystring that keeps filters across pages."""
    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(request.GET.get("page"))
    page_range = list(paginator.get_elided_page_range(page_obj.number, on_each_side=1, on_ends=1))
    params = request.GET.copy()
    params.pop("page", None)
    return page_obj, page_range, params.urlencode()


def _date(value):
    try:
        return parse_date(value) if value else None
    except ValueError:
        return None


@login_required
def dashboard(request):
    today = timezone.localdate()
    open_invoices = list(Document.objects.filter(doc_type="invoice", status__in=["draft", "sent"])
                         .prefetch_related("items"))
    month_receipts = Document.objects.filter(
        doc_type="receipt", status="paid", issue_date__year=today.year,
        issue_date__month=today.month).prefetch_related("items")
    ctx = {
        "types": TYPE_META,
        "docs": Document.objects.select_related("client").prefetch_related("items")[:8],
        "counts": {k: Document.objects.filter(doc_type=k).count() for k in TYPE_META},
        "outstanding": sum(d.total for d in open_invoices),
        "overdue_count": sum(1 for d in open_invoices if d.is_overdue),
        "collected": sum(d.total for d in month_receipts),
    }
    return render(request, "documents/dashboard.html", ctx)


@login_required
def document_list(request, doc_type):
    _check(doc_type)
    qs = (Document.objects.filter(doc_type=doc_type)
          .select_related("client").prefetch_related("items"))
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    d_from, d_to = request.GET.get("from", ""), request.GET.get("to", "")

    if q:
        qs = qs.filter(Q(number__icontains=q) | Q(client__name__icontains=q) | Q(client_name__icontains=q))
    if status == "overdue":
        qs = qs.filter(doc_type="invoice", status="sent", due_date__lt=timezone.localdate())
    elif status:
        qs = qs.filter(status=status)
    if _date(d_from):
        qs = qs.filter(issue_date__gte=_date(d_from))
    if _date(d_to):
        qs = qs.filter(issue_date__lte=_date(d_to))

    page_obj, page_range, querystring = paginate(request, qs)
    statuses = list(STATUS_CHOICES[doc_type]) + ([("overdue", "Overdue")] if doc_type == "invoice" else [])
    return render(request, "documents/document_list.html", {
        "docs": page_obj, "page_obj": page_obj, "page_range": page_range,
        "querystring": querystring, "meta": TYPE_META[doc_type], "doc_type": doc_type,
        "statuses": statuses, "f": {"q": q, "status": status, "from": d_from, "to": d_to}})


@login_required
def document_detail(request, pk):
    doc = get_object_or_404(Document, pk=pk)
    return render(request, "documents/document_detail.html", {
        "doc": doc, "meta": TYPE_META[doc.doc_type],
        "status_choices": STATUS_CHOICES[doc.doc_type],
        "converted": list(doc.converted.all())})


@login_required
@require_POST
@transaction.atomic
def document_convert(request, pk, target):
    src = get_object_or_404(Document, pk=pk)
    if (src.doc_type, target) not in CONVERT or src.status == "void":
        raise Http404
    existing = src.converted.filter(doc_type=target).first()
    if existing:
        messages.info(request, f"Already converted to {existing.number}.")
        return redirect("documents:detail", pk=existing.pk)

    profile = BusinessProfile.get()
    new = Document(doc_type=target, client=src.client, client_name=src.client_name,
                   discount=src.discount, vat_mode=src.vat_mode, notes=src.notes, source=src)
    if target == "invoice":
        new.status = "draft"
        new.terms = profile.default_terms if profile else ""
        new.due_date = timezone.localdate() + timedelta(days=14)
        src.status = "accepted"
    else:
        new.status = "paid"
        new.payment_method = "cash"
        new.served_by = request.user.get_full_name() or request.user.username
        src.status = "paid"
    new.save()
    DocumentItem.objects.bulk_create([
        DocumentItem(document=new, description=i.description, serial_numbers=i.serial_numbers,
                     quantity=i.quantity, unit_price=i.unit_price) for i in src.items.all()])
    src.save(update_fields=["status"])

    messages.success(request, f"{src.number} converted to {new.number}.")
    # Receipts open in edit so the payment method and reference can be confirmed
    return redirect("documents:edit" if target == "receipt" else "documents:detail", pk=new.pk)


@login_required
@require_POST
def document_status(request, pk):
    doc = get_object_or_404(Document, pk=pk)
    new = request.POST.get("status")
    if new in dict(STATUS_CHOICES[doc.doc_type]):
        doc.status = new
        doc.save(update_fields=["status"])
        messages.success(request, f"{doc.number} marked {doc.get_status_display().lower()}.")
    return redirect("documents:detail", pk=doc.pk)


def verify(request, number, code):
    """Public page opened by scanning the receipt QR. Shows no customer or item details."""
    doc = Document.objects.filter(number=number).first()
    ok = bool(doc) and hmac.compare_digest(code, doc.verify_code)
    return render(request, "documents/verify.html",
                  {"doc": doc if ok else None, "p": doc.biz if ok else None})
    

def _editor(request, doc, doc_type):
    profile = BusinessProfile.get()
    if request.method == "POST":
        form = DocumentForm(request.POST, instance=doc, doc_type=doc_type)
        formset = ItemFormSet(request.POST, instance=doc)
        if form.is_valid() and formset.is_valid():
            saved = form.save()
            formset.instance = saved
            formset.save()
            messages.success(request, f"{saved.number} saved.")
            return redirect("documents:detail", pk=saved.pk)
    else:
        initial = {}
        if doc.pk is None:
            if doc_type == Document.RECEIPT:
                initial = {"status": "paid", "payment_method": "cash",
                           "served_by": request.user.get_full_name() or request.user.username}
            else:
                initial = {"terms": profile.default_terms if profile else ""}
        form = DocumentForm(instance=doc, doc_type=doc_type, initial=initial)
        formset = ItemFormSet(instance=doc)
    return render(request, "documents/document_form.html", {
        "form": form, "formset": formset, "doc": doc, "meta": TYPE_META[doc_type],
        "doc_type": doc_type, "vat_rate": doc.vat_rate})


@login_required
def document_create(request, doc_type):
    _check(doc_type)
    return _editor(request, Document(doc_type=doc_type), doc_type)


@login_required
def document_edit(request, pk):
    doc = get_object_or_404(Document, pk=pk)
    return _editor(request, doc, doc.doc_type)


@login_required
def document_detail(request, pk):
    doc = get_object_or_404(Document, pk=pk)
    return render(request, "documents/document_detail.html", {"doc": doc, "meta": TYPE_META[doc.doc_type]})


@login_required
def document_preview(request, pk):
    doc = get_object_or_404(Document, pk=pk)
    return render(request, template_for(doc), build_context(doc, False))


@login_required
def receipt_print(request, pk):
    doc = get_object_or_404(Document, pk=pk, doc_type=Document.RECEIPT)
    return render(request, template_for(doc), build_context(doc, False, toolbar=True))


@login_required
def document_pdf(request, pk):
    doc = get_object_or_404(Document, pk=pk)
    resp = HttpResponse(build_pdf(doc, request), content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{doc.number}.pdf"'
    return resp