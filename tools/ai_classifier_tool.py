import json
import logging

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
    "SaaS", "Voyage", "Bureau", "Services publics", "Autre"
]

SYSTEM_PROMPT = """\
Tu es un assistant comptable expert en traitement de factures.
Tu reçois les données extraites par OCR d'une facture.
Ta tâche :
  1. Laisser les champs manquants vides et ecrire None.
  2. Classifier le type de dépense.
Réponds UNIQUEMENT avec un objet JSON valide.
Aucun texte avant ou après. Pas de backticks.\
"""

USER_PROMPT = """\
Voici les données OCR de la facture :
{ocr_data}

Retourne un JSON avec exactement cette structure :
{{
  "vendor_name": "Nom du fournisseur ou null",
  "invoice_date": "YYYY-MM-DD ou null",
  "invoice_id": "Numéro de facture ou null",
  "subtotal": montant HT en float ou null,
  "tax_amount": montant TVA en float ou null,
  "total_amount": montant TTC en float ou null,
  "currency": "MAD ou EUR ou USD",
  "expense_category": "SaaS ou Voyage ou Bureau ou Services publics ou Autre",
  "llm_confidence": "high ou medium ou low"
}}

Règles de classification :
- Microsoft, AWS, GitHub, Zoom, Salesforce, Google Cloud → "SaaS"
- Avion, hôtel, taxi, Uber, restaurant en déplacement   → "Voyage"
- Fournitures, imprimante, mobilier, équipement         → "Bureau"
- Électricité, eau, internet, téléphone                 → "Services publics"
- Tout le reste                                         → "Autre"\
"""


class AIClassifierTool:

    def __init__(self):
        # Connexion Azure OpenAI
        self._llm = AzureChatOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_KEY,
            azure_deployment=AZURE_OPENAI_DEPLOYMENT,
            api_version=AZURE_OPENAI_API_VERSION,
            temperature=LLM_TEMPERATURE,
        )

        self._parser = JsonOutputParser()
        self._prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("user",   USER_PROMPT),
        ])

        # Chaîne : prompt → LLM → parser JSON
        self._chain = self._prompt | self._llm | self._parser

    def classify(self, invoice: Invoice) -> Invoice:
        """
        Classifie la facture et complète les champs manquants.

        Args:
            invoice : objet Invoice après OCR

        Returns:
            Le même objet Invoice mis à jour
        """
        logger.info(f"Classification LLM : {invoice.vendor_name or 'inconnu'}")

        # Données à envoyer au LLM
        ocr_data = {
            "vendor_name":  invoice.vendor_name,
            "invoice_date": invoice.invoice_date,
            "invoice_id":   invoice.invoice_id,
            "subtotal":     invoice.subtotal,
            "tax_amount":   invoice.tax_amount,
            "total_amount": invoice.total_amount,
            "currency":     invoice.currency,
        }

        try:
            result: dict = self._chain.invoke({
                "ocr_data": json.dumps(ocr_data, ensure_ascii=False, indent=2)
            })
        except Exception as e:
            raise ValueError(f"Erreur Azure OpenAI : {e}") from e

        self._update_invoice(invoice, result)

        logger.info(
            f"Catégorie : {invoice.expense_category} "
            f"(confiance : {invoice.llm_confidence})"
        )
        return invoice

    def _update_invoice(self, invoice: Invoice, result: dict) -> None:
        """
        Met à jour l'Invoice avec la réponse du LLM.
        Complète uniquement les champs vides.
        """
        for attr in ("vendor_name", "invoice_date", "invoice_id",
                     "subtotal", "tax_amount", "total_amount", "currency"):
            llm_value = result.get(attr)
            if llm_value is not None and getattr(invoice, attr) is None:
                setattr(invoice, attr, llm_value)

        category = result.get("expense_category", "Autre")
        if category not in EXPENSE_CATEGORIES:
            category = "Autre"
        invoice.expense_category = category
        invoice.llm_confidence   = result.get("llm_confidence", "low")