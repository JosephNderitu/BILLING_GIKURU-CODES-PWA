# documents/admin.py
from django.contrib import admin
from .models import BusinessProfile, Client, Document, DocumentItem


class ItemInline(admin.TabularInline):
    model = DocumentItem
    extra = 1


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("number", "doc_type", "display_client", "issue_date", "status")
    list_filter = ("doc_type", "status")
    search_fields = ("number", "client__name", "client_name")
    inlines = [ItemInline]


admin.site.register(BusinessProfile)
admin.site.register(Client)