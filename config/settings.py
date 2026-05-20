import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"Variable manquante dans .env : '{key}'"
        )
    return value

#  Azure AD 
AZURE_TENANT_ID     = _require("TENANT_ID")
AZURE_CLIENT_ID     = _require("CLIENT_ID")
AZURE_CLIENT_SECRET = _require("CLIENT_SECRET")

#  Outlook 
USER_EMAIL       = _require("USER_EMAIL")
ACCOUNTANT_EMAIL = _require("ACCOUNTANT_EMAIL")

#  Azure Document Intelligence 
AZURE_DOC_ENDPOINT = _require("AZURE_ENDPOINT")
AZURE_DOC_KEY      = _require("AZURE_KEY")

#  Azure OpenAI 
AZURE_OPENAI_ENDPOINT    = _require("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY         = _require("AZURE_OPENAI_KEY")
AZURE_OPENAI_DEPLOYMENT  = _require("AZURE_OPENAI_DEPLOYMENT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
LLM_TEMPERATURE          = 0

#  Pipeline   
CYCLE_INTERVAL_MINUTES   = int(os.getenv("CYCLE_INTERVAL_MINUTES", "10"))
OCR_CONFIDENCE_THRESHOLD = float(os.getenv("OCR_CONFIDENCE_THRESHOLD", "0.7"))
MAX_RETRY_ATTEMPTS       = int(os.getenv("MAX_RETRY_ATTEMPTS", "3"))

# ── flies 

DATA_DIR        = BASE_DIR / "data"
PENDING_DIR     = DATA_DIR / "pending"
OUTPUTS_DIR     = DATA_DIR / "outputs"
NEED_REVIEW_DIR = DATA_DIR / "need_review"
VALID_INVOICES_DIR= DATA_DIR / "valid_invoice"
VALID_INVOICES_DIR.mkdir(exist_ok=True)

for _dir in [PENDING_DIR, OUTPUTS_DIR, NEED_REVIEW_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)
