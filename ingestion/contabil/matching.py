"""Module for performing database lookups and resolving foreign keys during accounting ingestion.

This module caches lookup maps in memory to minimize database roundtrips during ingestion.
Keys are normalized using `norm_key` to make matching robust against differences in casing,
whitespace, or accents.
"""

import logging

from database import execute_query
from .normalize import norm_key

# Logger instance for the matching module
logger = logging.getLogger("ingestion.contabil.matching")


def carregar_mapas() -> dict:
    """Pre-loads lookup maps from the database for resolving foreign keys.

    Fetches accounts, cells, categories, projects, and contracts in bulk. It normalizes names
    to create dictionary mappings. For projects, it maps from the contract number (which is stable
    and matches the code structure in spreadsheet lines like `NNN.AAAA`) to the external project ID,
    with a fallback mapping from the project's external ID directly.

    Returns:
        dict: A dictionary containing lookup maps:
            - 'conta': Mapping from normalized account name to account ID.
            - 'celula': Mapping from normalized cell name to cell ID.
            - 'categoria': Mapping from normalized category name to category ID.
            - 'projeto': Mapping from contract number or project external ID string to project ID.
    """
    contas = execute_query("SELECT id, nome FROM conta_bancaria", fetch_all=True) or []
    celulas = execute_query("SELECT id, nome FROM celula", fetch_all=True) or []
    categorias = execute_query("SELECT id, nome FROM categoria_transacao", fetch_all=True) or []
    projetos = execute_query(
        "SELECT id, external_id FROM projeto_externo WHERE external_id IS NOT NULL",
        fetch_all=True,
    ) or []
    contratos = execute_query(
        "SELECT numero, projeto_externo_id FROM contrato "
        "WHERE numero IS NOT NULL AND projeto_externo_id IS NOT NULL",
        fetch_all=True,
    ) or []

    # Map projects primarily by contract numbers (e.g. "NNN.YYYY") since this is the stable
    # reference in spreadsheets. Fallback to external_id if no contract matches.
    projeto_map = {str(r["external_id"]).strip(): r["id"] for r in projetos}
    projeto_map.update({str(r["numero"]).strip(): r["projeto_externo_id"] for r in contratos})

    return {
        "conta": {norm_key(r["nome"]): r["id"] for r in contas},
        "celula": {norm_key(r["nome"]): r["id"] for r in celulas},
        "categoria": {norm_key(r["nome"]): r["id"] for r in categorias},
        "projeto": projeto_map,
    }


def resolve_conta(mapas: dict, nome) -> int | None:
    """Resolves the database ID of an account by its name.

    Args:
        mapas (dict): The dictionary of pre-loaded lookup maps.
        nome (str or None): The name of the bank account to resolve.

    Returns:
        int | None: The database ID of the matching account, or None if not found/provided.
    """
    return mapas["conta"].get(norm_key(nome)) if nome else None


def resolve_celula(mapas: dict, nome) -> int | None:
    """Resolves the database ID of a cell/business unit by its name.

    Args:
        mapas (dict): The dictionary of pre-loaded lookup maps.
        nome (str or None): The name of the cell to resolve.

    Returns:
        int | None: The database ID of the matching cell, or None if not found/provided.
    """
    return mapas["celula"].get(norm_key(nome)) if nome else None


def resolve_categoria(mapas: dict, nome) -> int | None:
    """Resolves the database ID of a transaction category by its name.

    Args:
        mapas (dict): The dictionary of pre-loaded lookup maps.
        nome (str or None): The category name to resolve.

    Returns:
        int | None: The database ID of the matching category, or None if not found/provided.
    """
    return mapas["categoria"].get(norm_key(nome)) if nome else None


def resolve_projeto(mapas: dict, codigo) -> int | None:
    """Resolves the database ID of a project by its contract number or external ID.

    Matches codes like `NNN.YYYY` against the pre-loaded project map. Returning None is
    acceptable and indicates the transaction is a general operational cost or internal transfer
    not linked to a specific project.

    Args:
        mapas (dict): The dictionary of pre-loaded lookup maps.
        codigo (str or None): The contract number or project external ID to resolve.

    Returns:
        int | None: The database ID of the matching project, or None if no match is found.
    """
    return mapas["projeto"].get(str(codigo).strip()) if codigo else None

