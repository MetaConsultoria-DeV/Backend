"""matching.py — Resolve FKs no banco para a ingestão comercial."""

import logging
from typing import Optional
from database import execute_query

logger = logging.getLogger("ingestion.pipefy_comercial.matching")


def resolve_coordenacao(sigla: Optional[str]) -> Optional[int]:
    """Retorna o id da coordenacao pela sigla (TD/GN/OP/CE/DM).
    Siglas sem linha correspondente (ex.: CP/ND) → None (decisão de escopo)."""
    if not sigla:
        return None
    row = execute_query(
        "SELECT id FROM coordenacao WHERE sigla = %s LIMIT 1",
        (sigla,), fetch_one=True
    )
    if row:
        return row["id"]
    logger.info("Coordenação sem linha para sigla '%s' → coordenacao_id NULL", sigla)
    return None
