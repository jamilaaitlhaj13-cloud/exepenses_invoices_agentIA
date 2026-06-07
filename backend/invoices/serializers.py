from rest_framework import serializers
from .models import InvoiceRecord


class InvoiceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model  = InvoiceRecord
        fields = '__all__'
        read_only_fields = ['id', 'company', 'created_at', 'updated_at']


class InvoiceCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = InvoiceRecord
        exclude = ['company', 'created_at', 'updated_at']
        extra_kwargs = {
            'content_hash': {'required': False, 'default': ''},
        }


class InvoiceListSerializer(serializers.ModelSerializer):
    class Meta:
        model  = InvoiceRecord
        fields = [
            'id', 'vendor_name', 'invoice_date', 'invoice_id',
            'total_amount', 'currency', 'expense_category',
            'dit_confidence', 'status', 'source_filename',
            'source', 'created_at', 'excel_file',
        ]
