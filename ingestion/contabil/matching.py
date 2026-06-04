"""matching.py — Lookups no banco para resolver os FKs da `transacao`.

`conta_bancaria` e `celula` já estão populadas (referência); `projeto_externo` vem do
Pipefy. Aqui só LEMOS. Os mapas são carregados uma vez por sync (chaveados por
`norm_key`) para não bater no banco por linha.
"""

import logging

from database import execute_query
from .normalize import norm_key

logger = logging.getLogger("ingestion.contabil.matching")


def carregar_mapas() -> dict:
    """Carrega de uma vez os lookups usados na carga. Chaves normalizadas (norm_key)."""
    contas = execute_query("SELECT id, nome FROM conta_bancaria", fetch_all=True) or []
    celulas = execute_query("SELECT id, nome FROM celula", fetch_all=True) or []
    categorias = execute_query("SELECT id, nome FROM categoria_transacao", fetch_all=True) or []
    projetos = execute_query(
        "SELECT id, external_id FROM projeto_externo WHERE external_id IS NOT NULL",
        fetch_all=True,
    ) or []

    return {
        "conta": {norm_key(r["nome"]): r["id"] for r in contas},
        "celula": {norm_key(r["nome"]): r["id"] for r in celulas},
        "categoria": {norm_key(r["nome"]): r["id"] for r in categorias},
        "projeto": {str(r["external_id"]).strip(): r["id"] for r in projetos},
    }


def resolve_conta(mapas: dict, nome) -> int | None:
    return mapas["conta"].get(norm_key(nome)) if nome else None


def resolve_celula(mapas: dict, nome) -> int | None:
    return mapas["celula"].get(norm_key(nome)) if nome else None


def resolve_categoria(mapas: dict, nome) -> int | None:
    return mapas["categoria"].get(norm_key(nome)) if nome else None


def resolve_projeto(mapas: dict, codigo) -> int | None:
    """Casa pelo código NNN.YYYY em projeto_externo.external_id. Sem match -> None
    (não é erro: é gasto/ganho extra ou movimento interno). Nunca cria projeto."""
    return mapas["projeto"].get(str(codigo).strip()) if codigo else None
