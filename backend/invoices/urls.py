from django.urls import path
from .views import (
    InvoiceListCreateView,
    InvoiceDetailView,
    InvoiceUploadExcelView,
    InvoiceDownloadExcelView,
    InvoiceCheckHashView,
    DashboardStatsView,
)

urlpatterns = [
    path('',                            InvoiceListCreateView.as_view(),   name='invoice-list'),
    path('stats/',                      DashboardStatsView.as_view(),      name='invoice-stats'),
    path('check_hash/',                 InvoiceCheckHashView.as_view(),    name='invoice-check-hash'),
    path('<int:pk>/',                   InvoiceDetailView.as_view(),        name='invoice-detail'),
    path('<int:pk>/upload_excel/',      InvoiceUploadExcelView.as_view(),   name='invoice-upload-excel'),
    path('<int:pk>/excel/',             InvoiceDownloadExcelView.as_view(), name='invoice-download-excel'),
]
