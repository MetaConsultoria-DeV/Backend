"""Pure functions for normalizing data from the Controle Contábil spreadsheet.

This module processes raw spreadsheet fields into clean representations before database resolution.
It handles text cleaning, accent stripping, sector mapping, currency parsing, and regex extraction.
These operations do not read or write to any database or external file.
"""

import re
import unicodedata
from typing import Optional

# Constant identifying this data source in the database (matches default in schema)
EXTERNAL_SOURCE = "sharepoint_caixa"

# Regular expression to extract project codes in the NNN.YYYY format (e.g. 012.2023)
# \b: Word boundary
# \d{3}: Exactly three digits for the project number
# \.: Dot separator
# \d{4}: Exactly four digits representing the year
# \b: Word boundary
_CODIGO_RE = re.compile(r"\b(\d{3}\.\d{4})\b")


def norm_text(value) -> Optional[str]:
    """Collapses internal whitespaces and strips leading/trailing spaces from text.

    Keeps accents and casing. Used for preparing clean strings for database insertion
    (e.g., category names).

    Args:
        value: The raw input value to normalize (usually string-like).

    Returns:
        Optional[str]: The cleaned string, or None if the normalized result is empty.
    """
    if value is None:
        return None
    # Replace any sequence of whitespace characters (spaces, tabs, newlines) with a single space
    s = re.sub(r"\s+", " ", str(value)).strip()
    return s or None


def norm_key(value) -> str:
    """Creates a normalized comparison key for robust string matching.

    Performs case folding, removes diacritics/accents, collapses internal spaces,
    and strips whitespace. Used to reconcile variations like 'Área Comercial' and 'area comercial'.

    Args:
        value: The raw input string or object.

    Returns:
        str: The normalized string key (returns empty string if input is invalid/empty).
    """
    s = norm_text(value)
    if not s:
        return ""
    # Decompose unicode characters into combining characters (e.g., 'á' -> 'a' + '´')
    nfkd = unicodedata.normalize("NFKD", s)
    # Encode to ASCII, discarding any non-ASCII characters (diacritics), and decode back to string
    sem_acento = nfkd.encode("ascii", "ignore").decode("ascii")
    return sem_acento.lower().strip()


def parse_tipo(value) -> Optional[str]:
    """Parses transaction direction (income or expense).

    Checks the normalized value against 'entrada' and 'saida'.

    Args:
        value: The raw spreadsheet cell value for the transaction type.

    Returns:
        Optional[str]: 'entrada', 'saida', or None if the type is unrecognized.
    """
    k = norm_key(value)
    if k.startswith("entrada"):
        return "entrada"
    if k.startswith("saida"):
        return "saida"
    return None


# Dictionary mapping normalized sector keys to canonical Cell names in the database.
# Mapping to None means the sector is recognized as general/internal (no specific Cell).
# Sectors not present in this dictionary will not be recognized, triggering manual review.
_SETOR_TO_CELULA = {
    "presidencia": "Presidência",
    "projetos": "Projetos",
    "operacoes": "Operações",
    "gestao de pessoas": "Gestão de Pessoas",
    "marketing": "Marketing e Vendas",
    "area comercial": "Marketing e Vendas",
    "gerais": None,
}


def map_setor(value) -> tuple[Optional[str], bool]:
    """Maps spreadsheet sector names to database cell names.

    Args:
        value: The sector name from the spreadsheet.

    Returns:
        tuple[Optional[str], bool]: A tuple containing:
            - Optional[str]: The canonical name of the cell, or None (if general/unrecognized).
            - bool: True if the sector is recognized (either mapped to a cell or 'Gerais').
              False if the sector is unknown and must be flagged for manual review.
    """
    k = norm_key(value)
    if not k:
        return (None, False)
    if k in _SETOR_TO_CELULA:
        return (_SETOR_TO_CELULA[k], True)
    return (None, False)


def parse_valor(value) -> Optional[float]:
    """Parses numeric currency values from spreadsheet cells.

    Supports float values and formatted currency strings (e.g. "R$ 1.500,20").
    Returns absolute values; the sign is determined separately by the transaction type.

    Args:
        value: The raw value representing the transaction amount.

    Returns:
        Optional[float]: The absolute value as a float, rounded to 2 decimal places.
            Returns None if parsing fails.
    """
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return round(abs(float(value)), 2)
    s = str(value).strip()
    s = s.replace("R$", "").replace(" ", "")
    # Handle Brazilian number formatting (1.234,56 -> 1234.56)
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    # Remove any characters that are not digits, dots, or minus signs
    s = re.sub(r"[^0-9.\-]", "", s)
    if not s or s in ("-", ".", "-."):
        return None
    try:
        return round(abs(float(s)), 2)
    except ValueError:
        return None


def extract_codigo(value) -> Optional[str]:
    """Extracts project codes in the 'NNN.YYYY' format from the spreadsheet.

    Uses `_CODIGO_RE` to find valid patterns. General non-project labels (e.g.
    'ImpulseUp' or 'Reajuste de Saldo') do not match the pattern and return None.

    Args:
        value: The spreadsheet cell value from the 'Nº do Projeto' column.

    Returns:
        Optional[str]: The extracted code string (e.g., '001.2023'), or None.
    """
    if value is None:
        return None
    m = _CODIGO_RE.search(str(value))
    return m.group(1) if m else None

