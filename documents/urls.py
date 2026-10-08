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
]