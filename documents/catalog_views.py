from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import ProductForm, ReceiveStockForm
from .models import DeliveryItem, Product, ProductSerial, StockMovement
from .views import paginate


@login_required
def product_list(request):
    qs = Product.objects.with_stock()
    q = request.GET.get("q", "").strip()
    cat = request.GET.get("category", "")
    flt = request.GET.get("filter", "")
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(sku__icontains=q))
    if cat:
        qs = qs.filter(category=cat)
    if flt == "inactive":
        qs = qs.filter(active=False)
    else:
        qs = qs.filter(active=True)
        if flt == "low":
            qs = qs.filter(track_stock=True, on_hand__lte=F("reorder_level"))
    page_obj, page_range, querystring = paginate(request, qs)
    return render(request, "documents/product_list.html", {
        "products": page_obj, "page_obj": page_obj, "page_range": page_range,
        "querystring": querystring, "categories": DeliveryItem.CATEGORIES,
        "f": {"q": q, "category": cat, "filter": flt}})


@login_required
def product_edit(request, pk=None):
    product = get_object_or_404(Product, pk=pk) if pk else Product()
    form = ProductForm(request.POST or None, instance=product)
    if request.method == "POST" and form.is_valid():
        p = form.save()
        messages.success(request, f"{p.name} saved.")
        return redirect("documents:product_detail", pk=p.pk)
    return render(request, "documents/product_form.html", {"form": form, "product": product})


@login_required
def product_detail(request, pk):
    p = get_object_or_404(Product, pk=pk)
    return render(request, "documents/product_detail.html", {
        "p": p, "on_hand": p.stock, "form": ReceiveStockForm(initial={"reason": "purchase"}),
        "movements": p.movements.select_related("document")[:25],
        "in_stock": p.serials.filter(status=ProductSerial.IN_STOCK)[:100],
        "sold": p.serials.filter(status=ProductSerial.SOLD).select_related("document")[:50]})


@login_required
@require_POST
@transaction.atomic
def product_receive(request, pk):
    p = get_object_or_404(Product, pk=pk)
    form = ReceiveStockForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Check the stock form and try again.")
        return redirect("documents:product_detail", pk=p.pk)

    reason = form.cleaned_data["reason"]
    qty = form.cleaned_data["qty"] or Decimal("0")
    if p.track_serials and reason == "purchase":
        added, dup = 0, []
        for sn in dict.fromkeys(s.strip() for s in form.cleaned_data["serials"].splitlines() if s.strip()):
            if ProductSerial.objects.filter(product=p, serial__iexact=sn).exists():
                dup.append(sn)
                continue
            ProductSerial.objects.create(product=p, serial=sn)
            added += 1
        qty = Decimal(added)
        if dup:
            messages.warning(request, f"Skipped existing serials: {', '.join(dup)}")
    if qty == 0:
        messages.error(request, "Nothing to record. Enter a quantity (or new serial numbers).")
        return redirect("documents:product_detail", pk=p.pk)

    StockMovement.objects.create(product=p, qty=qty, reason=reason, note=form.cleaned_data["note"])
    messages.success(request, f"Recorded {qty:+.0f} for {p.name}.")
    return redirect("documents:product_detail", pk=p.pk)