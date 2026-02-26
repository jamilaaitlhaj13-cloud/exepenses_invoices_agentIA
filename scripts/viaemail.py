import os
import glob
import imaplib
import email
import pandas as pd
from dotenv import load_dotenv
from pathlib import Path
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from typing import List

# --- 1. CONFIGURATION & SÉCURITÉ ---
env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

AZURE_ENDPOINT = os.getenv("azure_endpoint")
AZURE_KEY = os.getenv("azure_key")
GROQ_KEY = os.getenv("MY_CLE")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_IMAP = os.getenv("EMAIL_IMAP")

DOSSIER_INVOICES = "data/invoices"
os.makedirs(DOSSIER_INVOICES, exist_ok=True)

# --- 2. FONCTION TÉLÉCHARGEMENT EMAILS ---
def recuperer_factures_email():
    print("📧 Connexion à la boîte mail...")
    try:
        mail = imaplib.IMAP4_SSL(EMAIL_IMAP)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")

        # Recherche des emails non lus
        status, messages = mail.search(None, '(UNSEEN)')
        ids = messages[0].split()
        print(f"📩 {len(ids)} nouvel(s) email(s) trouvé(s).")

        for num in ids:
            status, data = mail.fetch(num, "(RFC822)")
            for response_part in data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    for part in msg.walk():
                        if part.get_content_maintype() == 'multipart': continue
                        if part.get('Content-Disposition') is None: continue
                        
                        filename = part.get_filename()
                        if filename and filename.lower().endswith(('.png', '.jpg', '.jpeg', '.pdf')):
                            filepath = os.path.join(DOSSIER_INVOICES, filename)
                            with open(filepath, "wb") as f:
                                f.write(part.get_payload(decode=True))
                            print(f"📥 Pièce jointe enregistrée : {filename}")
        mail.close()
        mail.logout()
    except Exception as e:
        print(f"❌ Erreur Email : {e}")

# --- 3. STRUCTURE DES DONNÉES ---
class ArticleSchema(BaseModel):
    designation: str = Field(description="Nom du produit")
    quantite: float = Field(description="Quantité")
    prix_unitaire: float = Field(description="Prix unitaire")
    montant_ligne: float = Field(description="Total de la ligne")

class FactureSchema(BaseModel):
    fournisseur: str = Field(description="Nom de l'entreprise émettrice")
    numero_facture: str = Field(description="Identifiant de la facture")
    date_emission: str = Field(description="Date au format JJ/MM/AAAA")
    articles: List[ArticleSchema] = Field(description="Liste des produits/services")
    total_ttc: float = Field(description="Montant total TTC")

parser = JsonOutputParser(pydantic_object=FactureSchema)
llm = ChatGroq(groq_api_key=GROQ_KEY, model_name="llama-3.3-70b-versatile", temperature=0)
azure_client = DocumentAnalysisClient(AZURE_ENDPOINT, AzureKeyCredential(AZURE_KEY))

# --- 4. EXÉCUTION DU TRAITEMENT ---
def lancer_traitement():
    recuperer_factures_email() # Étape 1 : On télécharge
    
    # Étape 2 : On liste les fichiers
    extensions = ['*.png', '*.jpg', '*.jpeg', '*.pdf']
    liste_images = []
    for ext in extensions:
        liste_images.extend(glob.glob(os.path.join(DOSSIER_INVOICES, ext)))

    if not liste_images:
        print("Empty folder: Aucune facture à traiter.")
        return

    all_rows = []
    for path in liste_images:
        print(f"🔍 Analyse Azure + Groq : {os.path.basename(path)}")
        try:
            # OCR Azure
            with open(path, "rb") as f:
                poller = azure_client.begin_analyze_document("prebuilt-invoice", document=f)
                result = poller.result()
            
            # Structuration Groq
            prompt = f"Analyse ce texte de facture Azure :\n{result.content}\n{parser.get_format_instructions()}"
            response = llm.invoke([HumanMessage(content=prompt)])
            data = parser.parse(response.content)

            # Ajout au tableau
            for art in data.get('articles', []):
                all_rows.append({
                    "Fichier": os.path.basename(path),
                    "Fournisseur": data.get('fournisseur'),
                    "Numéro": data.get('numero_facture'),
                    "Date": data.get('date_emission'),
                    "Désignation": art.get('designation'),
                    "Prix Unit": art.get('prix_unitaire'),
                    "Total TTC": data.get('total_ttc')
                })
        except Exception as e:
            print(f"⚠️ Erreur sur {path} : {e}")

    # Étape 3 : Sauvegarde Excel
    if all_rows:
        df = pd.DataFrame(all_rows)
        df.to_excel("resultats_factures.xlsx", index=False)
        print(f"\n✅ Terminé ! Excel mis à jour avec {df['Fichier'].nunique()} documents.")

if __name__ == "__main__":
    lancer_traitement()