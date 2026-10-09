from django.db import transaction

from .models import ProductSerial, StockMovement


@transaction.atomic
def sync_document(doc):
    """Rebuild stock movements and serial status for one document. Returns warning strings."""
    warnings = []
    StockMovement.objects.filter(document=doc, reason=StockMovement.SALE).delete()
    ProductSerial.objects.filter(document=doc).update(status=ProductSerial.IN_STOCK, document=None)
    if not doc.is_sale:
        return warnings

    for item in doc.items.select_related("product"):
        p = item.product
        if not p or not p.track_stock:
            continue
        StockMovement.objects.create(product=p, qty=-item.quantity, reason=StockMovement.SALE,
                                     document=doc, note=doc.number)
        if not p.track_serials:
            continue
        serials = item.serials
        if len(serials) != int(item.quantity):
            warnings.append(f"{p.name}: {len(serials)} serial number(s) entered for {item.quantity:.0f} unit(s).")
        for sn in serials:
            row = ProductSerial.objects.filter(product=p, serial__iexact=sn).first()
            if row is None:
                warnings.append(f"Serial {sn} is not registered in stock for {p.name}.")
            elif row.status == ProductSerial.SOLD and row.document_id not in (None, doc.pk):
                warnings.append(f"Serial {sn} is already sold on another document.")
            else:
                row.status, row.document = ProductSerial.SOLD, doc
                row.save(update_fields=["status", "document"])
    return warnings