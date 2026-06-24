"""Module for performing entity matching for Pipefy Comercial.

Resolves foreign key references in the database, specifically matching coordination cells
by their abbreviated labels (sigla).
"""

import logging
from typing import Optional
from database import execute_query

# Logger instance for Comercial matching operations
logger = logging.getLogger("ingestion.pipefy_comercial.matching")


def resolve_coordenacao(sigla: Optional[str]) -> Optional[int]:
    """Resolves the database ID of a coordination cell by its abbreviation (sigla).

    Valid abbreviations include TD, GN, OP, CE, and DM. Unmapped labels (such as CP or ND)
    will return None as they do not have corresponding rows in the `coordenacao` table.

    Args:
        sigla (Optional[str]): The cell abbreviation (e.g. 'OP').

    Returns:
        Optional[int]: The database ID of the matching cell, or None if not found/unmapped.
    """
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

