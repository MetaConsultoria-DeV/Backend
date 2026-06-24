"""Module for orchestrating the Pipefy Comercial (Sales Pipeline) synchronization.

Coordinates the extraction of sales pipeline cards, maps lead details and opportunity statuses,
performs dynamic dimension seeding (for origins and loss reasons), and runs database upsert operations.
Supports both batch runs (`run_sync`) and single card webhook updates (`run_sync_card`, `run_delete_card`).
"""

import logging

from .client import fetch_all_cards, fetch_card_by_id
from .transform import transform_card
from .matching import resolve_coordenacao
from .field_map import EXTERNAL_SOURCE
from .load import (
    upsert_dim_origem, upsert_dim_motivo, upsert_lead,
    upsert_oportunidade, upsert_phase_event, delete_oportunidade_by_external,
)

# Logger instance for the Comercial sync module
logger = logging.getLogger("ingestion.pipefy_comercial.sync")


def _new_acc() -> dict:
    """Helper to initialize the synchronization metrics accumulator.

    Returns:
        dict: Initialized counters dictionary.
    """
    return {
        "inseridos":         0,
        "atualizados":       0,
        "fases_registradas": 0,
        "dims_novas":        [],
        "_dims_seen":        set(),
    }


def _flag_dim(acc: dict, prefixo: str, source_field: str, raw: str):
    """Flags a newly discovered raw value in dimension tables.

    This warning list prompts administrators to map the raw value to a canonical one.

    Args:
        acc (dict): The active metrics accumulator.
        prefixo (str): Dimension prefix ('origem' or 'motivo').
        source_field (str): Field identifier.
        raw (str): Raw unmapped text value.
    """
    chave = f"{prefixo}[{source_field}]: {raw}"
    if chave not in acc["_dims_seen"]:
        acc["_dims_seen"].add(chave)
        acc["dims_novas"].append(chave)


def _resumo(acc: dict, lidos: int, erros: list[str]) -> dict:
    """Constructs the standard synchronization execution summary.

    Args:
        acc (dict): The active metrics accumulator.
        lidos (int): Total records read.
        erros (list[str]): Errors logged.

    Returns:
        dict: Standardized sync response dictionary.
    """
    return {
        "lidos":             lidos,
        "inseridos":         acc["inseridos"],
        "atualizados":       acc["atualizados"],
        "fases_registradas": acc["fases_registradas"],
        "dims_novas":        acc["dims_novas"],
        "erros":             erros,
    }


def _process_card(card: dict, acc: dict, dry_run: bool = False) -> None:
    """Transforms and loads a single card into the database.

    Runs the transformation pipeline, seeds dimensions (auto-vivify), creates the lead,
    resolves cell coordination and parent references, and commits the opportunity and
    historical phase transitions.

    Args:
        card (dict): Raw card node payload from Pipefy API.
        acc (dict): Metrics accumulator to record inserts and updates.
        dry_run (bool): If True, logs metadata and skips database writes.
    """
    result = transform_card(card)

    if dry_run:
        logger.info(
            "[DRY-RUN] Card %s | lead=%s | fase=%s | status=%s | origens=%d | motivos=%d | eventos=%d",
            card.get("id", "?"),
            result["lead"]["nome"],
            result["oportunidade"]["fase_atual_nome"],
            result["oportunidade"]["status_terminal"],
            len(result["origens"]), len(result["motivos"]),
            len(result["phase_events"]),
        )
        return

    # --- Phase 1: Seed Lead Origins ---
    origem_ids = {}  # Cache resolved mapping IDs to prevent lookup queries
    for o in result["origens"]:
        oid, is_new = upsert_dim_origem(o["source_field"], o["raw_value"])
        origem_ids[(o["source_field"], o["raw_value"])] = oid
        if is_new:
            _flag_dim(acc, "origem", o["source_field"], o["raw_value"])

    # --- Phase 2: Seed Loss Reasons ---
    motivo_ids = {}
    for m in result["motivos"]:
        mid, is_new = upsert_dim_motivo(m["source_field"], m["raw_value"])
        motivo_ids[(m["source_field"], m["raw_value"])] = mid
        if is_new:
            _flag_dim(acc, "motivo", m["source_field"], m["raw_value"])

    # --- Phase 3: Load Lead ---
    lead_id = upsert_lead(result["lead"])

    # --- Phase 4: Load Opportunity ---
    opp = result["oportunidade"]
    opp["lead_id"] = lead_id
    # Resolve cell abbreviation (sigla) to its database ID
    opp["coordenacao_id"] = resolve_coordenacao(result["_coord_sigla"])
    
    # Resolve the active lead origin reference using the priority config
    ref_o = result["_origem_ref"]
    if ref_o:
        opp["origem_id"] = origem_ids.get((ref_o["source_field"], ref_o["raw_value"]))
        
    # Resolve the active loss reason reference using the priority config
    ref_m = result["_motivo_ref"]
    if ref_m:
        opp["motivo_perda_id"] = motivo_ids.get((ref_m["source_field"], ref_m["raw_value"]))

    opp_id, inserido = upsert_oportunidade(opp)
    if inserido:
        acc["inseridos"] += 1
    else:
        acc["atualizados"] += 1

    # --- Phase 5: Load historical events ---
    for ev in result["phase_events"]:
        ev["oportunidade_id"] = opp_id
        if upsert_phase_event(ev):
            acc["fases_registradas"] += 1


def run_sync(dry_run: bool = False) -> dict:
    """Executes a full synchronization of the Comercial pipeline cards to MySQL.

    Used by manual batch synchronizations and reconciliation loops.

    Args:
        dry_run (bool): If True, parses and processes card structures but skips
            persistent database writes.

    Returns:
        dict: A summary dictionary of batch execution statistics.
    """
    acc = _new_acc()
    lidos = 0
    erros: list[str] = []

    for card in fetch_all_cards():
        lidos += 1
        card_id = card.get("id", "?")
        try:
            _process_card(card, acc, dry_run=dry_run)
        except Exception as exc:
            logger.exception("Erro ao processar card %s", card_id)
            erros.append(f"card {card_id}: {exc}")

    return _resumo(acc, lidos, erros)


def run_sync_card(card_id: str, dry_run: bool = False) -> dict:
    """Executes an incremental single-card synchronization (triggered by webhook).

    Fetches the specific card from Pipefy, runs transformation rules, and updates
    or inserts the opportunity. This operation is idempotent.

    Args:
        card_id (str): The unique identifier of the target card.
        dry_run (bool): If True, skips writing changes to the database.

    Returns:
        dict: A summary dictionary of the single card execution.
    """
    acc = _new_acc()
    erros: list[str] = []

    card = fetch_card_by_id(card_id)
    if card is None:
        return _resumo(acc, 0, [f"card {card_id}: não encontrado no Pipefy"])

    try:
        _process_card(card, acc, dry_run=dry_run)
    except Exception as exc:
        logger.exception("Erro ao processar card %s", card_id)
        erros.append(f"card {card_id}: {exc}")

    return _resumo(acc, 1, erros)


def run_delete_card(card_id: str, dry_run: bool = False) -> dict:
    """Deletes a sales opportunity referenced by a deleted card ID (triggered by webhook).

    Since the card has been deleted from Pipefy, this function operates directly on the
    external ID reference without attempting an API fetch. Cascades deletions to history logs.

    Args:
        card_id (str): The unique card identifier.
        dry_run (bool): If True, logs deletion metadata but skips database updates.

    Returns:
        dict: Execution metrics details containing deleted row count.
    """
    if dry_run:
        logger.info("[DRY-RUN] Deletaria oportunidade external_id=%s", card_id)
        return {"lidos": 1, "removidos": 0, "erros": []}

    try:
        removidos = delete_oportunidade_by_external(EXTERNAL_SOURCE, card_id)
        logger.info("Delete card %s: %d oportunidade(s) removida(s)", card_id, removidos)
        return {"lidos": 1, "removidos": removidos, "erros": []}
    except Exception as exc:
        logger.exception("Erro ao deletar card %s", card_id)
        return {"lidos": 1, "removidos": 0, "erros": [f"card {card_id}: {exc}"]}

