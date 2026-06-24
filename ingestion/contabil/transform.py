"""Module for transforming raw spreadsheet rows into normalized transaction dicts.

This module maps raw dictionary rows parsed from openpyxl into standardized transaction formats.
It calculates unique, deterministic external IDs based on row contents to support idempotency.
Validation checks are performed to flag missing fields or unrecognized sectors for review.
"""

import hashlib
from typing import Optional

from .normalize import (
    EXTERNAL_SOURCE, norm_text, parse_tipo, map_setor, parse_valor, extract_codigo,
)


def _external_id(data, conta_key: str, tipo: str, sector_key: str,
                 categoria_key: str, valor: float, obs_key: str,
                 contador: dict) -> str:
    """Generates a stable, content-derived unique ID for the transaction.

    Constructs a unique signature by joining normalized transaction fields.
    Computes a SHA-1 hash of this signature, takes the first 16 characters,
    and appends a counter suffix (`-{N}`) to disambiguate identical legitimate transactions
    (e.g., two identical payments on the same day).

    Args:
        data (datetime.date): The transaction date.
        conta_key (str): The normalized account name key.
        tipo (str): The parsed transaction direction ('entrada' or 'saida').
        sector_key (str): The normalized sector key.
        categoria_key (str): The normalized category key.
        valor (float): The parsed absolute currency value.
        obs_key (str): The normalized observations key.
        contador (dict): A mutable counter dictionary keeping track of hash occurrences.

    Returns:
        str: A unique identifier string in the format `{sha1_prefix}-{occurrence_number}`.
    """
    # Join normalized fields with pipes to create a stable string representation of the row content
    base = f"{data.isoformat()}|{conta_key}|{tipo}|{sector_key}|{categoria_key}|{valor:.2f}|{obs_key}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
    
    # Increment the occurrence count for this specific content hash
    contador[h] = contador.get(h, 0) + 1
    return f"{h}-{contador[h]}"


def transform_row(raw: dict, contador: dict) -> dict:
    """Transforms a raw transaction dictionary into a normalized representation.

    Parses raw spreadsheet strings, maps the sector name to database cells, and extracts
    project codes. It runs validation checks to ensure required database columns are present
    and flags any warnings for the manual review report.

    Args:
        raw (dict): Raw transaction dict containing keys: row_num, data, conta, tipo,
            setor, categoria, projeto, valor, obs.
        contador (dict): A mutable dictionary tracking content hash counts (for ID generation).

    Returns:
        dict: A dictionary containing:
            - data (datetime.date): Transaction date.
            - conta_nome (str | None): Cleaned account name.
            - tipo (str | None): Parsed direction ('entrada' or 'saida').
            - celula_nome (str | None): Canonical database cell name.
            - categoria_nome (str | None): Cleaned category name.
            - codigo (str | None): Extracted project code.
            - valor (float | None): Parsed float value.
            - obs (str | None): Cleaned observations.
            - external_source (str): Source identifier (sharepoint_caixa).
            - external_id (str): Deterministic content hash ID.
            - gravavel (bool): True if required NOT NULL database fields are valid.
            - revisao (list[str]): List of warnings/reasons why this row needs manual curation.
    """
    revisao: list[str] = []

    # Clean and parse fields using normalize helpers
    conta_nome = norm_text(raw.get("conta"))
    tipo = parse_tipo(raw.get("tipo"))
    valor = parse_valor(raw.get("valor"))
    categoria_nome = norm_text(raw.get("categoria"))
    celula_nome, setor_ok = map_setor(raw.get("setor"))
    codigo = extract_codigo(raw.get("projeto"))
    obs = norm_text(raw.get("obs"))

    # Reference context for validation warnings
    ref = f"linha {raw.get('row_num')} ({raw['data'].isoformat()}"
    ref += f", {obs})" if obs else ")"

    # Validation rules to flag missing NOT NULL values or unrecognized mapping configurations
    if not conta_nome:
        revisao.append(f"sem conta — {ref}")
    if tipo is None:
        revisao.append(f"sem tipo entrada/saída — {ref}")
    if valor is None:
        revisao.append(f"sem valor — {ref}")
    if categoria_nome is None:
        revisao.append(f"sem categoria — {ref}")
    if raw.get("setor") is not None and not setor_ok:
        revisao.append(f"setor desconhecido '{norm_text(raw.get('setor'))}' — {ref}")

    # Generate the unique identifier. We use lowercase normalized values to ensure stability
    # across minor case differences.
    external_id = _external_id(
        raw["data"],
        conta_key=(conta_nome or "").lower(),
        tipo=(tipo or ""),
        sector_key=(celula_nome or norm_text(raw.get("setor")) or "").lower(),
        categoria_key=(categoria_nome or "").lower(),
        valor=(valor or 0.0),
        obs_key=(obs or "").lower(),
        contador=contador,
    )

    # A row is writable only if it has a bank account, direction type, and financial value
    gravavel = bool(conta_nome) and tipo is not None and valor is not None

    return {
        "data": raw["data"],
        "conta_nome": conta_nome,
        "tipo": tipo,
        "celula_nome": celula_nome,      # None implies no mapped cell (General/unknown)
        "categoria_nome": categoria_nome,  # None implies category_id remains NULL
        "codigo": codigo,                # None implies no project linked
        "valor": valor,
        "obs": obs,
        "external_source": EXTERNAL_SOURCE,
        "external_id": external_id,
        "gravavel": gravavel,
        "revisao": revisao,
    }
