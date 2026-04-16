"""
tools/export_tool.py
---------------------
ExportTool : génère le rapport Excel et gère les fichiers en fin de cycle.

Responsabilités :
  - Consolider les factures validées en un DataFrame Pandas
  - Exporter en Excel dans /data/outputs/ avec mise en forme
  - Déplacer les factures traitées hors de /data/pending/
  - Déplacer les factures en échec vers /data/need_review/
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from config.settings import OUTPUTS_DIR, NEED_REVIEW_DIR
from models.invoice import Invoice

logger = logging.getLogger(__name__)

HEADER_COLOR = "1F3864"   # Bleu NTT DATA


class ExportTool:

    def export(self, invoices: list[Invoice]) -> Path | None:
        """
        Génère le rapport Excel des factures validées du cycle.

        Args:
            invoices: Liste des objets Invoice avec is_valid=True.

        Returns:
            Chemin vers le fichier Excel généré, ou None si aucune facture.
        """
        if not invoices:
            logger.info("Aucune facture valide à exporter.")
            return None

        logger.info(f"Export de {len(invoices)} facture(s)...")

        rows = [inv.to_dict() for inv in invoices]
        df   = pd.DataFrame(rows)

        # Formater les colonnes numériques
        for col in ["Montant HT", "TVA", "Total TTC"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").round(2)

        timestamp   = datetime.now().strftime("%Y%m%d_%H%M")
        output_path = OUTPUTS_DIR / f"rapport_factures_{timestamp}.xlsx"

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Factures")
            self._format_sheet(writer.sheets["Factures"], df)

        logger.info(f"Rapport généré : {output_path.name}")
        return output_path

    def _format_sheet(self, ws, df: pd.DataFrame) -> None:
        """Mise en forme professionnelle de la feuille Excel."""
        header_font  = Font(color="FFFFFF", bold=True, name="Calibri", size=11)
        header_fill  = PatternFill("solid", fgColor=HEADER_COLOR)
        header_align = Alignment(horizontal="center", vertical="center")

        for col_idx in range(1, len(df.columns) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font      = header_font
            cell.fill      = header_fill
            cell.alignment = header_align

        # Largeurs automatiques
        for col_idx, col_name in enumerate(df.columns, start=1):
            letter  = get_column_letter(col_idx)
            max_len = max(
                len(str(col_name)),
                *[len(str(ws.cell(row=r, column=col_idx).value or ""))
                  for r in range(2, ws.max_row + 1)]
            )
            ws.column_dimensions[letter].width = min(max_len + 4, 40)

        ws.freeze_panes = "A2"

    # ── Gestion des fichiers ──────────────────────────────────────────────

    def move_to_need_review(self, file_path: Path) -> None:
        """
        Déplace une facture non traitable vers /data/need_review/
        pour inspection manuelle par le comptable.
        """
        dest = NEED_REVIEW_DIR / file_path.name
        shutil.move(str(file_path), str(dest))
        logger.info(f"Facture déplacée vers need_review : {file_path.name}")

    def cleanup_pending(self, file_path: Path) -> None:
        """
        Supprime le fichier de /data/pending/ après traitement réussi.
        Le fichier a déjà été archivé via l'email — on supprime la copie locale.
        """
        if file_path.exists():
            file_path.unlink()
            logger.debug(f"Fichier supprimé de pending : {file_path.name}")