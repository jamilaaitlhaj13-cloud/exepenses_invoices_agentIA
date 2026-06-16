# tools/ocr_extraction_tool.py

import logging
from pathlib import Path
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult
from azure.core.credentials import AzureKeyCredential
from config.settings import AZURE_DOC_ENDPOINT, AZURE_DOC_KEY, OCR_CONFIDENCE_THRESHOLD
from models.invoice import Invoice

logger = logging.getLogger(__name__)
REQUIRED_FIELDS = ["VendorName", "InvoiceDate", "InvoiceTotal"]
class OCRExtractionTool:

    def __init__(self):
        from azure.core.pipeline.transport import RequestsTransport
        transport = RequestsTransport(connection_timeout=30, read_timeout=120)
        self._client = DocumentIntelligenceClient(
            endpoint=AZURE_DOC_ENDPOINT,
            credential=AzureKeyCredential(AZURE_DOC_KEY),
            transport=transport,
        )

    def extract(self, invoice: Invoice) -> Invoice:
        """
        Sends the file to Azure Document Intelligence
        and fills the Invoice object with extracted data.
        """
        if invoice.source_file is None:
            raise ValueError("source_file is required for OCR")
        file_path = invoice.source_file
        if not file_path.exists():
            raise FileNotFoundError(f"File not found : {file_path}")
        if file_path.stat().st_size == 0:
            raise ValueError(f"Empty file:{file_path.name}")
        logger.info(f"OCR processing: {file_path.name}")

        # Map extension to correct MIME type (Azure is strict about this for images)
        _mime_map = {
            ".pdf":  "application/pdf",
            ".jpg":  "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png":  "image/png",
            ".tiff": "image/tiff",
            ".tif":  "image/tiff",
            ".bmp":  "image/bmp",
        }
        content_type = _mime_map.get(file_path.suffix.lower(), "application/octet-stream")

        # Pre-check quota before calling SDK (avoids silent hang on 403)
        import requests as _requests
        _api_ver = "2024-11-30"
        _check = _requests.get(
            f"{AZURE_DOC_ENDPOINT.rstrip('/')}/documentintelligence/documentModels?api-version={_api_ver}",
            headers={"Ocp-Apim-Subscription-Key": AZURE_DOC_KEY},
            timeout=15,
        )
        if _check.status_code == 403:
            _msg = _check.json().get("error", {}).get("message", "Quota épuisé")
            raise RuntimeError(f"Azure quota épuisé (403): {_msg}")
        if _check.status_code == 401:
            raise RuntimeError("Clé Azure invalide ou expirée (401)")

        try:
            with open(file_path, "rb") as f:
                poller = self._client.begin_analyze_document(
                    model_id="prebuilt-invoice",
                    body=f,
                    content_type=content_type,
                )
            result: AnalyzeResult = poller.result(timeout=120)

        except Exception as e:
            raise RuntimeError(
                f"Azure Document Intelligence error: {e}"
            ) from e

        if not result.documents:
            raise ValueError(
                f"No document detected in '{file_path.name}'. "
                f"Please check the scan quality."
            )

        fields = result.documents[0].fields or {}
        self._fill_invoice(invoice, fields)

        logger.info(
            f"OCR successful: {invoice.vendor_name} | "
            f"{invoice.invoice_date} | "
            f"{invoice.total_amount} {invoice.currency}"
        )
        if invoice.dit_confidence is not None:
            logger.info(
                f"  DiT confidence : {invoice.dit_confidence:.3f} "
                f"(visual verification)"
            )
        return invoice

    def _fill_invoice(self, invoice: Invoice, fields: dict) -> None:
        """Iterates over fields returned by Azure and fills the Invoice object."""

        #String fields 
        string_fields = {
            "VendorName":                 "vendor_name",
            "VendorAddressRecipient":     "vendor_address_recipient",
            "VendorTaxId":                "vendor_tax_id",
            "CustomerName":               "customer_name",
            "CustomerId":                 "customer_id",
            "CustomerAddressRecipient":   "customer_address_recipient",
            "CustomerTaxId":              "customer_tax_id",
            "InvoiceId":                  "invoice_id",
            "PurchaseOrder":              "purchase_order",
            "KVKNumber":                  "kvk_number",
            "PaymentTerm":                "payment_term",
            "BillingAddressRecipient":    "billing_address_recipient",
            "ShippingAddressRecipient":   "shipping_address_recipient",
            "RemittanceAddressRecipient": "remittance_address_recipient",
            "ServiceAddressRecipient":    "service_address_recipient",
        }
        for azure_key, attr in string_fields.items():
            field = fields.get(azure_key)
            if field:
                self._check_confidence(azure_key, field.confidence)
                setattr(invoice, attr, field.value_string or field.content)

        #Address fields 
        address_fields = {
            "VendorAddress":     "vendor_address",
            "CustomerAddress":   "customer_address",
            "BillingAddress":    "billing_address",
            "ShippingAddress":   "shipping_address",
            "RemittanceAddress": "remittance_address",
            "ServiceAddress":    "service_address",
        }
        for azure_key, attr in address_fields.items():
            field = fields.get(azure_key)
            if field:
                setattr(invoice, attr, field.content)

        #Date fields 
        date_fields = {
            "InvoiceDate":      "invoice_date",
            "DueDate":          "due_date",
            "ServiceStartDate": "service_start_date",
            "ServiceEndDate":   "service_end_date",
        }
        for azure_key, attr in date_fields.items():
            field = fields.get(azure_key)
            if field:
                self._check_confidence(azure_key, field.confidence)
                if field.value_date:
                    setattr(invoice, attr,
                            field.value_date.strftime("%Y-%m-%d"))
                else:
                    setattr(invoice, attr, field.content)

        #Amount fields 
        amount_fields = {
            "SubTotal":              "subtotal",
            "TotalDiscount":         "total_discount",
            "TotalTax":              "tax_amount",
            "InvoiceTotal":          "total_amount",
            "AmountDue":             "amount_due",
            "PreviousUnpaidBalance": "previous_unpaid_balance",
        }
        for azure_key, attr in amount_fields.items():
            field = fields.get(azure_key)
            if field:
                self._check_confidence(azure_key, field.confidence)
                amount = self._parse_amount(field)
                if amount is not None:
                    setattr(invoice, attr, amount)
                    if (field.value_currency and
                            field.value_currency.currency_symbol):
                        invoice.currency = \
                            field.value_currency.currency_symbol

        #Line items 
        items_field = fields.get("Items")
        if items_field and items_field.value_array:
            for item in items_field.value_array:
                item_fields = item.value_object or {}
                invoice.items.append({
                    "description":  self._get_string(item_fields, "Description"),
                    "quantity":     self._get_number(item_fields, "Quantity"),
                    "unit":         self._get_string(item_fields, "Unit"),
                    "unit_price":   self._get_amount(item_fields, "UnitPrice"),
                    "amount":       self._get_amount(item_fields, "Amount"),
                    "product_code": self._get_string(item_fields, "ProductCode"),
                    "tax":          self._get_amount(item_fields, "Tax"),
                    "tax_rate":     self._get_string(item_fields, "TaxRate"),
                    "date":         self._get_date(item_fields,   "Date"),
                })

        #Payment details 
        payment_field = fields.get("PaymentDetails")
        if payment_field and payment_field.value_array:
            for p in payment_field.value_array:
                pf = p.value_object or {}
                invoice.payment_details.append({
                    "iban":                self._get_string(pf, "IBAN"),
                    "bank_account_number": self._get_string(pf, "BankAccountNumber"),
                    "swift":               self._get_string(pf, "SWIFT"),
                    "bpay_biller_code":    self._get_string(pf, "BPayBillerCode"),
                    "bpay_reference":      self._get_string(pf, "BPayReference"),
                })

        #Tax details 
        tax_field = fields.get("TaxDetails")
        if tax_field and tax_field.value_array:
            for t in tax_field.value_array:
                tf = t.value_object or {}
                invoice.tax_details.append({
                    "amount": self._get_amount(tf, "Amount"),
                    "rate":   self._get_string(tf, "Rate"),
                })

    #Utility methods 

    def _check_confidence(self, field_name: str,
                          confidence: float) -> None:
        if (field_name in REQUIRED_FIELDS and
                confidence is not None and
                confidence < OCR_CONFIDENCE_THRESHOLD):
            raise ValueError(
                f"Low confidence score on '{field_name}': "
                f"{confidence:.2f} < {OCR_CONFIDENCE_THRESHOLD}")

    def _parse_amount(self, field) -> float | None:
        if field.value_currency:
            return float(field.value_currency.amount or 0)
        try:
            cleaned = (
                str(field.content)
                .replace("\xa0", "")
                .replace(" ", "")
                .replace(",", ".")
                .replace("€", "")
                .replace("$", "")
                .replace("MAD", "")
                .replace("DH", "")
                .replace("dh", "")
                .replace("Dh", "")
                .replace("DHS", "")
                .replace("درهم", "")
                .strip()
            )
            return float(cleaned) if cleaned else None
        except (ValueError, AttributeError):
            return None

    def _get_string(self, fields: dict, key: str) -> str | None:
        f = fields.get(key)
        return (f.value_string or f.content) if f else None

    def _get_number(self, fields: dict, key: str) -> float | None:
        f = fields.get(key)
        if not f:
            return None
        try:
            return float(f.value_number or f.content)
        except (TypeError, ValueError):
            return None

    def _get_amount(self, fields: dict, key: str) -> float | None:
        f = fields.get(key)
        return self._parse_amount(f) if f else None

    def _get_date(self, fields: dict, key: str) -> str | None:
        f = fields.get(key)
        if not f:
            return None
        if f.value_date:
            return f.value_date.strftime("%Y-%m-%d")
        return f.content