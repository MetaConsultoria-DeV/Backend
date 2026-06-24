"""Module for transforming raw GraphQL Pipefy Comercial card nodes into structured MySQL entity models.

This module processes data for the sales pipeline (Sales Pipeline). It extracts lead contact
profiles, harvesting origins and loss reasons dynamically from multiple fields using precedence
rules, translates stage labels into terminal statuses, resolves coordination abbreviations,
and converts phase histories into cronological transition logs.
"""

import re
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from .field_map import (
    EXTERNAL_SOURCE, EXTERNAL_SOURCE_PHASE,
    F_NOME, F_EMAIL, F_TELEFONE, F_EMPRESA, F_CARGO,
    F_RESPONSAVEIS, F_VALOR_FECHADO,
    COORD_LABEL_FIELDS, COORD_LABEL_TO_SIGLA,
    ORIGEM_FIELDS, ORIGEM_PRIORITY,
    MOTIVO_PERDA_FIELDS,
    PHASE_STATUS_TERMINAL, STATUS_TERMINAL_DEFAULT,
)

# Logger instance for the Comercial transform module
logger = logging.getLogger("ingestion.pipefy_comercial.transform")


# --- Helpers ---

def _parse_datetime(raw: str) -> Optional[datetime]:
    """Parses standard ISO datetime strings and returns naive datetime objects.

    MySQL DATETIME columns are naive (lack timezone metadata), so tzinfo is discarded.

    Args:
        raw (str): Raw timestamp string.

    Returns:
        Optional[datetime]: Naive datetime object, or None if parsing fails.
    """
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.replace(tzinfo=None)  # Discard timezone info
        except ValueError:
            continue
    return None


def _parse_money(raw) -> Optional[Decimal]:
    """Parses Brazilian currency format or clean numbers into Decimal objects.

    Supports inputs like 'R$ 5.300,50' (Brazilian format) and '5300.50' (standard).

    Args:
        raw: The raw currency value.

    Returns:
        Optional[Decimal]: Decimal parsed value, or None if parsing fails.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    s = re.sub(r"[R$\s]", "", s)
    if "," in s and "." in s:
        # Brazilian format with thousands separator dots and decimal comma (e.g. 1.234,56)
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        # Brazilian format with decimal comma only (e.g. 1234,56)
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except Exception:
        return None


def _field_value(f: dict):
    """Retrieves the appropriate field value based on field type.

    Args:
        f (dict): Individual field node from Pipefy.

    Returns:
        Any: array_value (list) for checklist or assignees, value (str) for standard fields.
    """
    return f.get("array_value") or f.get("value") or ""


def _build_fields_map(card: dict) -> dict:
    """Creates a flat dictionary of field ID to field value mappings.

    Args:
        card (dict): Raw card node dictionary.

    Returns:
        dict: flat key-value dictionary of custom fields.
    """
    fmap = {}
    for f in card.get("fields", []):
        fmap[f["field"]["id"]] = _field_value(f)
    return fmap


def _as_text(val) -> str:
    """Concatenates lists (checklist, assignees) into a comma-separated string.

    Args:
        val: The raw value.

    Returns:
        str: Cleaned string representation.
    """
    if isinstance(val, list):
        return ", ".join(str(v) for v in val if v not in (None, ""))
    return str(val).strip() if val else ""


def _resolve_coord_sigla(card: dict, fmap: dict) -> Optional[str]:
    """Resolves the coordination cell sigla from card labels and custom fields.

    Extracts coordination names from custom fields (`how_hot_is_this_opportunity`, `engenharia`)
    and the card's visual tags/labels. Matches them against the allowed coordination siglas
    (TD, GN, OP, CE, DM).

    Args:
        card (dict): Raw card node.
        fmap (dict): Flattened custom fields map.

    Returns:
        Optional[str]: Mapped abbreviation (sigla) or None.
    """
    candidates = []
    # Collect candidates from label select fields
    for fid in COORD_LABEL_FIELDS:
        candidates.append(_as_text(fmap.get(fid, "")))
    # Collect candidates from visual card labels
    for lbl in card.get("labels", []) or []:
        candidates.append((lbl.get("name") or "").strip())

    for cand in candidates:
        if not cand:
            continue
        # Split candidate strings that contain list separators (e.g. 'OP, CE')
        for token in re.split(r"[,;/]", cand):
            sigla = COORD_LABEL_TO_SIGLA.get(token.strip())
            if sigla:
                return sigla
    return None


def _build_phase_events(card: dict) -> list[dict]:
    """Converts a card's phases history into chronological phase transition logs.

    Sorts phase logs chronologically by `firstTimeIn`.
    Generates a unique `external_event_id` in the format `{card_id}:{phase_id}:{moved_iso}`
    to ensure idempotency. Calculates duration spent in the previous phase.

    Args:
        card (dict): Raw card node.

    Returns:
        list[dict]: chronological phase transition dictionaries ready for insertion.
    """
    history = card.get("phases_history", []) or []
    # Parse and filter transitions containing valid timestamps
    parsed = []
    for h in history:
        ts = _parse_datetime(h.get("firstTimeIn", ""))
        if ts is None:
            continue
        parsed.append({
            "phase_id":   str(h["phase"]["id"]),
            "phase_nome": h["phase"]["name"].strip(),
            "moved_at":   ts,
            "duration":   h.get("duration"),  # Duration in seconds (can be None)
        })
    parsed.sort(key=lambda x: x["moved_at"])

    card_id = card["id"]
    events = []
    for i, cur in enumerate(parsed):
        prev = parsed[i - 1] if i > 0 else None
        moved_iso = cur["moved_at"].strftime("%Y-%m-%dT%H:%M:%S")
        events.append({
            "from_phase_id":   prev["phase_id"] if prev else None,
            "from_phase_nome": prev["phase_nome"] if prev else None,
            "to_phase_id":     cur["phase_id"],
            "to_phase_nome":   cur["phase_nome"],
            "moved_at":        cur["moved_at"],
            "moved_by":        None,  # Not exposed in GraphQL phase history
            "duration_previous_phase_seconds": (
                int(prev["duration"]) if prev and prev["duration"] is not None else None
            ),
            "external_source":   EXTERNAL_SOURCE_PHASE,
            "external_event_id": f"{card_id}:{cur['phase_id']}:{moved_iso}",
            "oportunidade_id": None,  # Resolved during load
        })
    return events


# --- Public API ---

def transform_card(card: dict) -> dict:
    """Transforms a raw Pipefy Sales card node into structured commercial entity models.

    Args:
        card (dict): Raw GraphQL Sales pipeline card node.

    Returns:
        dict: A dictionary containing structured entity maps:
            - card_id (str): Raw card ID.
            - lead (dict): Cleaned lead profile fields.
            - oportunidade (dict): Structured opportunity fields (including phase, terminal status).
            - origens (list[dict]): Extracted lead origin raw values.
            - motivos (list[dict]): Extracted loss reason raw values.
            - _origem_ref (dict | None): Selected primary origin reference based on priority.
            - _motivo_ref (dict | None): Selected primary loss reason reference based on priority.
            - _coord_sigla (str | None): Resolved coordination cell sigla.
            - phase_events (list[dict]): chronological phase transition log dictionaries.
    """
    fmap = _build_fields_map(card)
    card_id = card["id"]

    # --- Lead Profile ---
    lead = {
        "nome":            (_as_text(fmap.get(F_NOME)) or card.get("title", "").strip())[:200],
        "email":           _as_text(fmap.get(F_EMAIL))[:200] or None,
        "telefone":        _as_text(fmap.get(F_TELEFONE))[:50] or None,
        "empresa":         _as_text(fmap.get(F_EMPRESA))[:200] or None,
        "cargo":           _as_text(fmap.get(F_CARGO))[:100] or None,
        "external_source": EXTERNAL_SOURCE,
        "external_id":     card_id,
    }

    # --- Lead Origin (dim_lead_origem) ---
    # Harvest lead origins across multiple stages
    origens = []
    for source_field, fid in ORIGEM_FIELDS.items():
        raw = _as_text(fmap.get(fid))
        if raw:
            origens.append({"source_field": source_field, "raw_value": raw})
            
    # Resolve primary origin reference using precedence configuration (LD overrides Start Form)
    origem_ref = None
    for sf in ORIGEM_PRIORITY:
        match = next((o for o in origens if o["source_field"] == sf), None)
        if match:
            origem_ref = match
            break

    # --- Loss Reasons (dim_motivo_perda) ---
    # Harvest loss reasons across all stages
    motivos = []
    motivo_ref = None
    for fid in MOTIVO_PERDA_FIELDS:
        raw = _as_text(fmap.get(fid))
        if raw:
            entry = {"source_field": fid, "raw_value": raw}
            motivos.append(entry)
            # Select the first non-empty field encountered as the primary reason
            if motivo_ref is None:
                motivo_ref = entry

    # --- Opportunity ---
    current_phase = card.get("current_phase") or {}
    fase_id = str(current_phase.get("id") or "")
    fase_nome = (current_phase.get("name") or "").strip()
    # Resolve the status terminal category
    status_terminal = PHASE_STATUS_TERMINAL.get(fase_id, STATUS_TERMINAL_DEFAULT)

    oportunidade = {
        "fase_atual_nome": fase_nome,
        "fase_atual_id":   fase_id,
        "responsaveis":    _as_text(fmap.get(F_RESPONSAVEIS)) or None,
        "valor_fechado":   _parse_money(fmap.get(F_VALOR_FECHADO)),
        "status_terminal": status_terminal,
        "criado_em":       _parse_datetime(card.get("createdAt", "")),
        "finalizado_em":   _parse_datetime(card.get("finished_at", "")),
        "external_source": EXTERNAL_SOURCE,
        "external_id":     card_id,
        "lead_id":         None,   # Populated during load
        "cliente_id":      None,   # Remains NULL until contract creation
        "origem_id":       None,   # Populated during load
        "motivo_perda_id": None,   # Populated during load
        "coordenacao_id":  None,   # Populated during load
    }

    return {
        "card_id":         card_id,
        "lead":            lead,
        "oportunidade":    oportunidade,
        "origens":         origens,
        "motivos":         motivos,
        "_origem_ref":     origem_ref,
        "_motivo_ref":     motivo_ref,
        "_coord_sigla":    _resolve_coord_sigla(card, fmap),
        "phase_events":    _build_phase_events(card),
    }
