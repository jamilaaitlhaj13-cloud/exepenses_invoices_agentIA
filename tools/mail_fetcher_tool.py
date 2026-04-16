"""
tools/mail_fetcher_tool.py
--------------------------
MailFetcherTool : récupère les factures depuis Office 365 via Microsoft Graph API.

Responsabilités :
  - Authentification OAuth2 (MSAL - client credentials)
  - Récupération des emails non lus avec pièces jointes
  - Filtrage par mots-clés (Facture, Invoice, Factura, Reçu)
  - Téléchargement des pièces jointes vers /data/pending/
  - Archivage des emails traités vers le dossier "Processed"
  - Notification email au comptable en cas d'anomalie définitive
"""

import base64
import logging
import uuid
from pathlib import Path

import msal
import requests

from config.settings import (
    AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET,
    GRAPH_API_BASE_URL, GRAPH_SCOPES,
    MAILBOX_USER_EMAIL, ACCOUNTANT_EMAIL,
    MAX_RETRY_ATTEMPTS, PENDING_DIR,
)

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS  = {".pdf", ".jpg", ".jpeg", ".png"}
INVOICE_KEYWORDS    = ["facture", "invoice", "factura", "reçu", "receipt"]


class MailFetcherTool:

    def __init__(self):
        self._access_token: str | None = None
        self._token_expiry: float = 0.0

    # ── Authentification ──────────────────────────────────────────────────

    def _get_access_token(self) -> str:
        import time
        if self._access_token and time.time() < self._token_expiry - 60:
            return self._access_token

        app = msal.ConfidentialClientApplication(
            client_id=AZURE_CLIENT_ID,
            client_credential=AZURE_CLIENT_SECRET,
            authority=f"https://login.microsoftonline.com/{AZURE_TENANT_ID}",
        )
        result = app.acquire_token_for_client(scopes=GRAPH_SCOPES)

        if "access_token" not in result:
            raise ConnectionError(
                f"Échec authentification Azure AD : {result.get('error_description')}"
            )

        self._access_token = result["access_token"]
        self._token_expiry = time.time() + result.get("expires_in", 3600)
        logger.info("Token Azure AD obtenu.")
        return self._access_token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json",
        }

    def _graph_get(self, url: str, params: dict = None) -> dict:
        resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
        if resp.status_code == 401:
            self._access_token = None
            resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # ── Récupération ──────────────────────────────────────────────────────

    def fetch_invoices(self) -> list[Path]:
        """
        Récupère les emails non lus avec factures en pièces jointes.

        Returns:
            Liste des chemins des fichiers téléchargés dans /data/pending/
        """
        logger.info("Recherche des emails non lus avec factures...")

        url = f"{GRAPH_API_BASE_URL}/users/{MAILBOX_USER_EMAIL}/messages"
        params = {
            "$filter": "isRead eq false and hasAttachments eq true",
            "$select": "id,subject,hasAttachments",
            "$top": 50,
        }

        downloaded: list[Path] = []
        page_url = url

        while page_url:
            data = self._graph_get(page_url, params=params if page_url == url else None)
            for msg in data.get("value", []):
                if self._is_invoice_email(msg):
                    downloaded.extend(self._download_attachments(msg["id"]))
            page_url = data.get("@odata.nextLink")

        logger.info(f"{len(downloaded)} fichier(s) téléchargé(s).")
        return downloaded

    def _is_invoice_email(self, message: dict) -> bool:
        subject = message.get("subject", "").lower()
        return any(kw in subject for kw in INVOICE_KEYWORDS)

    def _download_attachments(self, message_id: str) -> list[Path]:
        url = f"{GRAPH_API_BASE_URL}/users/{MAILBOX_USER_EMAIL}/messages/{message_id}/attachments"
        data = self._graph_get(url)
        saved = []

        for att in data.get("value", []):
            name = att.get("name", "")
            ext  = Path(name).suffix.lower()
            if ext not in ALLOWED_EXTENSIONS:
                continue

            content_b64 = att.get("contentBytes", "")
            if not content_b64:
                continue

            dest = PENDING_DIR / f"{uuid.uuid4().hex}{ext}"
            dest.write_bytes(base64.b64decode(content_b64))
            logger.info(f"  Téléchargé : {dest.name}  (original : {name})")
            saved.append(dest)

        return saved

    # ── Archivage ─────────────────────────────────────────────────────────

    def archive_email(self, message_id: str) -> None:
        """Déplace l'email vers le dossier 'Processed' après traitement."""
        folder_id = self._get_or_create_folder("Processed")
        url = f"{GRAPH_API_BASE_URL}/users/{MAILBOX_USER_EMAIL}/messages/{message_id}/move"
        requests.post(url, headers=self._headers(),
                      json={"destinationId": folder_id}, timeout=30)
        logger.info(f"Email {message_id} archivé.")

    def _get_or_create_folder(self, name: str) -> str:
        url  = f"{GRAPH_API_BASE_URL}/users/{MAILBOX_USER_EMAIL}/mailFolders"
        data = self._graph_get(url)
        for folder in data.get("value", []):
            if folder["displayName"] == name:
                return folder["id"]
        resp = requests.post(url, headers=self._headers(),
                             json={"displayName": name}, timeout=30)
        resp.raise_for_status()
        return resp.json()["id"]

    # ── Notification ──────────────────────────────────────────────────────

    def notify_accountant(self, filename: str, errors: list[str]) -> None:
        """
        Envoie un email de notification au comptable pour une facture
        qui n'a pas pu être traitée automatiquement.
        """
        errors_html = "".join(f"<li>{e}</li>" for e in errors)
        body = f"""
        <p>Bonjour,</p>
        <p>SmartExpenseAgent n'a pas pu traiter automatiquement
        la facture <strong>{filename}</strong>
        après {MAX_RETRY_ATTEMPTS} tentatives.</p>
        <p><strong>Problèmes détectés :</strong></p>
        <ul>{errors_html}</ul>
        <p>Merci de la traiter manuellement. Elle est disponible dans le dossier
        <code>need_review</code>.</p>
        <p><em>— SmartExpenseAgent</em></p>
        """

        url = f"{GRAPH_API_BASE_URL}/users/{MAILBOX_USER_EMAIL}/sendMail"
        payload = {
            "message": {
                "subject": f"[SmartExpenseAgent] À traiter manuellement : {filename}",
                "body": {"contentType": "HTML", "content": body},
                "toRecipients": [{"emailAddress": {"address": ACCOUNTANT_EMAIL}}],
            }
        }
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=30)
        if resp.ok:
            logger.info(f"Notification envoyée au comptable : {filename}")
        else:
            logger.error(f"Échec notification : {resp.text[:100]}")