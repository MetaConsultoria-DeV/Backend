"""transform.py — Flatten de um card do Pipefy de Vendas → dicts por tabela MySQL.

Tabelas-alvo (só colunas existentes): leads, oportunidade, dim_lead_origem,
dim_motivo_perda, oportunidade_phase_history. Campo sem coluna é descartado.
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

logger = logging.getLogger("ingestion.pipefy_comercial.transform")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_datetime(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.replace(tzinfo=None)  # MySQL datetime é naive
        except ValueError:
            continue
    return None


def _parse_money(raw) -> Optional[Decimal]:
    """Aceita formato BR ('5.300,00') e normalizado da API ('5300.0')."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    s = re.sub(r"[R$\s]", "", s)
    if "," in s and "." in s:
        # BR: ponto de milhar, vírgula decimal
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        # só vírgula → decimal BR
        s = s.replace(",", ".")
    # só ponto (ou sem separador) → ponto já é decimal
    try:
        return Decimal(s)
    except Exception:
        return None


def _field_value(f: dict):
    """checklist/assignee devolvem array_value; demais devolvem value."""
    return f.get("array_value") or f.get("value") or ""


def _build_fields_map(card: dict) -> dict:
    fmap = {}
    for f in card.get("fields", []):
        fmap[f["field"]["id"]] = _field_value(f)
    return fmap


def _as_text(val) -> str:
    """Junta listas (assignee/checklist) num texto legível."""
    if isinstance(val, list):
        return ", ".join(str(v) for v in val if v not in (None, ""))
    return str(val).strip() if val else ""


def _resolve_coord_sigla(card: dict, fmap: dict) -> Optional[str]:
    """Coordenação: tenta os campos label_select, depois as labels do card.
    Só retorna sigla que exista na tabela `coordenacao` (TD/GN/OP/CE)."""
    candidates = []
    for fid in COORD_LABEL_FIELDS:
        candidates.append(_as_text(fmap.get(fid, "")))
    for lbl in card.get("labels", []) or []:
        candidates.append((lbl.get("name") or "").strip())

    for cand in candidates:
        if not cand:
            continue
        # campo pode trazer "OP, CE" — pega o primeiro token conhecido
        for token in re.split(r"[,;/]", cand):
            sigla = COORD_LABEL_TO_SIGLA.get(token.strip())
            if sigla:
                return sigla
    return None


def _build_phase_events(card: dict) -> list[dict]:
    """Converte phases_history em eventos de transição (append-only, idempotente).

    Um evento por ENTRADA em fase, em ordem cronológica. A duração da fase ANTERIOR
    vem do campo `duration` (segundos) daquela fase.
    """
    history = card.get("phases_history", []) or []
    # Ordena por firstTimeIn
    parsed = []
    for h in history:
        ts = _parse_datetime(h.get("firstTimeIn", ""))
        if ts is None:
            continue
        parsed.append({
            "phase_id":   str(h["phase"]["id"]),
            "phase_nome": h["phase"]["name"].strip(),
            "moved_at":   ts,
            "duration":   h.get("duration"),  # segundos na fase (pode ser None)
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
            "moved_by":        None,  # phases_history não expõe o autor
            "duration_previous_phase_seconds": (
                int(prev["duration"]) if prev and prev["duration"] is not None else None
            ),
            "external_source":   EXTERNAL_SOURCE_PHASE,
            "external_event_id": f"{card_id}:{cur['phase_id']}:{moved_iso}",
            # FK preenchida no load
            "oportunidade_id": None,
        })
    return events


# ── Função pública ──────────────────────────────────────────────────────────

def transform_card(card: dict) -> dict:
    fmap = _build_fields_map(card)
    card_id = card["id"]

    # ── lead ─────────────────────────────────────────────────────────────────
    lead = {
        "nome":            (_as_text(fmap.get(F_NOME)) or card.get("title", "").strip())[:200],
        "email":           _as_text(fmap.get(F_EMAIL))[:200] or None,
        "telefone":        _as_text(fmap.get(F_TELEFONE))[:50] or None,
        "empresa":         _as_text(fmap.get(F_EMPRESA))[:200] or None,
        "cargo":           _as_text(fmap.get(F_CARGO))[:100] or None,
        "external_source": EXTERNAL_SOURCE,
        "external_id":     card_id,
    }

    # ── dim_lead_origem (auto-vivify raw) ────────────────────────────────────
    origens = []
    for source_field, fid in ORIGEM_FIELDS.items():
        raw = _as_text(fmap.get(fid))
        if raw:
            origens.append({"source_field": source_field, "raw_value": raw})
    # qual origem a oportunidade aponta (prioridade ld > start_form)
    origem_ref = None
    for sf in ORIGEM_PRIORITY:
        match = next((o for o in origens if o["source_field"] == sf), None)
        if match:
            origem_ref = match
            break

    # ── dim_motivo_perda (auto-vivify raw) ───────────────────────────────────
    motivos = []
    motivo_ref = None
    for fid in MOTIVO_PERDA_FIELDS:
        raw = _as_text(fmap.get(fid))
        if raw:
            entry = {"source_field": fid, "raw_value": raw}
            motivos.append(entry)
            if motivo_ref is None:  # primeiro na ordem de prioridade
                motivo_ref = entry

    # ── oportunidade ─────────────────────────────────────────────────────────
    current_phase = card.get("current_phase") or {}
    fase_id = str(current_phase.get("id") or "")
    fase_nome = (current_phase.get("name") or "").strip()
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
        # FKs resolvidas no load
        "lead_id":         None,
        "cliente_id":      None,   # fica NULL até virar contrato
        "origem_id":       None,
        "motivo_perda_id": None,
        "coordenacao_id":  None,
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
