import os
import logging
import json
import sys
from dotenv import load_dotenv
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential


load_dotenv()
logger=logging.getLogger(__name__)

class OCREngine:
    def __init__(self):
        self.endpoint=os.getenv("AZURE_ENDPOINT")
        self.key=os.getenv("AZURE_KEY")

        if not self.endpoint or not self.key:
            logger.critical("azure credentials not found")
            raise ValueError("azure credentials missing")
        
        self.client=DocumentAnalysisClient(
            endpoint=self.endpoint,
            credential=AzureKeyCredential(self.key))
        logger.info("OCREngine initialized successfully")

    def extract_invoice_data(self,file_path):
        logger.info(f"beginning of the analysis:{file_path}")
        with open(file_path,"rb") as f:
            poller=self.client.begin_analyze_document("prebuilt-invoice",document=f)
            result=poller.result()
        
        for invoice in result.documents:
            # invoice date
            date_invoice_field = invoice.fields.get("InvoiceDate")
            invoice_date = "not detected"
            if date_invoice_field:
                invoice_date = str(date_invoice_field.value) if date_invoice_field.value else date_invoice_field.content

            # due date
            date_due_field = invoice.fields.get("DueDate")
            due_date = "not detected"
            if date_due_field:
                due_date = str(date_due_field.value) if date_due_field.value else date_due_field.content
            else:
                logger.warning(f"due date not detected by OCR in {file_path}")
            
            vendor = invoice.fields.get("VendorName")
            invoice_id = invoice.fields.get("InvoiceId")
            subtotal = invoice.fields.get("SubTotal")
            tax = invoice.fields.get("TotalTax")
            total = invoice.fields.get("InvoiceTotal")

            data = {
                "supplier_name": vendor.value.replace("\n", " ") if vendor and vendor.value else "unknown",
                "invoice_date": invoice_date,
                "due_date":due_date,
                "invoice_ID": invoice_id.value if invoice_id and invoice_id.value else None,
                "total_HT": subtotal.value.amount if subtotal and subtotal.value else 0.0,
                "total_TVA": tax.value.amount if tax and tax.value else 0.0,
                "total_TTC": total.value.amount if total and total.value else 0.0,
    }
        return data
    
if __name__ == "__main__":
    load_dotenv()

    log_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    file_handler = logging.FileHandler("app.log", encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(log_format)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.WARNING) 
    console_handler.setFormatter(log_format)

    logging.basicConfig(
        level=logging.INFO,
        handlers=[file_handler, console_handler],
        force=True
    )

    try:
        agent = OCREngine()
        folder="data/pending"
        for file in os.listdir(folder):
            file_path=os.path.join(folder,file)
            resultat = agent.extract_invoice_data(file_path)
        
            logger.info(f"result for {file}")
            logger.info(json.dumps(resultat, indent=2, ensure_ascii=False))

    except FileNotFoundError:
        #missing file
        logger.error("TECHNICAL DETAIL: the path is incorrect or the file does not exist")
        logger.error("ERROR : The image file could not be found.")
    except ConnectionError:
        #internet problem
        logger.exception("TECHNICAL DETAIL: Connection to Azure servers failed.")
        logger.error("ERROR: Internet connection problem.")

    except Exception as e:
        logger.exception(f"TECHNICAL DETAIL of the error: {str(e)}")
        logger.info(f"CRITICAL ERROR : {type(e).__name__} occurred")

    finally:
        logging.info("End of test session.")