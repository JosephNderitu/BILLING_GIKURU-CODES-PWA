TYPE_META = {
    "quotation": {"label": "Quotation", "plural": "Quotations", "accent": "#1B2FA8", "icon": "fa-file-lines", "tw": "brand-blue"},
    "invoice":   {"label": "Invoice",   "plural": "Invoices",   "accent": "#16A34A", "icon": "fa-file-invoice-dollar", "tw": "brand-green"},
    "receipt":   {"label": "Receipt",   "plural": "Receipts",   "accent": "#F5B301", "icon": "fa-receipt", "tw": "brand-gold"},
}
STATUS_STYLES = {
    "draft": "bg-slate-100 text-slate-600",
    "sent": "bg-brand-blue/10 text-brand-blue",
    "accepted": "bg-brand-green/10 text-brand-green",
    "paid": "bg-brand-green/10 text-brand-green",
    "void": "bg-red-50 text-red-600",
    "overdue": "bg-brand-gold/20 text-yellow-800",
}

CHECKLISTS = {
    "computer": [
        "Unit received complete and undamaged",
        "Specs match the invoice (CPU, RAM, storage)",
        "Powers on and boots to Windows",
        "Windows installed and activated",
        "Windows version:",
        "Microsoft Office installed and activated",
        "Office version:",
        "Keyboard and mouse respond",
        "Network / Wi-Fi connects",
    ],
    "monitor": [
        "Received undamaged",
        "Powers on, clear display",
        "No dead pixels or lines",
        "Power and display cables included",
    ],
    "keyboard": ["Received undamaged", "All keys respond"],
    "mouse": ["Received undamaged", "Cursor and buttons respond"],
    "cable": ["Quantity and type correct", "Connectors undamaged"],
    "other": ["Received undamaged", "Working as expected"],
}

CATEGORY_KEYWORDS = [
    ("computer", ("optiplex", "desktop", "computer", "laptop", "cpu", "thinkpad", "elitebook",
                  "probook", "latitude", "all-in-one", "mini pc", "workstation")),
    ("monitor", ("monitor", "screen", "display")),
    ("keyboard", ("keyboard",)),
    ("mouse", ("mouse",)),
    ("cable", ("cable", "adapter", "charger", "hdmi", "vga", "power cord")),
]


def guess_category(text):
    t = (text or "").lower()
    for cat, words in CATEGORY_KEYWORDS:
        if any(w in t for w in words):
            return cat
    return "other"


DEFAULT_DELIVERY_TERMS = (
    "I confirm that the items listed above were delivered to me, tested in my presence and found "
    "complete and in good working condition, except where noted under Remarks. I have seen the "
    "equipment power on and the installed software working. Warranty terms are as stated on the "
    "invoice or receipt."
)