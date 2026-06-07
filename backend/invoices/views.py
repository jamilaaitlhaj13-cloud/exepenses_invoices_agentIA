import os
from django.http import FileResponse, Http404
from django.db.models import Sum, Count, Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from .models import InvoiceRecord
from .serializers import InvoiceListSerializer, InvoiceCreateSerializer, InvoiceRecordSerializer


class InvoiceListCreateView(APIView):
    """GET /api/invoices/  — list  |  POST /api/invoices/ — create"""

    def get(self, request):
        qs = InvoiceRecord.objects.filter(company=request.user)

        # Filters
        status_filter   = request.query_params.get('status')
        category_filter = request.query_params.get('category')
        source_filter   = request.query_params.get('source')

        if status_filter:
            qs = qs.filter(status=status_filter)
        if category_filter:
            qs = qs.filter(expense_category=category_filter)
        if source_filter:
            qs = qs.filter(source=source_filter)

        serializer = InvoiceListSerializer(qs, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        serializer = InvoiceCreateSerializer(data=request.data)
        if serializer.is_valid():
            invoice = serializer.save(company=request.user)
            return Response(
                InvoiceRecordSerializer(invoice, context={'request': request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class InvoiceDetailView(APIView):
    """GET /api/invoices/{id}/"""

    def _get_invoice(self, pk, company):
        try:
            return InvoiceRecord.objects.get(pk=pk, company=company)
        except InvoiceRecord.DoesNotExist:
            raise Http404

    def get(self, request, pk):
        invoice    = self._get_invoice(pk, request.user)
        serializer = InvoiceRecordSerializer(invoice, context={'request': request})
        return Response(serializer.data)

    def delete(self, request, pk):
        invoice = self._get_invoice(pk, request.user)
        invoice.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvoiceUploadExcelView(APIView):
    """POST /api/invoices/{id}/upload_excel/ — attach Excel file to invoice record"""
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        try:
            invoice = InvoiceRecord.objects.get(pk=pk, company=request.user)
        except InvoiceRecord.DoesNotExist:
            raise Http404

        excel_file = request.FILES.get('excel_file')
        if not excel_file:
            return Response({'error': 'Aucun fichier fourni.'}, status=status.HTTP_400_BAD_REQUEST)

        invoice.excel_file = excel_file
        invoice.save()
        return Response({'excel_url': request.build_absolute_uri(invoice.excel_file.url)})


class InvoiceDownloadExcelView(APIView):
    """GET /api/invoices/{id}/excel/ — download Excel file"""

    def get(self, request, pk):
        try:
            invoice = InvoiceRecord.objects.get(pk=pk, company=request.user)
        except InvoiceRecord.DoesNotExist:
            raise Http404

        if not invoice.excel_file:
            return Response({'error': 'Aucun rapport Excel pour cette facture.'}, status=status.HTTP_404_NOT_FOUND)

        file_path = invoice.excel_file.path
        if not os.path.exists(file_path):
            return Response({'error': 'Fichier introuvable sur le serveur.'}, status=status.HTTP_404_NOT_FOUND)

        response = FileResponse(
            open(file_path, 'rb'),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
        return response


class InvoiceCheckHashView(APIView):
    """GET /api/invoices/check_hash/?hash=<md5> — vérifie si une facture a déjà été traitée"""

    def get(self, request):
        content_hash = request.query_params.get("hash", "").strip()
        if not content_hash:
            return Response({"error": "Paramètre 'hash' requis."}, status=400)
        exists = InvoiceRecord.objects.filter(
            company=request.user,
            content_hash=content_hash,
        ).exists()
        return Response({"exists": exists, "hash": content_hash})


class DashboardStatsView(APIView):
    """GET /api/invoices/stats/ — dashboard metrics for this company"""

    def get(self, request):
        qs = InvoiceRecord.objects.filter(company=request.user)

        total        = qs.count()
        validated    = qs.filter(status='validated').count()
        rejected     = qs.filter(status='rejected').count()
        need_review  = qs.filter(status='need_review').count()
        total_amount = qs.filter(status='validated').aggregate(
            s=Sum('total_amount')
        )['s'] or 0

        # By category
        by_category = list(
            qs.filter(status='validated')
              .values('expense_category')
              .annotate(count=Count('id'), amount=Sum('total_amount'))
              .order_by('-count')
        )

        # By source
        by_source = list(
            qs.values('source')
              .annotate(count=Count('id'))
        )

        # Recent 5
        recent = InvoiceListSerializer(
            qs[:5], many=True, context={'request': request}
        ).data

        return Response({
            'total':        total,
            'validated':    validated,
            'rejected':     rejected,
            'need_review':  need_review,
            'total_amount': float(total_amount),
            'by_category':  by_category,
            'by_source':    by_source,
            'recent':       recent,
        })
