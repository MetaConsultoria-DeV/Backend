"""matching.py — Resolve cliente_id e projeto_externo_id no banco."""

import logging
from typing import Optional
from database import execute_query

logger = logging.getLogger("ingestion.pipefy.matching")


def resolve_forma_pagamento(nome: str) -> Optional[int]:
    """Retorna id da forma_pagamento pelo nome exato."""
    row = execute_query(
        "SELECT id FROM forma_pagamento WHERE nome = %s LIMIT 1",
        (nome,), fetch_one=True
    )
    if row:
        return row["id"]
    logger.warning("Forma de pagamento não encontrada: '%s'", nome)
    return None


def resolve_cliente(cpf_cnpj: Optional[str], nome_normalizado: str) -> Optional[int]:
    """
    1º) Casa por cpf_cnpj (se preenchido).
    2º) Fallback: casa por nome normalizado (lower, sem acento, sem espaço duplo).
    Retorna o id do cliente existente, ou None se não encontrado.
    """
    if cpf_cnpj:
        row = execute_query(
            "SELECT id FROM cliente WHERE cpf_cnpj = %s LIMIT 1",
            (cpf_cnpj,), fetch_one=True
        )
        if row:
            return row["id"]

    if nome_normalizado:
        # Normalização no banco: LOWER + remover acentos não é nativo no MySQL sem
        # collation específica — usamos LOWER(nome) e comparamos com a versão normalizada.
        # Para robustez, trazemos todos os nomes e comparamos em Python.
        rows = execute_query(
            "SELECT id, nome FROM cliente",
            fetch_all=True
        ) or []
        for r in rows:
            import unicodedata, re
            nfkd = unicodedata.normalize("NFKD", r["nome"])
            norm = re.sub(r"\s+", " ", nfkd.encode("ascii", "ignore").decode("ascii").lower()).strip()
            if norm == nome_normalizado:
                return r["id"]

    return None


def resolve_contrato_por_numero(numero: str) -> Optional[dict]:
    """Procura um contrato existente pelo número (chave de negócio, UNIQUE).

    Retorna {'id', 'projeto_externo_id', 'cliente_id'} se já existe, senão None.
    Usado para o bot NÃO duplicar projeto/contrato quando o número já está no banco
    (curado à mão ou criado pelo app). 'numero' é globalmente único, então não
    filtra por source.
    """
    if not numero:
        return None
    return execute_query(
        "SELECT id, projeto_externo_id, cliente_id FROM contrato WHERE numero = %s LIMIT 1",
        (numero,), fetch_one=True
    )


def resolve_projeto_externo(codigo: str) -> Optional[int]:
    """
    Busca projeto_externo pelo external_id = código extraído do título.
    external_source = 'pipefy_financeiro'.
    """
    if not codigo:
        return None
    row = execute_query(
        "SELECT id FROM projeto_externo WHERE external_source = %s AND external_id = %s LIMIT 1",
        ("pipefy_financeiro", codigo), fetch_one=True
    )
    return row["id"] if row else None
