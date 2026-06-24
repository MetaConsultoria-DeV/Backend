"""Module for loading Pipefy Financeiro data into the MySQL database.

Implements sequential upserts (insert or update) across the schema tables:
1. forma_pagamento (Payment methods)
2. cliente (Clients, resolved via matching algorithm)
3. projeto_externo (External projects linked to Pipefy cards)
4. contrato (Contracts, linked to clients and projects)
5. contrato_pagamento (Installments/payments associated with contracts)
"""

import logging
from typing import Optional
from database import execute_query, execute_insert
from .matching import resolve_cliente

# Logger instance for the load module
logger = logging.getLogger("ingestion.pipefy.load")


def upsert_forma_pagamento(nome: str) -> int:
    """Inserts a payment method or returns its ID if it already exists.

    Enforces uniqueness on the `nome` column.

    Args:
        nome (str): The name of the payment method (e.g. 'Boleto', 'Cartão').

    Returns:
        int: The database ID of the payment method.
    """
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
    """Upserts a client record using a multi-step resolution matching algorithm.

    Resolves client identity before writing to prevent duplicate records:
      1. Tries to match by CPF/CNPJ (if provided).
      2. If unmatched, performs a lookup by normalized name comparison.
    If an existing client is matched, updates their profile filling in blank fields
    (using COALESCE) without overwriting existing data.
    If no match is found, inserts a new client record.

    Args:
        c (dict): Client dictionary containing:
            - nome (str): Canonical name of the client.
            - cpf_cnpj (str | None): Document identifier.
            - email (str | None): Contact email.
            - telefone (str | None): Contact phone number.
            - external_source (str): Source identifier (pipefy_financeiro).
            - external_id (str): External ID (usually Pipefy card ID).
            - nome_normalizado (str): Normalized version of the client name.

    Returns:
        int: The database ID of the client (either resolved or newly created).

    Raises:
        RuntimeError: If a new client row insertion fails.
    """
    # Call matching lookup helper
    existing_id = resolve_cliente(c.get("cpf_cnpj"), c.get("nome_normalizado", ""))
    
    if existing_id:
        # Update existing record, merging new fields where current values are NULL
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

    # If no existing client is found, insert a new record
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
    """Upserts an external project record, unique by `(external_source, external_id)`.

    Args:
        p (dict): Project details:
            - nome (str): Project title.
            - descricao_projeto (str | None): Detailed project description.
            - external_source (str): Source system tag.
            - external_id (str): Unique card or project ID.

    Returns:
        int: The database ID of the external project.

    Raises:
        RuntimeError: If the project cannot be fetched after execution.
    """
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
    """Upserts a contract record, unique by `(external_source, external_id)`.

    Uses COALESCE on update to avoid regression of finance attributes (like parcelas,
    vencimento, etc.) if subsequent synchronization payloads contain partial data.

    Args:
        c (dict): Contract details including:
            - cliente_id (int): Database client ID.
            - projeto_externo_id (int): Database project ID.
            - numero (str): Contract identifier number.
            - valor_total (float): Contract total money value.
            - forma_pagamento_id (int | None): Database payment method ID.
            - quantidade_parcelas (int | None): Number of installments.
            - estimativa_gastos_ppp (float | None): Cost estimation for PPP.
            - fase_atual (str): Current contract state.
            - data_vencimento_base (date | None): Base reference day for billing.
            - data_inicio_pagamento (date | None): Payment schedule start date.
            - finalizado_em (date | None): Completion timestamp.
            - external_source (str): Source system.
            - external_id (str): External ID string.

    Returns:
        tuple[int, bool]: A tuple containing:
            - int: The contract database ID.
            - bool: True if the contract row was newly created, False if it was updated.
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
    # rowcount == 1 means a new record was successfully inserted.
    inserido = (rowcount == 1)
    return row["id"], inserido


def completar_contrato_existente(contrato_id: int, c: dict, cliente_id: Optional[int],
                                 forma_id: Optional[int]) -> None:
    """Updates missing financial fields on an existing contract record.

    Ensures that contracts created manually in the app can be populated with financial details
    extracted from Pipefy, without changing the contract number or project link.
    COALESCE prevents overwriting existing non-null database fields with empty/null card data.

    Args:
        contrato_id (int): Database ID of the target contract.
        c (dict): Transformed contract data containing financial updates.
        cliente_id (int | None): Database ID of the resolved client.
        forma_id (int | None): Database ID of the resolved payment method.
    """
    execute_query(
        """
        UPDATE contrato SET
            cliente_id            = COALESCE(%s, cliente_id),
            valor_total           = COALESCE(%s, valor_total),
            quantidade_parcelas   = COALESCE(%s, quantidade_parcelas),
            forma_pagamento_id    = COALESCE(forma_pagamento_id, %s),
            estimativa_gastos_ppp = COALESCE(%s, estimativa_gastos_ppp),
            fase_atual            = %s,
            data_vencimento_base  = COALESCE(%s, data_vencimento_base),
            data_inicio_pagamento = COALESCE(%s, data_inicio_pagamento),
            finalizado_em         = COALESCE(%s, finalizado_em)
        WHERE id = %s
        """,
        (
            cliente_id, c.get("valor_total"), c.get("quantidade_parcelas"), forma_id,
            c.get("estimativa_gastos_ppp"), c.get("fase_atual"),
            c.get("data_vencimento_base"), c.get("data_inicio_pagamento"),
            c.get("finalizado_em"), contrato_id,
        ),
    )


def upsert_contrato_pagamento(p: dict) -> None:
    """Upserts a contract payment (installment) record, unique by `(external_source, external_id)`.

    Ensures installment updates (such as payment dates or status changes) are written
    without resetting static attributes like payment numbers.

    Args:
        p (dict): Payment details:
            - contrato_id (int): Database contract ID.
            - cliente_id (int): Database client ID.
            - projeto_externo_id (int): Database project ID.
            - forma_pagamento_id (int | None): Database payment method ID.
            - valor (float): Financial value of the installment.
            - data_vencimento (date | None): Due date.
            - data_pagamento (date | None): Payment date.
            - status (str): Installment payment status (e.g. 'pago', 'aberto').
            - numero_parcela (int): Installment number (e.g., 2).
            - total_parcelas (int): Total contract installments (e.g., 10).
            - external_source (str): Source system identifier.
            - external_id (str): Unique identifier for this specific payment.
    """
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

