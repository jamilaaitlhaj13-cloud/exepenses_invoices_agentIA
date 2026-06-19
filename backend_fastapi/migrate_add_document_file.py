"""
Migration : ajoute la colonne document_file à invoice_records.
Exécuter une seule fois : python migrate_add_document_file.py
"""
from sqlalchemy import text
from database import engine

with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE invoice_records ADD COLUMN document_file VARCHAR(500) DEFAULT ''"))
        conn.commit()
        print("✓ Colonne document_file ajoutée.")
    except Exception as e:
        if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
            print("✓ Colonne déjà présente — rien à faire.")
        else:
            raise
