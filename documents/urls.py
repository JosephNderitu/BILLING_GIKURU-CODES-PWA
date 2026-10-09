from django.urls import path
from . import views, catalog_views, report_views   # replace the existing import line

app_name = "documents"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("list/<str:doc_type>/", views.document_list, name="list"),
    path("new/<str:doc_type>/", views.document_create, name="create"),
    path("doc/<int:pk>/", views.document_detail, name="detail"),
    path("doc/<int:pk>/edit/", views.document_edit, name="edit"),
    path("doc/<int:pk>/preview/", views.document_preview, name="preview"),
    path("doc/<int:pk>/pdf/", views.document_pdf, name="pdf"),
    path("doc/<int:pk>/print/", views.receipt_print, name="print"),
    path("doc/<int:pk>/convert/<str:target>/", views.document_convert, name="convert"),
    path("doc/<int:pk>/status/", views.document_status, name="status"),
    path("verify/<str:number>/<str:code>/", views.verify, name="verify"),
    path("deliveries/", views.delivery_list, name="delivery_list"),
    path("doc/<int:doc_pk>/delivery/new/", views.delivery_create, name="delivery_create"),
    path("delivery/<int:pk>/", views.delivery_detail, name="delivery_detail"),
    path("delivery/<int:pk>/edit/", views.delivery_edit, name="delivery_edit"),
    path("delivery/<int:pk>/preview/", views.delivery_preview, name="delivery_preview"),
    path("delivery/<int:pk>/pdf/", views.delivery_pdf, name="delivery_pdf"),
    path("delivery/<int:pk>/upload/", views.delivery_upload, name="delivery_upload"),
    path("delivery/<int:pk>/signed/", views.delivery_signed_file, name="delivery_signed"),
    
    # share
    path("doc/<int:pk>/share/reset/", views.document_share_reset, name="share_reset"),
    path("s/<str:token>/", views.public_document, name="public"),
    path("s/<str:token>/preview/", views.public_preview, name="public_preview"),
    path("s/<str:token>/pdf/", views.public_pdf, name="public_pdf"),
    # products
    path("products/", catalog_views.product_list, name="product_list"),
    path("products/new/", catalog_views.product_edit, name="product_new"),
    path("products/<int:pk>/", catalog_views.product_detail, name="product_detail"),
    path("products/<int:pk>/edit/", catalog_views.product_edit, name="product_edit"),
    path("products/<int:pk>/receive/", catalog_views.product_receive, name="product_receive"),
    # reports
    path("reports/", report_views.sales, name="reports"),
    path("reports/sales/", report_views.sales, name="report_sales"),
    path("reports/vat/", report_views.vat, name="report_vat"),
    path("reports/aging/", report_views.aging, name="report_aging"),
    path("reports/statements/", report_views.statements, name="report_statements"),
]