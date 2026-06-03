"""sync.py — Orquestra extract → transform → load do Pipefy de Vendas → MySQL."""

import logging

from .client import fetch_all_cards
from .transform import transform_card
from .matching import resolve_coordenacao
from .load import (
    upsert_dim_origem, upsert_dim_motivo, upsert_lead,
    upsert_oportunidade, upsert_phase_event,
)

logger = logging.getLogger("ingestion.pipefy_comercial.sync")


def run_sync(dry_run: bool = False) -> dict:
    """
    Sincroniza o Pipefy de Vendas (Sales Pipeline) → MySQL comercial.

    Returns:
        {
          "lidos": int,
          "inseridos": int,          # oportunidades criadas
          "atualizados": int,        # oportunidades já existentes
          "fases_registradas": int,  # eventos de histórico novos
          "dims_novas": list[str],   # origens/motivos vistos pela 1ª vez (mapear canônico)
          "erros": list[str],
        }
    """
    lidos = 0
    inseridos = 0
    atualizados = 0
    fases_registradas = 0
    dims_novas: list[str] = []
    _dims_seen: set[str] = set()
    erros: list[str] = []

    def _flag_dim(prefixo: str, source_field: str, raw: str):
        chave = f"{prefixo}[{source_field}]: {raw}"
        if chave not in _dims_seen:
            _dims_seen.add(chave)
            dims_novas.append(chave)

    for card in fetch_all_cards():
        lidos += 1
        card_id = card.get("id", "?")
        try:
            result = transform_card(card)

            if dry_run:
                logger.info(
                    "[DRY-RUN] Card %s | lead=%s | fase=%s | status=%s | origens=%d | motivos=%d | eventos=%d",
                    card_id,
                    result["lead"]["nome"],
                    result["oportunidade"]["fase_atual_nome"],
                    result["oportunidade"]["status_terminal"],
                    len(result["origens"]), len(result["motivos"]),
                    len(result["phase_events"]),
                )
                continue

            # ── 1. dim_lead_origem (auto-vivify) ────────────────────────────
            origem_ids = {}  # (source_field, raw) -> id
            for o in result["origens"]:
                oid, is_new = upsert_dim_origem(o["source_field"], o["raw_value"])
                origem_ids[(o["source_field"], o["raw_value"])] = oid
                if is_new:
                    _flag_dim("origem", o["source_field"], o["raw_value"])

            # ── 2. dim_motivo_perda (auto-vivify) ───────────────────────────
            motivo_ids = {}
            for m in result["motivos"]:
                mid, is_new = upsert_dim_motivo(m["source_field"], m["raw_value"])
                motivo_ids[(m["source_field"], m["raw_value"])] = mid
                if is_new:
                    _flag_dim("motivo", m["source_field"], m["raw_value"])

            # ── 3. leads ────────────────────────────────────────────────────
            lead_id = upsert_lead(result["lead"])

            # ── 4. oportunidade ─────────────────────────────────────────────
            opp = result["oportunidade"]
            opp["lead_id"] = lead_id
            opp["coordenacao_id"] = resolve_coordenacao(result["_coord_sigla"])
            ref_o = result["_origem_ref"]
            if ref_o:
                opp["origem_id"] = origem_ids.get((ref_o["source_field"], ref_o["raw_value"]))
            ref_m = result["_motivo_ref"]
            if ref_m:
                opp["motivo_perda_id"] = motivo_ids.get((ref_m["source_field"], ref_m["raw_value"]))

            opp_id, inserido = upsert_oportunidade(opp)
            if inserido:
                inseridos += 1
            else:
                atualizados += 1

            # ── 5. oportunidade_phase_history ───────────────────────────────
            for ev in result["phase_events"]:
                ev["oportunidade_id"] = opp_id
                if upsert_phase_event(ev):
                    fases_registradas += 1

        except Exception as exc:
            logger.exception("Erro ao processar card %s", card_id)
            erros.append(f"card {card_id}: {exc}")

    return {
        "lidos":             lidos,
        "inseridos":         inseridos,
        "atualizados":       atualizados,
        "fases_registradas": fases_registradas,
        "dims_novas":        dims_novas,
        "erros":             erros,
    }
