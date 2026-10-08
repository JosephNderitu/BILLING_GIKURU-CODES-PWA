from django.urls import path
from . import views

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
]