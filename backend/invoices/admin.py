from django.contrib import admin
from .models import InvoiceRecord


@admin.register(InvoiceRecord)
class InvoiceAdmin(admin.ModelAdmin):
    list_display  = ['vendor_name', 'invoice_date', 'total_amount', 'currency',
                     'expense_category', 'status', 'company', 'created_at']
    list_filter   = ['status', 'expense_category', 'currency', 'source']
    search_fields = ['vendor_name', 'invoice_id', 'company__company_name']
    ordering      = ['-created_at']
