"""load.py — Upserts ON DUPLICATE KEY: categoria_transacao -> transacao."""

import logging

from database import execute_query

logger = logging.getLogger("ingestion.contabil.load")


def upsert_categoria(nome: str, tipo: str, celula_id: int | None) -> tuple[int, bool]:
    """Upsert por `nome` (uk_categoria_transacao_nome). Retorna (id, criada).

    `criada=True` quando a linha foi inserida agora (rowcount==1), False se já existia.
    Não sobrescreve tipo/celula curados à mão: só preenche se estiver vazio (COALESCE).
    """
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
    row = execute_query(
        "SELECT id FROM categoria_transacao WHERE nome = %s LIMIT 1",
        (nome,), fetch_one=True,
    )
    if not row:
        raise RuntimeError(f"Falha ao upsert categoria_transacao: {nome}")
    return row["id"], (rowcount == 1)


def upsert_transacao(t: dict) -> bool:
    """Upsert por (external_source, external_id). Retorna inserido (True=novo).

    rowcount do MySQL: 1=insert, 2=update. `contrato_pagamento_id` fica sempre NULL
    nesta automação (é o cross-link do sync do Pipefy).

    `projeto_externo_id` nunca regride: se o resolve desta rodada vier NULL (projeto
    ainda não importado, external_id trocado etc.), o vínculo já gravado é mantido.
    """
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
