import os
import logging
import sys
import json
from dotenv import load_dotenv
from src.ocr_agent import OCREngine 

load_dotenv()

log_format = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')

file_handler = logging.FileHandler("app.log", encoding='utf-8')
file_handler.setLevel(logging.INFO) 
file_handler.setFormatter(log_format)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.WARNING) 
console_handler.setFormatter(log_format)

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler],
    force=True)

logger = logging.getLogger("MainProcess")

def run():
    logger.info("--- PIPELINE START-UP ---")
    ocr = OCREngine()
    folder="data/pending"
    for file in os.listdir(folder):
        if file.endswith((".jpg",".jpeg",".png",".pdf")):
            file_path=os.path.join(folder,file)
            resultat = ocr.extract_invoice_data(file_path)
            logger.info(f"result for {file}")
            logger.info(json.dumps(resultat, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    run()