"""Module for orchestrating the Pipefy Financeiro database synchronization.

Retrieves cards from Pipefy, transforms fields, matches documents or contract numbers to avoid
duplication, and loads data into five schema tables: payment methods, clients, projects,
contracts, and installments.
"""

import logging
from typing import Optional

from .client import fetch_all_cards
from .transform import transform_card
from .matching import resolve_contrato_por_numero
from .load import (
    upsert_forma_pagamento, upsert_cliente, upsert_projeto_externo,
    upsert_contrato, upsert_contrato_pagamento, completar_contrato_existente,
)

# Logger instance for the Pipefy sync module
logger = logging.getLogger("ingestion.pipefy.sync")


def run_sync(dry_run: bool = False) -> dict:
    """Executes a full synchronization from Pipefy Financeiro to the MySQL database.

    Fetches cards from Pipefy, parses fields, matches existing contracts by contract number,
    handles client matching to merge updates, and seeds or updates contract records.

    Args:
        dry_run (bool): If True, runs the extraction and transformation phases but skips
            database modifications.

    Returns:
        dict: A execution summary dictionary containing:
            - lidos (int): Total cards retrieved from Pipefy.
            - ignorados (int): Cards skipped because they lack a contract number in the title.
            - inseridos (int): Number of new contract records inserted.
            - atualizados (int): Number of existing contract records updated.
            - para_revisao (list[str]): List of card IDs marked for review (e.g. variable pricing).
            - erros (list[str]): Error messages encountered during synchronization.
    """
    lidos = 0
    ignorados = 0
    inseridos = 0
    atualizados = 0
    para_revisao = []
    erros = []

    # Iterate through all cards retrieved from Pipefy using the client generator
    for card in fetch_all_cards():
        lidos += 1
        card_id = card.get("id", "?")
        try:
            result = transform_card(card)

            # Filter: Check if the card title contains a valid contract code (NNN.YYYY).
            # If no code is present, skip the card. This is intentional and not logged as an error.
            if not result["codigo"]:
                ignorados += 1
                logger.info("Card %s ignorado: título sem código de contrato (NNN.YYYY)", card_id)
                continue

            # Check if card has variable values or other flags requiring manual attention
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
                continue

            # --- Check: Does a contract with this business key (number) already exist? ---
            # Reuses existing contracts and projects to prevent duplication. If a contract
            # exists, updates its financial metadata (which might have been initialized
            # with placeholder values) and upserts its installments.
            contrato = result["contrato"]
            existente = resolve_contrato_por_numero(contrato["numero"])
            if existente:
                forma_id = upsert_forma_pagamento(result["forma_pagamento"]["nome"])
                if result["cliente"]["nome"]:
                    cliente_id = upsert_cliente(result["cliente"])
                else:
                    cliente_id = existente.get("cliente_id")
                    
                # Merge new financial fields into the manually curated or existing contract
                completar_contrato_existente(existente["id"], contrato, cliente_id, forma_id)
                
                # Load or update associated installments/payment rows
                for parcela in result["parcelas"]:
                    parcela["contrato_id"]        = existente["id"]
                    parcela["cliente_id"]         = cliente_id
                    parcela["projeto_externo_id"] = existente["projeto_externo_id"]
                    parcela["forma_pagamento_id"] = forma_id
                    upsert_contrato_pagamento(parcela)
                atualizados += 1
                logger.info(
                    "Card %s: contrato %s já existia (projeto %s) — completei dados e %d parcelas, sem duplicar",
                    card_id, contrato["numero"], existente["projeto_externo_id"], len(result["parcelas"]),
                )
                continue

            # --- Ingestion Sequence: Parent Entities First ---
            
            # 1. Payment method
            forma_id = upsert_forma_pagamento(result["forma_pagamento"]["nome"])

            # 2. Client
            cliente_id = upsert_cliente(result["cliente"])

            # 3. External project
            projeto_id = upsert_projeto_externo(result["projeto_externo"])

            # 4. Contract
            contrato = result["contrato"]
            contrato["cliente_id"]         = cliente_id
            contrato["projeto_externo_id"] = projeto_id
            contrato["forma_pagamento_id"] = forma_id
            contrato_id, inserido = upsert_contrato(contrato)
            if inserido:
                inseridos += 1
            else:
                atualizados += 1

            # 5. Installments / payments
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
        "ignorados":    ignorados,
        "inseridos":    inseridos,
        "atualizados":  atualizados,
        "para_revisao": para_revisao,
        "erros":        erros,
    }

