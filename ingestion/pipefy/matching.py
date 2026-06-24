"""Module for resolving database references and performing entity matching for Pipefy Financeiro.

Enforces business rules for resolving payment methods, clients, contracts, and projects.
To support robust client matching without complex MySQL collations, client names are
fetched in bulk and normalized within Python.
"""

import logging
from typing import Optional
from database import execute_query

# Logger instance for matching operations
logger = logging.getLogger("ingestion.pipefy.matching")


def resolve_forma_pagamento(nome: str) -> Optional[int]:
    """Resolves the database ID of a payment method by its exact name.

    Args:
        nome (str): The exact name of the payment method to resolve.

    Returns:
        Optional[int]: The database ID of the payment method, or None if not found.
    """
    row = execute_query(
        "SELECT id FROM forma_pagamento WHERE nome = %s LIMIT 1",
        (nome,), fetch_one=True
    )
    if row:
        return row["id"]
    logger.warning("Forma de pagamento não encontrada: '%s'", nome)
    return None


def resolve_cliente(cpf_cnpj: Optional[str], nome_normalizado: str) -> Optional[int]:
    """Matches a client against the database using documents or normalized names.

    First, attempts an exact match using the CPF/CNPJ document (if provided).
    As a fallback, fetches all client profiles, normalizes their database names in Python
    (stripping accents, lowercasing, and collapsing whitespace), and compares them against
    the normalized search key.

    Args:
        cpf_cnpj (Optional[str]): The client document string (CPF or CNPJ).
        nome_normalizado (str): The pre-normalized search string of the client's name.

    Returns:
        Optional[int]: The database ID of the matched client, or None if no match is found.
    """
    if cpf_cnpj:
        row = execute_query(
            "SELECT id FROM cliente WHERE cpf_cnpj = %s LIMIT 1",
            (cpf_cnpj,), fetch_one=True
        )
        if row:
            return row["id"]

    if nome_normalizado:
        # Since MySQL lacks simple accent-insensitive collations across database encodings,
        # we fetch all clients and normalize/compare names using Python's standard library.
        rows = execute_query(
            "SELECT id, nome FROM cliente",
            fetch_all=True
        ) or []
        for r in rows:
            import unicodedata, re
            # Decompose combining unicode characters to strip accents (NFKD)
            nfkd = unicodedata.normalize("NFKD", r["nome"])
            # Remove diacritics, lowercase, collapse spaces, and trim
            norm = re.sub(r"\s+", " ", nfkd.encode("ascii", "ignore").decode("ascii").lower()).strip()
            if norm == nome_normalizado:
                return r["id"]

    return None


def resolve_contrato_por_numero(numero: str) -> Optional[dict]:
    """Retrieves an existing contract record using its unique contract number.

    This prevents duplicate contracts from being created by the ingestion pipeline if a
    contract was already created manually or by another process.

    Args:
        numero (str): The unique contract business key to search for.

    Returns:
        Optional[dict]: A dictionary containing {'id', 'projeto_externo_id', 'cliente_id'}
            if the contract exists, or None if no match is found.
    """
    if not numero:
        return None
    return execute_query(
        "SELECT id, projeto_externo_id, cliente_id FROM contrato WHERE numero = %s LIMIT 1",
        (numero,), fetch_one=True
    )


def resolve_projeto_externo(codigo: str) -> Optional[int]:
    """Resolves the database ID of a project using its external ID (project code).

    Finds the record in the `projeto_externo` table where `external_source` is
    'pipefy_financeiro' and `external_id` matches the project code.

    Args:
        codigo (str): The external project code (e.g. '015.2023').

    Returns:
        Optional[int]: The database ID of the external project, or None if not found.
    """
    if not codigo:
        return None
    row = execute_query(
        "SELECT id FROM projeto_externo WHERE external_source = %s AND external_id = %s LIMIT 1",
        ("pipefy_financeiro", codigo), fetch_one=True
    )
    return row["id"] if row else None

