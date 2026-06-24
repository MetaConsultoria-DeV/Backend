"""Module for parsing the Controle Contábil Excel spreadsheet.

Anchors dynamically to the header row based on column labels rather than absolute row indexes
since analysts may insert rows above the main table. Extracts transactions by scanning for rows
with valid dates below the identified header.
"""

import io
import logging
import datetime as _dt
from typing import Optional, Union

import openpyxl

from .normalize import norm_key

# Logger instance for the parser module
logger = logging.getLogger("ingestion.contabil.parser")

# 0-based column indices in the spreadsheet (corresponding to columns D to K)
COL_DATA = 3       # Column D: Transaction Date
COL_CONTA = 4      # Column E: Bank Account Name
COL_TIPO = 5       # Column F: Type (Entrada/Saída)
COL_SETOR = 6      # Column G: Sector (Presidência, Projetos, etc.)
COL_CATEGORIA = 7  # Column H: Transaction Category
COL_PROJETO = 8    # Column I: Project number/code
COL_VALOR = 9      # Column J: Financial Value
COL_OBS = 10       # Column K: Observations / Remarks


def _is_header_row(row: tuple) -> bool:
    """Heuristic helper to check if a row corresponds to the table headers.

    Checks if column D normalized contains 'data', E contains 'conta', and J contains 'valor'.

    Args:
        row (tuple): A row of cell values from the spreadsheet.

    Returns:
        bool: True if the row matches the header heuristics, False otherwise.
    """
    def at(i):
        return norm_key(row[i]) if i < len(row) and row[i] is not None else ""
    return at(COL_DATA).startswith("data") and at(COL_CONTA).startswith("conta") \
        and at(COL_VALOR).startswith("valor")


def _as_date(value) -> Optional[_dt.date]:
    """Safely converts a cell value into a datetime.date object.

    Handles both datetime.datetime and datetime.date objects. Discards time-only
    formatted cells.

    Args:
        value: The raw cell value from openpyxl.

    Returns:
        Optional[_dt.date]: The extracted date, or None if the value is not a valid date.
    """
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    return None


def parse_xlsx(source: Union[bytes, str, io.BytesIO]) -> list[dict]:
    """Reads the Excel spreadsheet and parses transaction rows.

    This function opens the Excel sheet (in read-only, data-only mode to prevent formula retrieval)
    and searches for the main table header. It iterates from that header downward, capturing
    every row containing a valid transaction date in the Date column.

    Args:
        source (Union[bytes, str, io.BytesIO]): Raw spreadsheet bytes (e.g., from n8n upload),
            file path string (for tests), or a BytesIO buffer.

    Returns:
        list[dict]: A list of raw transaction dictionaries, each containing:
            - row_num (int): 1-based line number for curation/debugging.
            - data (datetime.date): Parsed transaction date.
            - conta: Raw account value.
            - tipo: Raw direction type value.
            - setor: Raw sector value.
            - categoria: Raw category value.
            - projeto: Raw project identifier.
            - valor: Raw currency value.
            - obs: Raw comments/observations.

    Raises:
        ValueError: If no valid header row matching the heuristic can be found in the worksheet.
    """
    if isinstance(source, bytes):
        source = io.BytesIO(source)
    # Open workbook in data_only mode to read evaluated formula values, and read_only for memory efficiency
    wb = openpyxl.load_workbook(source, data_only=True, read_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))

    # Find the active header row. Look for a header row followed by a row containing a valid date.
    header_idx = None
    for i, row in enumerate(rows):
        if _is_header_row(row):
            nxt = rows[i + 1] if i + 1 < len(rows) else ()
            if nxt and len(nxt) > COL_DATA and _as_date(nxt[COL_DATA]) is not None:
                header_idx = i
                break
                
    if header_idx is None:
        # Fallback: take the very last header row matching the signature even if no date immediately follows it
        candidatos = [i for i, row in enumerate(rows) if _is_header_row(row)]
        if not candidatos:
            raise ValueError("Cabeçalho da tabela de transações não encontrado na planilha")
        header_idx = candidatos[-1]
        logger.warning("Cabeçalho achado por fallback na linha %d", header_idx + 1)

    out: list[dict] = []
    # Parse rows starting right after the header index
    for i in range(header_idx + 1, len(rows)):
        row = rows[i]
        if row is None:
            continue
        data = _as_date(row[COL_DATA] if len(row) > COL_DATA else None)
        if data is None:
            # Skip rows without a valid date (e.g. empty lines, footer notes, totals)
            continue

        def cell(idx):
            return row[idx] if len(row) > idx else None

        out.append({
            "row_num": i + 1,  # 1-based row number for reporting
            "data": data,
            "conta": cell(COL_CONTA),
            "tipo": cell(COL_TIPO),
            "setor": cell(COL_SETOR),
            "categoria": cell(COL_CATEGORIA),
            "projeto": cell(COL_PROJETO),
            "valor": cell(COL_VALOR),
            "obs": cell(COL_OBS),
        })

    wb.close()
    logger.info("Planilha lida: %d transações (cabeçalho na linha %d)", len(out), header_idx + 1)
    return out

