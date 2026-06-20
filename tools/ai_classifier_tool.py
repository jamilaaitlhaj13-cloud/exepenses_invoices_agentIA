# tools/ai_classifier_tool.py

import json
import logging
import re
from datetime import datetime

from langchain_openai import AzureChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from config.settings import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    AZURE_OPENAI_DEPLOYMENT,
    AZURE_OPENAI_API_VERSION,
    LLM_TEMPERATURE,
)
from models.invoice import Invoice

logger = logging.getLogger(__name__)

EXPENSE_CATEGORIES = [
    "SaaS",
    "Travel",
    "Office",
    "Utilities",
    "IT Hardware",
    "Consulting & Services",
    "Marketing & Communication",
    "Legal & Compliance",
    "Maintenance & Repair",
    "Food & Catering",
    "Training & Education",
    "Insurance",
    "Rent & Real Estate",
    "Raw Materials & Inventory",
    "Healthcare & Medical",
    "Logistics & Delivery",
    "HR & Recruitment",
    "Other",
]

CATEGORIES_STR = " or ".join(EXPENSE_CATEGORIES)

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SYSTEM_PROMPT = """\
You are an expert accounting assistant specialized in invoice processing.
You receive data extracted by OCR from an invoice.
Your tasks :
  1. DO NOT add or invent missing fields — keep them as null.
  2. If a field exists but is badly formatted, reformat it correctly.
  3. Classify the expense into the correct category.
Respond ONLY with a valid JSON object.
No text before or after. No backticks.\
"""

USER_PROMPT = f"""\
Here is the OCR data extracted from the invoice :
{{ocr_data}}

Return a JSON with exactly this structure :
{{{{
  "vendor_name":       "Vendor name — clean the text if needed, or null",
  "invoice_date":      "YYYY-MM-DD — reformat if needed (e.g. 30/10/2024 → 2024-10-30), or null",
  "invoice_id":        "Invoice number or null",
  "subtotal":          subtotal as clean float or null,
  "tax_amount":        tax amount as clean float or null,
  "total_amount":      total amount as clean float or null,
  "currency":          "MAD or EUR or USD — standardize if needed",
  "expense_category":  "{CATEGORIES_STR}",
  "llm_confidence":    "high or medium or low"
}}}}

Reformatting rules :
- Dates    : always convert to YYYY-MM-DD format
- Amounts  : always return as float (remove currency symbols, spaces, commas)
- vendor_name : remove extra spaces or line breaks
- currency : standardize to MAD, EUR or USD

Classification rules :
- Microsoft, AWS, GitHub, Zoom, Salesforce, Google Cloud,
  Adobe, Slack, Notion, Jira, Azure, Office365             → "SaaS"
- Flights, hotels, taxis, Uber, restaurants on travel,
  train, car rental, SNCF, Air Arabia, Royal Air Maroc      → "Travel"
- Supplies, printer, furniture, office equipment,
  stationery, paper, Staples                                → "Office"
- Electricity, water, internet, phone, gas, telecom,
  network, Maroc Telecom, Orange, Inwi                      → "Utilities"
- Dell, HP, Lenovo, Apple, Cisco, servers, screens,
  keyboards, hard drives, laptops, hardware                 → "IT Hardware"
- Consulting, audit, training, professional services,
  agency, freelance, coaching, PricewaterhouseCoopers,
  Deloitte, McKinsey                                        → "Consulting & Services"
- Advertising, marketing, printing, design, branding,
  events, social media, studio, creative agency             → "Marketing & Communication"
- Lawyer, notary, legal fees, compliance,
  cabinet juridique, audit juridique                        → "Legal & Compliance"
- Maintenance, repair, cleaning, security, gardening,
  technical support, facility management                    → "Maintenance & Repair"
- Restaurant, catering, cafeteria, meal, food delivery,
  traiteur, repas d'affaires, sodexo, lunch                → "Food & Catering"
- Training, e-learning, certification, Coursera, Udemy,
  formation, workshop, conference registration, seminar     → "Training & Education"
- Insurance premium, assurance, wafa assurance, AXA,
  CNSS, AMO, mutuelle, RMA, coverage, police d'assurance   → "Insurance"
- Rent, lease, loyer, bail, real estate, office space,
  warehouse rental, agence immobilière, property           → "Rent & Real Estate"
- Raw materials, matières premières, stock, inventory,
  supplies wholesale, goods purchase, fabric, metal,
  components, packaging                                     → "Raw Materials & Inventory"
- Doctor, clinic, pharmacy, hospital, medical,
  optician, dentist, pharmacie, clinique, healthcare       → "Healthcare & Medical"
- Shipping, delivery, transport, DHL, FedEx, Amana,
  courier, freight, logistics, colissimo, transit          → "Logistics & Delivery"
- Recruitment, staffing, job posting, LinkedIn Talent,
  headhunter, interim, RH, payroll services, HR            → "HR & Recruitment"
- Everything else                                           → "Other"\
"""
class AIClassifierTool:

    def __init__(self):
        self._llm = AzureChatOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_KEY,
            azure_deployment=AZURE_OPENAI_DEPLOYMENT,
            api_version=AZURE_OPENAI_API_VERSION,
            temperature=LLM_TEMPERATURE,
            request_timeout=60,
        )
        self._parser = JsonOutputParser()
        self._prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("user",   USER_PROMPT),
        ])
        self._chain = self._prompt | self._llm | self._parser

    def classify(self, invoice: Invoice) -> Invoice:
        """
        Classify the invoice and reformat poorly formatted fields.
        Does NOT create missing fields.
        """
        logger.info(
            f"LLM classification: {invoice.vendor_name or 'unknown'}"
        )

        #  Build OCR context 
        ocr_data = {
            "vendor_name":  invoice.vendor_name,
            "invoice_date": invoice.invoice_date,
            "invoice_id":   invoice.invoice_id,
            "subtotal":     invoice.subtotal,
            "tax_amount":   invoice.tax_amount,
            "total_amount": invoice.total_amount,
            "currency":     invoice.currency,
            }

        if invoice.items:
            ocr_data["items_descriptions"] = [
                item.get("description")
                for item in invoice.items
                if item.get("description")
            ]

        # Add DiT confidence score to context
        if invoice.dit_confidence is not None:
            ocr_data["dit_document_confidence"] = round(
                invoice.dit_confidence, 3
            )

        try:
            result: dict = self._chain.invoke({
                "ocr_data": json.dumps(
                    ocr_data, ensure_ascii=False, indent=2
                )
            })
        except Exception as e:
            raise ValueError(f"Azure OpenAI error: {e}") from e

        self._update_invoice(invoice, result)
        logger.info(
            f"Category : {invoice.expense_category} "
            f"(LLM confidence : {invoice.llm_confidence})"
        )
        return invoice

    def _update_invoice(self, invoice: Invoice, result: dict) -> None:
        """Update Invoice with LLM response."""
        #  Date 
        llm_date = result.get("invoice_date")
        if llm_date:
            if not invoice.invoice_date or \
               not self._is_valid_date(invoice.invoice_date):
                logger.info(
                    f"Date reformatted : "
                    f"'{invoice.invoice_date}' → '{llm_date}'"
                )
                invoice.invoice_date = llm_date

        # Vendor name 
        llm_vendor = result.get("vendor_name")
        if invoice.vendor_name and llm_vendor:
            cleaned = " ".join(invoice.vendor_name.split())
            if cleaned != invoice.vendor_name or \
               llm_vendor != invoice.vendor_name:
                logger.info(
                    f"Vendor name cleaned : "
                    f"'{invoice.vendor_name}' → '{llm_vendor}'"
                )
                invoice.vendor_name = llm_vendor

        # Amounts 
        for attr in ("subtotal", "tax_amount", "total_amount", "amount_due"):
            llm_value = result.get(attr)
            if llm_value is not None:
                try:
                    cleaned = float(llm_value)
                    current = getattr(invoice, attr)
                    if current is None or current != cleaned:
                        if current is not None:
                            logger.info(
                                f"{attr} reformatted : {current} → {cleaned}"
                            )
                        setattr(invoice, attr, cleaned)
                except (TypeError, ValueError):
                    pass

        # Currency 
        llm_currency = result.get("currency")
        if llm_currency and llm_currency in ("MAD", "EUR", "USD"):
            invoice.currency = llm_currency

        # Category 
        category = result.get("expense_category", "Other")
        if category not in EXPENSE_CATEGORIES:
            logger.warning(
                f"Unknown category : '{category}' → 'Other'"
            )
            category = "Other"
        invoice.expense_category = category

        #  LLM Confidence 
        invoice.llm_confidence = result.get("llm_confidence", "low")

    def _is_valid_date(self, date_str: str) -> bool:
        """Check if date is in YYYY-MM-DD format and reasonable range."""
        if not date_str or not DATE_PATTERN.match(str(date_str)):
            return False
        try:
            d = datetime.strptime(str(date_str), "%Y-%m-%d")
            return 2000 <= d.year <= 2030
        except ValueError:
            return False