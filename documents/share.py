import re
from urllib.parse import quote

from django.conf import settings
from django.urls import reverse


def base_url(request):
    return (getattr(settings, "SITE_URL", "") or request.build_absolute_uri("/")).rstrip("/")


def wa_phone(raw):
    """Kenyan numbers to wa.me format (digits, country code, no plus)."""
    d = re.sub(r"\D", "", raw or "")
    if not d or d.startswith("254"):
        return d
    if d.startswith("0"):
        return "254" + d[1:]
    if len(d) == 9 and d[0] in "17":
        return "254" + d
    return d


def share_url(request, doc):
    return base_url(request) + reverse("documents:public", args=[doc.ensure_share_token()])


def whatsapp_url(request, doc):
    kind = doc.get_doc_type_display().lower()
    text = (f"Hello {doc.display_client}, here is your {kind} {doc.number} from {doc.biz.name} "
            f"for KSh {doc.total:,.2f}.\n{share_url(request, doc)}")
    phone = wa_phone(doc.client.phone if doc.client else "")
    return f"https://wa.me/{phone}?text={quote(text)}"