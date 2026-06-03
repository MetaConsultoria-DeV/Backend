"""sync.py — Orquestra extract → transform → load e retorna resumo."""

import logging
from typing import Optional

from .client import fetch_all_cards
from .transform import transform_card
from .load import (
    upsert_forma_pagamento, upsert_cliente, upsert_projeto_externo,
    upsert_contrato, upsert_contrato_pagamento,
)

logger = logging.getLogger("ingestion.pipefy.sync")


def run_sync(dry_run: bool = False) -> dict:
    """
    Executa a sincronização completa do Pipefy Financeiro → MySQL.

    Args:
        dry_run: Se True, roda toda a lógica mas não grava no banco.

    Returns:
        {
          "lidos": int,
          "inseridos": int,
          "atualizados": int,
          "para_revisao": list[str],   # card_ids com valor variável
          "erros": list[str],
        }
    """
    lidos = 0
    inseridos = 0
    atualizados = 0
    para_revisao = []
    erros = []

    for card in fetch_all_cards():
        lidos += 1
        card_id = card.get("id", "?")
        try:
            result = transform_card(card)

            if result["para_revisao"]:
                para_revisao.append(card_id)
                logger.warning("Card %s: marcado para revisão (valor variável)", card_id)

            if dry_run:
                logger.info(
                    "[DRY-RUN] Card %s | cliente=%s | projeto=%s | parcelas=%d",
                    card_id,
                    result["cliente"]["nome"],
                    result["projeto_externo"]["external_id"],
                    len(result["parcelas"]),
                )
                # Em dry-run não consultamos o banco; contamos tudo como "lido".
                continue

            # ── 1. forma_pagamento ──────────────────────────────────────────
            forma_id = upsert_forma_pagamento(result["forma_pagamento"]["nome"])

            # ── 2. cliente ──────────────────────────────────────────────────
            cliente_id = upsert_cliente(result["cliente"])

            # ── 3. projeto_externo ──────────────────────────────────────────
            projeto_id = upsert_projeto_externo(result["projeto_externo"])

            # ── 4. contrato ─────────────────────────────────────────────────
            contrato = result["contrato"]
            contrato["cliente_id"]         = cliente_id
            contrato["projeto_externo_id"] = projeto_id
            contrato["forma_pagamento_id"] = forma_id
            contrato_id, inserido = upsert_contrato(contrato)
            if inserido:
                inseridos += 1
            else:
                atualizados += 1

            # ── 5. contrato_pagamento (parcelas) ────────────────────────────
            for parcela in result["parcelas"]:
                parcela["contrato_id"]         = contrato_id
                parcela["cliente_id"]          = cliente_id
                parcela["projeto_externo_id"]  = projeto_id
                parcela["forma_pagamento_id"]  = forma_id
                upsert_contrato_pagamento(parcela)

        except Exception as exc:
            logger.exception("Erro ao processar card %s", card_id)
            erros.append(f"card {card_id}: {exc}")

    return {
        "lidos":        lidos,
        "inseridos":    inseridos,
        "atualizados":  atualizados,
        "para_revisao": para_revisao,
        "erros":        erros,
    }
