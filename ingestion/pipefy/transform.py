"""Module for transforming raw GraphQL Pipefy card nodes into structured MySQL entity models.

This module acts as the semantic translation layer for Pipefy Financeiro. It extracts
unstructured form fields, normalizes names and documents, splits contract values into individual
installments (pivot operation), handles decimal precision, and parses phase histories to
extract process timestamps.
"""

import re
import unicodedata
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from .field_map import (
    EXTERNAL_SOURCE,
    F_NOME_PROJETO, F_NOME_EXTERNO, F_CLIENTE, F_CPF_CNPJ,
    F_VALOR_TOTAL, F_FORMA_PAGAMENTO, F_QTD_PARCELAS,
    F_VENCIMENTO_BASE, F_RECORRENCIA, F_VALOR_VARIAVEL,
    F_ESTIMATIVA_PPP, F_EMAIL_FATURAMENTO, F_TELEFONE,
    PARCELA_FIELD_IDS,
    PHASE_NAME_EM_PAGAMENTO, PHASE_NAME_CONCLUIDO, PHASE_NAME_CANCELADO,
)

# Logger instance for the transformation process
logger = logging.getLogger("ingestion.pipefy.transform")

# --- Helpers ---

def _normalize_name(text: str) -> str:
    """Normalizes names by lowercasing, removing accents, and collapsing spaces.

    Used as the comparison key for name-based matching of clients.

    Args:
        text (str): The raw text to normalize.

    Returns:
        str: The normalized name key.
    """
    if not text:
        return ""
    # Normalize unicode text (decomposing accents)
    nfkd = unicodedata.normalize("NFKD", text)
    # Strip diacritics / accents
    ascii_ = nfkd.encode("ascii", "ignore").decode("ascii")
    # Collapse multiple whitespace characters into a single space
    return re.sub(r"\s+", " ", ascii_.lower()).strip()


def _normalize_cpf_cnpj(raw: str) -> Optional[str]:
    """Extracts only digits from CPF/CNPJ and validates string length.

    Args:
        raw (str): The raw document string.

    Returns:
        Optional[str]: Normalized digit string (11 digits for CPF, 14 for CNPJ), or None.
    """
    if not raw:
        return None
    # Strip any non-digit characters
    digits = re.sub(r"\D", "", raw)
    if len(digits) not in (11, 14):
        return None
    return digits


def _parse_decimal(raw: str) -> Optional[Decimal]:
    """Parses raw Brazilian currency strings into Decimal numbers.

    Args:
        raw (str): The currency text (e.g. 'R$ 1.500,50').

    Returns:
        Optional[Decimal]: Decimal object, or None if parsing fails.
    """
    if not raw:
        return None
    # Remove R$ currency symbol, spaces, and thousands-separator dots; swap comma for dot decimal point
    cleaned = re.sub(r"[R$\s]", "", raw).replace(".", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except Exception:
        return None


def _parse_int(raw: str) -> Optional[int]:
    """Parses numeric string values into integers.

    Args:
        raw (str): Raw string input.

    Returns:
        Optional[int]: The parsed integer, or None.
    """
    if not raw:
        return None
    try:
        return int(re.sub(r"\D", "", raw))
    except Exception:
        return None


def _parse_datetime(raw: str) -> Optional[datetime]:
    """Parses various ISO/Pipefy datetime string formats.

    Args:
        raw (str): Raw datetime string.

    Returns:
        Optional[datetime]: The parsed datetime object, or None.
    """
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _parse_date(raw: str) -> Optional[date]:
    """Parses datetime strings into date objects.

    Args:
        raw (str): Raw string.

    Returns:
        Optional[date]: Parsed date, or None.
    """
    dt = _parse_datetime(raw)
    return dt.date() if dt else None


def _extract_code(title: str) -> Optional[str]:
    """Extracts project contract codes (e.g. 'NNN.YYYY') from the card's title.

    Matches code patterns at the start of the card title.

    Args:
        title (str): Card title (e.g., '005.2023 - Projeto de Consultoria').

    Returns:
        Optional[str]: Extracted code matching NNN.YYYY, or None.
    """
    if not title:
        return None
    # Match code sequence (exactly three digits, a dot, and four digits) at start of title
    m = re.match(r"^(\d{3}\.\d{4})", title.strip())
    return m.group(1) if m else None


def _build_fields_map(card: dict) -> dict:
    """Builds a flat dictionary mapping field IDs to their values.

    Args:
        card (dict): Raw GraphQL node dictionary of a Pipefy card.

    Returns:
        dict: A flat dictionary of field ID to field value mappings.
    """
    fmap = {}
    for f in card.get("fields", []):
        fid = f["field"]["id"]
        # checklist_vertical uses array_value; other types use value
        val = f.get("array_value") or f.get("value") or ""
        fmap[fid] = val
    return fmap


def _get_phase_timestamp(card: dict, phase_name: str) -> Optional[datetime]:
    """Retrieves the timestamp of when the card first entered a specific phase.

    Args:
        card (dict): Card node containing phases_history.
        phase_name (str): Case-insensitive phase name to search.

    Returns:
        Optional[datetime]: Datetime of the first entry, or None if not found.
    """
    for ph in card.get("phases_history", []):
        if ph["phase"]["name"].strip().lower() == phase_name.lower():
            return _parse_datetime(ph.get("firstTimeIn", ""))
    return None


# --- Public API ---

def transform_card(card: dict) -> dict:
    """Transforms a raw Pipefy card node into structured database models.

    Maps custom card fields to schema definitions, calculates contract numbers,
    determines process stage timestamps, and generates individual installment (payment) rows.
    Installment total value is split evenly, with rounding remainders absorbed by the last installment.

    Args:
        card (dict): Raw GraphQL Pipefy card node.

    Returns:
        dict: Dictionary containing structured target entity maps:
            - card_id (str): Raw card ID.
            - codigo (str | None): Extracted project code.
            - forma_pagamento (dict): Payment method metadata.
            - cliente (dict): Normalised client fields.
            - projeto_externo (dict): Project metadata.
            - contrato (dict): Contract properties (including status, phase history).
            - parcelas (list[dict]): Pivoted list of contract payment installments.
            - para_revisao (bool): True if the card is flagged for manual pricing review.
    """
    fmap = _build_fields_map(card)
    card_id = card["id"]
    title   = card.get("title", "")
    codigo  = _extract_code(title)

    # --- Payment Method ---
    forma_nome = (fmap.get(F_FORMA_PAGAMENTO) or "").strip() or "Boleto"
    forma_pagamento = {"nome": forma_nome}

    # --- Client ---
    nome_cliente  = (fmap.get(F_CLIENTE) or "").strip()
    cpf_cnpj_raw  = fmap.get(F_CPF_CNPJ) or ""
    cpf_cnpj      = _normalize_cpf_cnpj(cpf_cnpj_raw)
    email         = (fmap.get(F_EMAIL_FATURAMENTO) or "").strip() or None
    telefone      = (fmap.get(F_TELEFONE) or "").strip() or None

    cliente = {
        "nome":            nome_cliente,
        "nome_normalizado": _normalize_name(nome_cliente),
        "cpf_cnpj":        cpf_cnpj,
        "email":           email,
        "telefone":        telefone,
        "external_source": EXTERNAL_SOURCE,
        "external_id":     card_id,
    }

    # --- External Project ---
    nome_proj_raw   = (fmap.get(F_NOME_PROJETO) or "").strip()
    # Remove project code prefix (e.g. '008.2026 - ') from the project name
    nome_proj       = re.sub(r"^\d{3}\.\d{4}\s*[-–]\s*", "", nome_proj_raw).strip()
    descricao_proj  = (fmap.get(F_NOME_EXTERNO) or "").strip() or None

    projeto_externo = {
        "nome":             nome_proj or nome_proj_raw,
        "descricao_projeto": descricao_proj,
        "external_source":  EXTERNAL_SOURCE,
        "external_id":      codigo or card_id,   # Project code serves as matching key
    }

    # --- Contract ---
    valor_total      = _parse_decimal(fmap.get(F_VALOR_TOTAL) or "")
    qtd_parcelas     = _parse_int(fmap.get(F_QTD_PARCELAS) or "")
    estimativa_ppp   = _parse_decimal(fmap.get(F_ESTIMATIVA_PPP) or "")
    venc_base_raw    = fmap.get(F_VENCIMENTO_BASE) or ""
    venc_base        = _parse_date(venc_base_raw)
    fase_atual       = (card.get("current_phase") or {}).get("name", "").strip()

    # The project code is the unique contract business key. Falls back to Card ID.
    numero_contrato = codigo if codigo else f"FIN-{card_id}"

    # Extract phase entry timestamps
    data_inicio_pagamento = _get_phase_timestamp(card, PHASE_NAME_EM_PAGAMENTO)
    finalizado_em = (
        _get_phase_timestamp(card, PHASE_NAME_CONCLUIDO)
        or _get_phase_timestamp(card, PHASE_NAME_CANCELADO)
    )

    contrato = {
        "numero":               numero_contrato,
        "valor_total":          valor_total,
        "quantidade_parcelas":  qtd_parcelas,
        "estimativa_gastos_ppp": estimativa_ppp,
        "fase_atual":           fase_atual,
        "data_vencimento_base": venc_base,
        "data_inicio_pagamento": data_inicio_pagamento,
        "finalizado_em":        finalizado_em,
        "external_source":      EXTERNAL_SOURCE,
        "external_id":          card_id,
        "cliente_id":           None,  # Populated during matching/load
        "projeto_externo_id":   None,  # Populated during matching/load
        "forma_pagamento_id":   None,  # Populated during matching/load
        "_forma_pagamento_nome": forma_nome,
    }

    # --- Pivot: Installments (contrato_pagamento) ---
    valor_variavel = (fmap.get(F_VALOR_VARIAVEL) or "").strip().lower()
    # Cards flagged with variable/extra pricing require manual spreadsheet curation
    para_revisao   = valor_variavel in ("sim", "yes", "s")
    recorrencia    = (fmap.get(F_RECORRENCIA) or "").strip().lower()
    parcelas       = []

    if qtd_parcelas and qtd_parcelas > 0:
        if para_revisao:
            logger.warning("Card %s marcado para revisão (valor variável)", card_id)
        else:
            # Distribute contract value evenly. Rounding decimals are absorbed by the last installment.
            if valor_total:
                unit = (valor_total / qtd_parcelas).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                soma = unit * (qtd_parcelas - 1)
                ultima = valor_total - soma
            else:
                unit = ultima = Decimal("0.00")

            for n in range(1, qtd_parcelas + 1):
                # Retrieve the checkbox indicating payment status for this installment
                field_id = PARCELA_FIELD_IDS[n - 1] if n <= len(PARCELA_FIELD_IDS) else None
                raw_val  = fmap.get(field_id, "") if field_id else ""

                if isinstance(raw_val, list):
                    pago = any("paga" in str(v).lower() for v in raw_val)
                else:
                    pago = "paga" in str(raw_val).lower()

                # Calculate due dates (increments by 30 days if monthly)
                if venc_base and "mensal" in recorrencia:
                    data_venc = venc_base + timedelta(days=30 * (n - 1))
                else:
                    data_venc = venc_base

                valor_parc = ultima if n == qtd_parcelas else unit

                parcelas.append({
                    "numero_parcela":  n,
                    "total_parcelas":  qtd_parcelas,
                    "valor":           valor_parc,
                    "data_vencimento": data_venc,
                    "data_pagamento":  None,
                    "status":          "pago" if pago else "pendente",
                    "external_source": EXTERNAL_SOURCE,
                    "external_id":     f"{card_id}-p{n}",
                    "contrato_id":          None,  # Populated during load
                    "cliente_id":           None,  # Populated during load
                    "projeto_externo_id":   None,  # Populated during load
                    "forma_pagamento_id":   None,  # Populated during load
                })

    return {
        "card_id":        card_id,
        "codigo":         codigo,
        "forma_pagamento": forma_pagamento,
        "cliente":        cliente,
        "projeto_externo": projeto_externo,
        "contrato":       contrato,
        "parcelas":       parcelas,
        "para_revisao":   para_revisao,
    }

