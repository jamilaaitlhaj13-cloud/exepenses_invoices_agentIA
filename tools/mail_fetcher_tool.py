# tools/mail_fetcher_tool.py

import base64
import json
import logging
import uuid
import os
from pathlib import Path
import msal
import requests
from openai import AzureOpenAI
import hashlib
from config.settings import (
    AZURE_CLIENT_ID,
    ACCOUNTANT_EMAIL,
    MAX_RETRY_ATTEMPTS,
    PENDING_DIR,
)

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  

SCOPES = [
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/Mail.ReadWrite",
]

GRAPH_API  = "https://graph.microsoft.com/v1.0"
TOKEN_FILE = "ms_token.json"
class MailFetcherTool:
    def __init__(self):
        self.client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        )
        self.deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT")
        self._token_cache = msal.SerializableTokenCache()
        if Path(TOKEN_FILE).exists():
            self._token_cache.deserialize(open(TOKEN_FILE).read())

        self._app = msal.PublicClientApplication(
            client_id=AZURE_CLIENT_ID,
            authority="https://login.microsoftonline.com/common",
            token_cache=self._token_cache,
        )
        self._token = self._get_token()
        self._pending_messages={}
        self._processed_message_ids=set()
        self._pending_messages={}
        self._processed_files_hashes=set()


    def _get_token(self) -> str:
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(SCOPES, account=accounts[0])
            if result and "access_token" in result:
                self._save_cache()
                return result["access_token"]
        return self._device_flow_auth()


    def _device_flow_auth(self) -> str:
        flow = self._app.initiate_device_flow(scopes=SCOPES)
        if "error" in flow:
            raise ConnectionError(f"Device flow failed: {flow.get('error_description')}")
        print("\n" + "=" * 60)
        print(flow["message"])
        print("=" * 60 + "\n")
        result = self._app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise ConnectionError(f"Auth failed: {result.get('error_description')}")
        self._save_cache()
        return result["access_token"]

    def _save_cache(self):
        if self._token_cache.has_state_changed:
            with open(TOKEN_FILE, "w") as f:
                f.write(self._token_cache.serialize())


    def _refresh_token(self) -> str:
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(SCOPES, account=accounts[0])
            if result and "access_token" in result:
                self._save_cache()
                return result["access_token"]
        logger.warning("Token expired — re-authenticating...")
        return self._device_flow_auth()


    def _headers(self) -> dict:
        self._token = self._refresh_token()
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type":  "application/json",
        }


    # INVOICE DETECTION
    def _clean_subject(self, subject: str) -> str:
        prefixes = ["Fwd:", "FWD:", "Fw:", "FW:", "Tr:", "TR:", "Re:", "RE:", "RE :", "Re :"]
        cleaned = subject
        for prefix in prefixes:
            if cleaned.lower().startswith(prefix.lower()):
                cleaned = cleaned[len(prefix):].strip()
        return cleaned

    def _quick_check(self, subject: str, attachments_meta: list) -> bool | None:
        """
        Quick pre-check to avoid LLM calls for obvious cases.
        Returns:
            True  → definitely an invoice (skip LLM)
            False → definitely NOT an invoice (skip LLM)
            None  → uncertain (call LLM)
        """
        subject_lower = self._clean_subject(subject).lower()
        has_attachment = len(attachments_meta) > 0

        # Check attachment names
        attachment_names = " ".join(a.get("name", "").lower() for a in attachments_meta)

        
        
        #Obvious NOT INVOICE 
        obvious_non_invoice = [
            "invitation", "meeting", "réunion", "rendez-vous",
            "newsletter", "happy birthday", "congratulations",
            "out of office", "absence", "vacation", "congé"
        ]
        has_non_invoice_subject = any(
            word in subject_lower for word in obvious_non_invoice
        )
        if has_non_invoice_subject:
            logger.info(
                f"Quick match: non-business subject → NOT_INVOICE "
                f"(subject: '{subject[:60]}')"
            )
            return False
        
        return None

    def llm_is_invoice_email(
        self,
        subject: str,
        sender: str,
        body: str,
        attachments_meta: list
    ) -> bool:
        """
        Classify if an email contains an invoice.
        Uses quick keyword check first, then LLM for ambiguous cases.
        """
        
        #Step 1: Quick keyword check (free, fast) ──────
        quick_result = self._quick_check(subject, attachments_meta)
        if quick_result is not None:
            return quick_result
        
        #Step 2: LLM for ambiguous cases ───────────────
        cleaned_subject = self._clean_subject(subject)
        prompt = f"""You are an expert email analyst for an automated invoice processing system.

Your job: determine if this email contains or references an INVOICE that needs to be processed.

Analyze the email holistically. Ask yourself: "Is the sender requesting payment or sending a bill?"

An email is an INVOICE email if:
- It is requesting payment for goods or services
- It contains or references a bill, facture, receipt, or payment request
- It has an attached document that looks like an invoice

An email is NOT an INVOICE email if:
- It's a meeting invitation, newsletter, casual conversation, out-of-office reply
- It's an order confirmation that explicitly says "this is not an invoice"
- It's asking the recipient to download an invoice from a portal (no attachment)

Use your judgment. Think about the INTENT of the email, not just keywords.
Understand that invoices come in many forms, languages, and formats.

Email to analyze:
- Subject     : {cleaned_subject}
- Sender      : {sender}
- Body preview: {body[:400]}
- Attachments : {json.dumps(attachments_meta) if attachments_meta else 'None'}

Return ONLY valid JSON, no markdown, no explanation:
{{"label": "INVOICE" or "NOT_INVOICE", "confidence": 0.0 to 1.0, "reason": "brief explanation in English"}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an intelligent email analyst. "
                            "You understand that invoices come in many forms, "
                            "languages, and formats. Use your judgment, not rigid rules. "
                            "Always return valid JSON only."
                        )
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_completion_tokens=200,
            )
            txt = response.choices[0].message.content.strip()
            # Clean markdown code blocks if present
            if txt.startswith("```"):
                parts = txt.split("```")
                txt = parts[1] if len(parts) > 1 else txt
                if txt.startswith("json"):
                    txt = txt[4:]
                txt = txt.strip()
            data       = json.loads(txt)
            label      = data.get("label", "NOT_INVOICE")
            confidence = float(data.get("confidence", 0.0))
            reason     = data.get("reason", "")

            logger.info(
                f"LLM → {label} (confidence={confidence:.2f}) | {reason}"
            )
            return label == "INVOICE" and confidence >= 0.7

        except json.JSONDecodeError as e:
            logger.warning(
                f"LLM JSON parsing failed: {e} | raw: {txt[:100] if 'txt' in dir() else 'N/A'}"
            )
            # Fallback: accept if subject contains obvious invoice words
            subject_lower = subject.lower()
            return False
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            # Fallback: accept if subject contains obvious invoice words
            subject_lower = subject.lower()
            return False

    # GRAPH API
    def get_attachments_metadata(self, message_id: str) -> list:
        """
        Fetch attachment metadata WITHOUT downloading content.
        """
        url = (
            f"{GRAPH_API}/me/messages/{message_id}/attachments"
            f"?$select=name,contentType,size"
        )
        try:
            response = requests.get(
                url, headers=self._headers(), timeout=30
            )
            response.raise_for_status()
            attachments = response.json().get("value", [])
            return [
                {
                    "name":        a.get("name", ""),
                    "contentType": a.get("contentType", ""),
                    "size":        a.get("size", 0),
                }
                for a in attachments
            ]
        except Exception as e:
            logger.warning(f"Could not fetch attachments metadata: {e}")
            return []

    # MAIN PIPELINE
    def fetch_invoices(self) -> list[Path]:
        """
        Fetch unread emails with attachments, classify them,
        and download invoice attachments.
        """
        logger.info("Searching for unread emails with attachments...")

        url    = f"{GRAPH_API}/me/messages"
        params = {
            "$filter": "isRead eq false",
            "$select": "id,subject,from,bodyPreview,hasAttachments",
            "$top": 50,
            }
        try:
            response = requests.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            messages = response.json().get("value", [])
        except requests.HTTPError as e:
            logger.error(f"Graph API error: {e}")
            return []
        except requests.Timeout:
            logger.error("Graph API timeout")
            return []

        logger.info(f"{len(messages)} email(s) with attachments found")
        accepted_files: list[Path] = []

        for msg in messages:
            msg_id  = msg["id"]
            if not msg.get("hasAttachments"):
                logger.debug(f"No attachments: '{msg.get('subject', '')[:60]}'")
                continue
            if msg_id in self._processed_message_ids:
                logger.info(f"skiping already processed:{msg.get('subject','')[:60]}")
                continue
            subject = msg.get("subject", "")
            sender  = (
                msg.get("from", {})
                .get("emailAddress", {})
                .get("address", "")
            )
            body    = msg.get("bodyPreview", "")

            logger.info(f"Analyzing: '{subject[:80]}' | {sender}")

            # Get metadata without downloading
            attachments_meta = self.get_attachments_metadata(msg_id)

            # Classify
            is_invoice = self.llm_is_invoice_email(
                subject, sender, body, attachments_meta
            )

            if not is_invoice:
                logger.info(f"Not an invoice → skipped: {subject[:60]}")
                continue

            logger.info(f"Invoice detected → downloading: {subject[:60]}")
            # Download attachments
            files = self._download_attachments(msg_id)

            if files:
                new_files=[]
                for f in files:
                    file_hash=hashlib.md5(f.read_bytes()).hexdigest()
                    if file_hash in self._processed_files_hashes:
                        logger.info(f"duplicate file (same content){f.name} -> skipped")
                        f.unlink()
                        continue
                    self._processed_files_hashes.add(file_hash)
                    self._pending_messages[str(f)]=msg_id
                    new_files.append(f)
                accepted_files.extend(new_files)
                if new_files:
                    logger.info(f"  {len(new_files)} unique file(s) downloaded")
                else:
                    logger.info(f"  All files were duplicates — skipped")
            else:
                logger.warning(f"  No valid files in: {subject[:60]}")
        logger.info(
            f"Cycle complete — {len(accepted_files)} invoice(s) collected"
        )
        return accepted_files

    # DOWNLOAD
    def _download_attachments(self, message_id: str) -> list[Path]:
        """Download valid attachments to PENDING_DIR"""
        url = f"{GRAPH_API}/me/messages/{message_id}/attachments"
        try:
            response = requests.get(
                url, headers=self._headers(), timeout=30
            )
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return []

        saved = []
        for att in response.json().get("value", []):
            name = att.get("name", "")
            ext  = Path(name).suffix.lower()
            size = att.get("size", 0)

            # Check extension
            if ext not in ALLOWED_EXTENSIONS:
                logger.debug(f"Ignored extension: {name}")
                continue

            # Check size
            if size > MAX_ATTACHMENT_SIZE:
                logger.warning(
                    f"Attachment too large: {name} "
                    f"({size / 1e6:.1f} MB)"
                )
                continue
            content = att.get("contentBytes")
            if not content:
                logger.warning(f"Empty attachment: {name}")
                continue

            file_path = PENDING_DIR / f"{uuid.uuid4().hex}{ext}"
            file_path.write_bytes(base64.b64decode(content))
            logger.info(
                f"  Downloaded: {file_path.name} (original: {name})"
            )
            saved.append(file_path)
        return saved

    # EMAIL OPS
    def _mark_as_read(self, message_id: str) -> None:
        """Mark an email as read."""
        url = f"{GRAPH_API}/me/messages/{message_id}"
        try:
            requests.patch(
                url,
                headers=self._headers(),
                json={"isRead": True},
                timeout=30,
            )
        except Exception as e:
            logger.warning(f"Mark as read failed: {e}")

    def notify_accountant(self,filename: str,errors: list[str]) -> None:
        """Send notification to accountant when an invoice cannot be processed."""
        errors_html = "".join(f"<li>{e}</li>" for e in errors)
        body_html = f"""
        <p>Hello,</p>
        <p>SmartExpenseAgent could not process the invoice
        <strong>{filename}</strong>
        after <strong>{MAX_RETRY_ATTEMPTS} attempts</strong>.</p>
        <p><strong>Errors detected:</strong></p>
        <ul>{errors_html}</ul>
        <p>The file has been moved to
        <code>data/need_review/</code>
        for manual processing.</p>
        <br>
        <p><em>— SmartExpenseAgent</em></p>
        """
        payload = {
            "message": {
                "subject": f"[SmartExpenseAgent] Manual review required: {filename}",
                "body": {"contentType": "HTML", "content": body_html},
                "toRecipients": [
                    {"emailAddress": {"address": ACCOUNTANT_EMAIL}}
                ],
            }
        }

        try:
            response = requests.post(
                f"{GRAPH_API}/me/sendMail",
                headers=self._headers(),
                json=payload,
                timeout=30,
            )
            if response.ok:
                logger.info(f"Notification sent to {ACCOUNTANT_EMAIL}")
            else:
                logger.error(
                    f"Notification failed: {response.text[:100]}"
                )
        except Exception as e:
            logger.error(f"Notification error: {e}")
    def mark_message_as_read(self, file_path: Path) -> None:
        """Mark email as read AFTER successful processing."""
        msg_id = self._pending_messages.pop(str(file_path), None)
        if msg_id:

            self._mark_as_read(msg_id)
            logger.info(f"Email marked as read: {msg_id[:20]}...")

    def mark_as_validated(self, file_path: Path) -> None:
        """
        Called when the full pipeline succeeds.
        Email IS marked as read.
        """
        msg_id = self._pending_messages.pop(str(file_path), None)
        if msg_id:
            self._processed_message_ids.add(msg_id)
            self._mark_as_read(msg_id)
            logger.info(f"Email marked as read (invoice validated)")


    def mark_as_rejected(self, file_path: Path) -> None:
        """
        Called when DiT rejects the document.
        Email stays UNREAD (visible to human) but won't be processed again.
        """
        msg_id = self._pending_messages.pop(str(file_path), None)
        if msg_id:
            self._processed_message_ids.add(msg_id)
            logger.info(f"Email marked as processed (rejected — left unread for manual review)")