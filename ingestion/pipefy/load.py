"""load.py — Upserts ON DUPLICATE KEY nas 5 tabelas, na ordem das FKs."""

import logging
from typing import Optional
from database import execute_query, execute_insert
from .matching import resolve_cliente

logger = logging.getLogger("ingestion.pipefy.load")


def upsert_forma_pagamento(nome: str) -> int:
    """Garante que a forma_pagamento existe e retorna o id."""
    execute_query(
        """
        INSERT INTO forma_pagamento (nome)
        VALUES (%s)
        ON DUPLICATE KEY UPDATE nome = VALUES(nome)
        """,
        (nome,),
    )
    row = execute_query(
        "SELECT id FROM forma_pagamento WHERE nome = %s LIMIT 1",
        (nome,), fetch_one=True
    )
    return row["id"]


def upsert_cliente(c: dict) -> int:
    """
    Resolve o cliente ANTES de gravar, honrando a decisão fechada (matching por nome
    agora, convergindo pra CPF/CNPJ):
      1) tenta casar por cpf_cnpj (se preenchido);
      2) senão, casa por nome normalizado (todos os nomes comparados em Python).
    Se achou, atualiza a linha existente (preenche lacunas sem clobber) e devolve o id.
    Se não achou, insere uma linha nova chaveada por (external_source, external_id).

    Assim um mesmo cliente que aparece em vários cards NÃO vira N linhas.
    """
    existing_id = resolve_cliente(c.get("cpf_cnpj"), c.get("nome_normalizado", ""))
    if existing_id:
        execute_query(
            """
            UPDATE cliente SET
              nome            = %s,
              cpf_cnpj        = COALESCE(cpf_cnpj, %s),
              email           = COALESCE(%s, email),
              telefone        = COALESCE(%s, telefone),
              external_source = COALESCE(external_source, %s),
              external_id     = COALESCE(external_id, %s)
            WHERE id = %s
            """,
            (c["nome"], c.get("cpf_cnpj"), c.get("email"), c.get("telefone"),
             c["external_source"], c["external_id"], existing_id),
        )
        return existing_id

    new_id = execute_insert(
        """
        INSERT INTO cliente (nome, cpf_cnpj, email, telefone, external_source, external_id)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (c["nome"], c.get("cpf_cnpj"), c.get("email"), c.get("telefone"),
         c["external_source"], c["external_id"]),
    )
    if not new_id:
        raise RuntimeError(f"Falha ao inserir cliente: {c['nome']}")
    return new_id


def upsert_projeto_externo(p: dict) -> int:
    """Upsert por (external_source, external_id). Retorna o id."""
    execute_query(
        """
        INSERT INTO projeto_externo (nome, descricao_projeto, external_source, external_id)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
          nome              = VALUES(nome),
          descricao_projeto = COALESCE(VALUES(descricao_projeto), descricao_projeto)
        """,
        (p["nome"], p.get("descricao_projeto"),
         p["external_source"], p["external_id"]),
    )
    row = execute_query(
        "SELECT id FROM projeto_externo WHERE external_source = %s AND external_id = %s LIMIT 1",
        (p["external_source"], p["external_id"]), fetch_one=True
    )
    if not row:
        raise RuntimeError(f"Falha ao upsert projeto_externo: {p['nome']}")
    return row["id"]


def upsert_contrato(c: dict) -> tuple[int, bool]:
    """Upsert por (external_source, external_id).

    Retorna (id, inserido) — `inserido=True` quando a linha foi criada agora,
    `False` quando já existia e foi atualizada. (rowcount do MySQL: 1=insert, 2=update.)
    """
    rowcount = execute_query(
        """
        INSERT INTO contrato (
            cliente_id, projeto_externo_id, numero, valor_total,
            forma_pagamento_id, quantidade_parcelas, estimativa_gastos_ppp,
            fase_atual, data_vencimento_base, data_inicio_pagamento, finalizado_em,
            external_source, external_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            cliente_id           = VALUES(cliente_id),
            projeto_externo_id   = VALUES(projeto_externo_id),
            valor_total          = VALUES(valor_total),
            forma_pagamento_id   = COALESCE(VALUES(forma_pagamento_id), forma_pagamento_id),
            quantidade_parcelas  = COALESCE(VALUES(quantidade_parcelas), quantidade_parcelas),
            estimativa_gastos_ppp= COALESCE(VALUES(estimativa_gastos_ppp), estimativa_gastos_ppp),
            fase_atual           = VALUES(fase_atual),
            data_vencimento_base = COALESCE(VALUES(data_vencimento_base), data_vencimento_base),
            data_inicio_pagamento= COALESCE(VALUES(data_inicio_pagamento), data_inicio_pagamento),
            finalizado_em        = COALESCE(VALUES(finalizado_em), finalizado_em)
        """,
        (
            c["cliente_id"], c["projeto_externo_id"], c["numero"], c["valor_total"],
            c.get("forma_pagamento_id"), c.get("quantidade_parcelas"), c.get("estimativa_gastos_ppp"),
            c.get("fase_atual"), c.get("data_vencimento_base"),
            c.get("data_inicio_pagamento"), c.get("finalizado_em"),
            c["external_source"], c["external_id"],
        ),
    )
    row = execute_query(
        "SELECT id FROM contrato WHERE external_source = %s AND external_id = %s LIMIT 1",
        (c["external_source"], c["external_id"]), fetch_one=True
    )
    if not row:
        raise RuntimeError(f"Falha ao upsert contrato: {c['external_id']}")
    inserido = (rowcount == 1)
    return row["id"], inserido


def upsert_contrato_pagamento(p: dict) -> None:
    """Upsert por (external_source, external_id)."""
    execute_query(
        """
        INSERT INTO contrato_pagamento (
            contrato_id, cliente_id, projeto_externo_id, forma_pagamento_id,
            valor, data_vencimento, data_pagamento, status,
            numero_parcela, total_parcelas,
            external_source, external_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            valor           = VALUES(valor),
            data_vencimento = COALESCE(VALUES(data_vencimento), data_vencimento),
            data_pagamento  = COALESCE(VALUES(data_pagamento), data_pagamento),
            status          = VALUES(status)
        """,
        (
            p["contrato_id"], p["cliente_id"], p["projeto_externo_id"], p["forma_pagamento_id"],
            p["valor"], p.get("data_vencimento"), p.get("data_pagamento"), p["status"],
            p["numero_parcela"], p["total_parcelas"],
            p["external_source"], p["external_id"],
        ),
    )
