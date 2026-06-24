"""Module for loading accounting transactions and categories into the MySQL database.

This module implements database upsert (insert or update) operations on both
`categoria_transacao` and `transacao` tables using MySQL's `ON DUPLICATE KEY UPDATE` syntax.
"""

import logging

from database import execute_query

# Logger instance for this module
logger = logging.getLogger("ingestion.contabil.load")


def upsert_categoria(nome: str, tipo: str, celula_id: int | None) -> tuple[int, bool]:
    """Performs an upsert operation on the transaction category table.

    The database lookup/uniqueness is enforced via the unique key constraint on the `nome`
    column (`uk_categoria_transacao_nome`). If a duplicate name is encountered, the category
    fields are updated without overwriting manual curations.

    Args:
        nome (str): The unique name of the transaction category.
        tipo (str): The type of the transaction category (e.g., 'Entrada' or 'Saída').
        celula_id (int | None): The associated cell/business unit ID, if available.

    Returns:
        tuple[int, bool]: A tuple containing:
            - int: The database ID of the category (either newly inserted or existing).
            - bool: True if a new category record was created, False if it already existed.

    Raises:
        RuntimeError: If the category cannot be retrieved after insertion.
    """
    # MySQL rowcount is 1 for a new row insertion, and 2 (or 0) for an update.
    # COALESCE ensures that if a cell_id was manually curated in the database,
    # it won't be overwritten by a NULL value from the spreadsheet.
    rowcount = execute_query(
        """
        INSERT INTO categoria_transacao (nome, tipo, celula_id, ativo)
        VALUES (%s, %s, %s, 1)
        ON DUPLICATE KEY UPDATE
            tipo      = VALUES(tipo),
            celula_id = COALESCE(celula_id, VALUES(celula_id))
        """,
        (nome, tipo, celula_id),
    )
    
    # Retrieve the auto-incremented database ID for the unique category name
    row = execute_query(
        "SELECT id FROM categoria_transacao WHERE nome = %s LIMIT 1",
        (nome,), fetch_one=True,
    )
    if not row:
        raise RuntimeError(f"Falha ao upsert categoria_transacao: {nome}")
    
    # Created is True only when a new row was inserted (rowcount == 1)
    return row["id"], (rowcount == 1)


def upsert_transacao(t: dict) -> bool:
    """Performs an upsert operation on the transactions table.

    Uniqueness is checked against `(external_source, external_id)`.
    If the transaction already exists, fields are updated. The link to `projeto_externo_id`
    is preserved (never regresses to NULL) using COALESCE.

    Args:
        t (dict): A dictionary containing transaction data with the following keys:
            - data: Transaction date.
            - conta_id: Account ID.
            - tipo: Transaction type.
            - categoria_id: Transaction category ID (optional).
            - celula_id: Cell/Business unit ID (optional).
            - valor: Financial value.
            - projeto_externo_id: ID of the external project, if resolved.
            - external_id: The unique ID from the external source.
            - external_source: The string identifying the source system.

    Returns:
        bool: True if the transaction was newly inserted (rowcount == 1),
            False if it was updated or remained unchanged.
    """
    # In MySQL, INSERT ... ON DUPLICATE KEY UPDATE returns:
    # - 1 if the row was inserted as new.
    # - 2 if an existing row was updated.
    # - 0 if an existing row was updated with the same values.
    # The contrato_pagamento_id remains NULL because it is managed separately by
    # the Pipefy synchronization cross-linking process.
    rowcount = execute_query(
        """
        INSERT INTO transacao (
            data, conta_id, tipo, categoria_id, celula_id, valor,
            projeto_externo_id, contrato_pagamento_id, external_id, external_source
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, %s, %s)
        ON DUPLICATE KEY UPDATE
            data               = VALUES(data),
            conta_id           = VALUES(conta_id),
            tipo               = VALUES(tipo),
            categoria_id       = VALUES(categoria_id),
            celula_id          = VALUES(celula_id),
            valor              = VALUES(valor),
            projeto_externo_id = COALESCE(VALUES(projeto_externo_id), projeto_externo_id)
        """,
        (
            t["data"], t["conta_id"], t["tipo"], t.get("categoria_id"),
            t.get("celula_id"), t["valor"], t.get("projeto_externo_id"),
            t["external_id"], t["external_source"],
        ),
    )
    return rowcount == 1

