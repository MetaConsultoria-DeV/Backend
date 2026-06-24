"""bdu.py — Endpoints read-only que alimentam o frontend BDU (Next.js).

Aditivo: não altera nenhuma rota existente nem o schema MySQL.
Apenas SELECTs parametrizados (LEFT JOIN + COALESCE) que degradam para
listas/zeros quando as tabelas estão vazias.

Padrões herdados de main.py: async + asyncio.to_thread(execute_query, ...).
Prefixo: /api/bdu
"""

import asyncio
import os
import secrets
from fastapi import APIRouter, Query, Header, HTTPException, Depends

from database import execute_query


def require_bdu_token(authorization: str | None = Header(default=None)) -> None:
    """Dependency to enforce read token authorization for BDU endpoints.

    - Sem `BDU_READ_TOKEN` no ambiente -> libera (comportamento atual; nada muda).
    - Com a env definida -> exige `Authorization: Bearer <token>`, comparado em
      tempo constante. O frontend (Next.js, server-side) envia o mesmo token.

    Para ATIVAR a proteção sem janela de queda: defina BDU_READ_TOKEN primeiro no
    frontend (reinicie), depois no backend (reinicie). Mesmo valor nos dois lados.

    Args:
        authorization (str | None): The Authorization header value. Defaults to Header(default=None).

    Raises:
        HTTPException: 401 Unauthorized if the token is missing or incorrect.
    """
    expected = os.getenv("BDU_READ_TOKEN", "")
    if not expected:
        return  # fail-open: a proteção só liga quando a env existir nos dois lados
    prefix = "Bearer "
    provided = authorization[len(prefix):] if authorization and authorization.startswith(prefix) else ""
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Não autorizado")


router = APIRouter(
    prefix="/api/bdu",
    tags=["bdu"],
    dependencies=[Depends(require_bdu_token)],
)


async def _q(query: str, params=None):
    """Atalho: roda execute_query(fetch_all=True) numa thread e nunca devolve None.

    Args:
        query (str): The SQL query string.
        params (tuple, optional): Parameters to bind to the SQL query. Defaults to None.

    Returns:
        list[dict]: A list of dictionary rows, or an empty list if no results or None returned.
    """
    rows = await asyncio.to_thread(execute_query, query, params, False, True)
    return rows or []


def _f(value) -> float:
    """Converte Decimal/None para float seguro (JSON).

    Args:
        value (Any): The value to convert.

    Returns:
        float: The converted value, or 0.0 if the value is None.
    """
    return float(value) if value is not None else 0.0


# ============================================================
# VISÃO GERAL (home) — TASK-023
# ============================================================
@router.get("/overview")
async def get_overview(
    data_inicio: str | None = Query(default=None),
    data_fim: str | None = Query(default=None),
):
    """GET /api/bdu/overview

    Returns a high-level summary of total entity counts (members, projects, contracts,
    coordinations, etc.), and financial summaries (total incoming, outgoing, result,
    and average ticket value).

    Args:
        data_inicio (str | None): Filter start date in YYYY-MM-DD format (applies only to transactions).
        data_fim (str | None): Filter end date in YYYY-MM-DD format (applies only to transactions).

    Returns:
        dict: High-level KPI indicators. E.g.:
            {
                "membros": int,
                "projetos": int,
                "contratos": int,
                "coordenacoes": int,
                "celulas": int,
                "servicos": int,
                "clientes": int,
                "oportunidades_abertas": int,
                "receita_contratada": float,
                "total_entradas": float,
                "total_saidas": float,
                "resultado": float,
                "ticket_medio": float
            }
    """
    counts_q = """
    SELECT
      (SELECT COUNT(*) FROM membro) AS membros,
      (SELECT COUNT(*) FROM projeto_externo) AS projetos,
      (SELECT COUNT(*) FROM contrato) AS contratos,
      (SELECT COUNT(*) FROM coordenacao) AS coordenacoes,
      (SELECT COUNT(*) FROM celula) AS celulas,
      (SELECT COUNT(*) FROM servico) AS servicos,
      (SELECT COUNT(*) FROM cliente) AS clientes,
      (SELECT COUNT(*) FROM oportunidade WHERE status_terminal = 'ativo') AS oportunidades_abertas
    """
    counts = await asyncio.to_thread(execute_query, counts_q, None, True, False)

    receita = await asyncio.to_thread(
        execute_query, "SELECT COALESCE(SUM(valor_total), 0) AS total FROM contrato", None, True, False
    )
    # Recorte temporal só vale para o caixa (transacao.data); contagens e receita
    # contratada não têm data confiável no banco (datas de contrato 100% nulas).
    clausula, params = _periodo(data_inicio, data_fim, coluna="data")
    fluxo = await _q(
        f"SELECT tipo, COALESCE(SUM(valor), 0) AS total FROM transacao WHERE 1=1 {clausula} GROUP BY tipo",
        tuple(params) or None,
    )
    entradas = next((_f(r["total"]) for r in fluxo if r["tipo"] == "entrada"), 0.0)
    saidas = next((_f(r["total"]) for r in fluxo if r["tipo"] == "saida"), 0.0)
    receita_contratada = _f(counts and receita and receita["total"])

    counts = counts or {}
    contrato_count = counts.get("contratos", 0) or 0
    return {
        "membros": counts.get("membros", 0),
        "projetos": counts.get("projetos", 0),
        "contratos": contrato_count,
        "coordenacoes": counts.get("coordenacoes", 0),
        "celulas": counts.get("celulas", 0),
        "servicos": counts.get("servicos", 0),
        "clientes": counts.get("clientes", 0),
        "oportunidades_abertas": counts.get("oportunidades_abertas", 0),
        "receita_contratada": receita_contratada,
        "total_entradas": entradas,
        "total_saidas": saidas,
        "resultado": entradas - saidas,
        "ticket_medio": round(receita_contratada / contrato_count, 2) if contrato_count else 0.0,
    }


# ============================================================
# ESTRUTURA & PESSOAS (mapa) — TASK-024
# ============================================================
@router.get("/estrutura/celulas")
async def get_celulas():
    """GET /api/bdu/estrutura/celulas

    Retrieves a list of cells along with the count of active members within each cell.

    Returns:
        list[dict]: List of cells:
            - id (int): Cell ID.
            - nome (str): Cell name.
            - sigla (str): Cell abbreviation.
            - membros (int): Count of members in the cell.
    """
    return await _q(
        """
        SELECT c.id, c.nome, c.sigla,
               (SELECT COUNT(*) FROM membro_celula mc WHERE mc.celula_id = c.id) AS membros
        FROM celula c
        ORDER BY c.nome
        """
    )


@router.get("/estrutura/pessoas")
async def get_pessoas():
    """GET /api/bdu/estrutura/pessoas

    Retrieves a member directory containing names, emails, roles, cells, and department
    coordinations associated with each member.

    Returns:
        list[dict]: Directory listing of active members with aggregated:
            - id (int): Member ID.
            - nome (str): Full name.
            - email (str): Email address.
            - cargos (str): Comma-separated list of roles.
            - celula (str): Main cell name.
            - coordenacoes (str): Comma-separated department abbreviations.
    """
    return await _q(
        """
        SELECT
          m.id, m.nome, m.email,
          (SELECT GROUP_CONCAT(DISTINCT cg.nome ORDER BY cg.nome SEPARATOR ', ')
             FROM membro_cargo mc JOIN cargo cg ON cg.id = mc.cargo_id
            WHERE mc.membro_id = m.id) AS cargos,
          (SELECT cel.nome FROM membro_celula mcel
             JOIN celula cel ON cel.id = mcel.celula_id
            WHERE mcel.membro_id = m.id LIMIT 1) AS celula,
          (SELECT GROUP_CONCAT(DISTINCT co.sigla ORDER BY co.sigla SEPARATOR ', ')
             FROM membro_coordenacao mco JOIN coordenacao co ON co.id = mco.coordenacao_id
            WHERE mco.membro_id = m.id) AS coordenacoes
        FROM membro m
        ORDER BY m.nome
        """
    )


# ============================================================
# COMERCIAL — TASK-026 (filtros temporais em criado_em)
# ============================================================
def _periodo(data_inicio, data_fim, coluna="o.criado_em"):
    """Generates a parameterized SQL WHERE clause and parameter list for date filtering.

    Args:
        data_inicio (str | None): Start date in YYYY-MM-DD format.
        data_fim (str | None): End date in YYYY-MM-DD format.
        coluna (str, optional): The SQL column name to filter on. Defaults to "o.criado_em".

    Returns:
        tuple[str, list]: A tuple containing the SQL snippet (e.g. ' AND o.criado_em >= %s')
            and the corresponding list of date values.
    """
    clausula, params = "", []
    if data_inicio:
        clausula += f" AND {coluna} >= %s"
        params.append(data_inicio)
    if data_fim:
        clausula += f" AND {coluna} <= %s"
        params.append(data_fim)
    return clausula, params


@router.get("/comercial/funil")
async def get_funil(
    data_inicio: str | None = Query(default=None),
    data_fim: str | None = Query(default=None),
):
    """GET /api/bdu/comercial/funil

    Calculates sales funnel step counts and values grouped by opportunity status.

    Args:
        data_inicio (str | None): Start date for opportunity creation (YYYY-MM-DD).
        data_fim (str | None): End date for opportunity creation (YYYY-MM-DD).

    Returns:
        list[dict]: Opportunities grouped by funnel stage:
            - fase (str): Stage name.
            - qtd (int): Quantity of opportunities in this stage.
            - valor (float): Sum of values in this stage.
    """
    clausula, params = _periodo(data_inicio, data_fim)
    return await _q(
        f"""
        SELECT o.fase_atual_nome AS fase,
               COUNT(*) AS qtd,
               COALESCE(SUM(o.valor_fechado), 0) AS valor
        FROM oportunidade o
        WHERE 1=1 {clausula}
        GROUP BY o.fase_atual_nome
        ORDER BY qtd DESC
        """,
        tuple(params) or None,
    )


@router.get("/comercial/oportunidades")
async def get_oportunidades(
    data_inicio: str | None = Query(default=None),
    data_fim: str | None = Query(default=None),
):
    """GET /api/bdu/comercial/oportunidades

    Lists opportunities with their current funnel stage, customer, values, and origin.

    Args:
        data_inicio (str | None): Start date for opportunity creation (YYYY-MM-DD).
        data_fim (str | None): End date for opportunity creation (YYYY-MM-DD).

    Returns:
        list[dict]: Detailed opportunities list:
            - id (int): Opportunity ID.
            - fase (str): Funnel stage.
            - valor (float): Deal value.
            - status_terminal (str): Final status (active, won, lost).
            - criado_em (str): Creation date.
            - responsaveis (str): Names of team members responsible.
            - lead (str): Name of the lead source.
            - cliente (str): Client name.
            - coordenacao (str): Coordination name.
            - coordenacao_sigla (str): Coordination abbreviation.
            - origem (str): Canonical lead source.
            - motivo_perda (str): Reason for deal loss, if lost.
    """
    clausula, params = _periodo(data_inicio, data_fim)
    return await _q(
        f"""
        SELECT o.id, o.fase_atual_nome AS fase, o.valor_fechado AS valor,
               o.status_terminal, o.criado_em, o.responsaveis,
               l.nome AS `lead`, cli.nome AS cliente, co.nome AS coordenacao, co.sigla AS coordenacao_sigla,
               COALESCE(org.canonical_value, org.raw_value) AS origem,
               COALESCE(mp.canonical_value, mp.raw_value) AS motivo_perda
        FROM oportunidade o
        LEFT JOIN leads l ON l.id = o.lead_id
        LEFT JOIN cliente cli ON cli.id = o.cliente_id
        LEFT JOIN coordenacao co ON co.id = o.coordenacao_id
        LEFT JOIN dim_lead_origem org ON org.id = o.origem_id
        LEFT JOIN dim_motivo_perda mp ON mp.id = o.motivo_perda_id
        WHERE 1=1 {clausula}
        ORDER BY o.criado_em DESC
        """,
        tuple(params) or None,
    )


@router.get("/comercial/origens")
async def get_origens(
    data_inicio: str | None = Query(default=None),
    data_fim: str | None = Query(default=None),
):
    """GET /api/bdu/comercial/origens

    Retrieves counts of commercial opportunities grouped by lead origin channel.

    Args:
        data_inicio (str | None): Start date for opportunity creation (YYYY-MM-DD).
        data_fim (str | None): End date for opportunity creation (YYYY-MM-DD).

    Returns:
        list[dict]: Lead origins:
            - nome (str): Canonical or raw origin name.
            - qtd (int): Count of opportunities.
    """
    # Recorte por criado_em (quando a demanda entrou).
    clausula, params = _periodo(data_inicio, data_fim)  # coluna padrao = o.criado_em
    return await _q(
        f"""
        SELECT COALESCE(org.canonical_value, org.raw_value) AS nome, COUNT(*) AS qtd
        FROM oportunidade o
        JOIN dim_lead_origem org ON org.id = o.origem_id
        WHERE 1=1 {clausula}
        GROUP BY nome ORDER BY qtd DESC
        """,
        tuple(params) or None,
    )


@router.get("/comercial/motivos-perda")
async def get_motivos_perda(
    data_inicio: str | None = Query(default=None),
    data_fim: str | None = Query(default=None),
):
    """GET /api/bdu/comercial/motivos-perda

    Retrieves counts of lost/refused opportunities grouped by reason for loss.

    Args:
        data_inicio (str | None): Start date in YYYY-MM-DD format.
        data_fim (str | None): End date in YYYY-MM-DD format.

    Returns:
        list[dict]: Reasons for loss:
            - nome (str): Reason description.
            - qtd (int): Count of lost opportunities.
    """
    # Recorte por quando a perda aconteceu (finalizado_em), com fallback para
    # criado_em quando finalizado_em estiver nulo (nao derruba linhas).
    clausula, params = _periodo(
        data_inicio, data_fim, coluna="COALESCE(o.finalizado_em, o.criado_em)"
    )
    return await _q(
        f"""
        SELECT COALESCE(mp.canonical_value, mp.raw_value) AS nome, COUNT(*) AS qtd
        FROM oportunidade o
        JOIN dim_motivo_perda mp ON mp.id = o.motivo_perda_id
        WHERE o.status_terminal IN ('recusado', 'desistido') {clausula}
        GROUP BY nome ORDER BY qtd DESC
        """,
        tuple(params) or None,
    )


@router.get("/comercial/clientes")
async def get_clientes_comercial():
    """GET /api/bdu/comercial/clientes

    Retrieves a list of clients detailing their opportunities, contracts count,
    and total contract revenue.

    Returns:
        list[dict]: Client stats sorted by revenue descending:
            - id (int): Client ID.
            - nome (str): Client name.
            - oportunidades (int): Total opportunities count.
            - contratos (int): Total contracts count.
            - receita (float): Sum of contract values.
    """
    return await _q(
        """
        SELECT cli.id, cli.nome,
               (SELECT COUNT(*) FROM oportunidade o WHERE o.cliente_id = cli.id) AS oportunidades,
               (SELECT COUNT(*) FROM contrato c WHERE c.cliente_id = cli.id) AS contratos,
               (SELECT COALESCE(SUM(c.valor_total), 0) FROM contrato c WHERE c.cliente_id = cli.id) AS receita
        FROM cliente cli
        ORDER BY receita DESC
        """
    )


# ============================================================
# FINANCEIRO — TASK-027
# ============================================================
@router.get("/financeiro/contratos")
async def get_contratos(
    data_inicio: str | None = Query(default=None),
    data_fim: str | None = Query(default=None),
):
    """GET /api/bdu/financeiro/contratos

    Retrieves contracts detailing their payments progress, current phase, client,
    and associated project.

    Args:
        data_inicio (str | None): Start date in YYYY-MM-DD format (filters active contracts).
        data_fim (str | None): End date in YYYY-MM-DD format (filters active contracts).

    Returns:
        list[dict]: Contracts ordered by total value descending:
            - id (int): Contract ID.
            - numero (str): Contract number.
            - valor_total (float): Contract value.
            - quantidade_parcelas (int): Total payment installments.
            - fase_atual (str): Contract phase.
            - cliente (str): Client name.
            - projeto (str): Associated project name.
            - parcelas_pagas (int): Paid installments.
            - parcelas_total (int): Total installments in DB.
    """
    clausula, params = "", []
    if data_inicio:
        clausula += " AND (c.data_fim IS NULL OR c.data_fim >= %s)"
        params.append(data_inicio)
    if data_fim:
        clausula += " AND (c.data_inicio IS NULL OR c.data_inicio <= %s)"
        params.append(data_fim)

    return await _q(
        f"""
        SELECT c.id, c.numero, c.valor_total, c.quantidade_parcelas, c.fase_atual,
               cli.nome AS cliente, pe.nome AS projeto,
               (SELECT COUNT(*) FROM contrato_pagamento cp
                 WHERE cp.contrato_id = c.id AND cp.status = 'pago') AS parcelas_pagas,
               (SELECT COUNT(*) FROM contrato_pagamento cp WHERE cp.contrato_id = c.id) AS parcelas_total
        FROM contrato c
        LEFT JOIN cliente cli ON cli.id = c.cliente_id
        LEFT JOIN projeto_externo pe ON pe.id = c.projeto_externo_id
        WHERE 1=1 {clausula}
        ORDER BY c.valor_total DESC
        """,
        tuple(params) or None,
    )


@router.get("/financeiro/transacoes")
async def get_transacoes(
    tipo: str | None = Query(default=None),
    data_inicio: str | None = Query(default=None),
    data_fim: str | None = Query(default=None),
):
    """GET /api/bdu/financeiro/transacoes

    Lists transactions, with bank account details, category, and projects.

    Args:
        tipo (str | None): Filter by type ('entrada' or 'saida').
        data_inicio (str | None): Start date in YYYY-MM-DD format.
        data_fim (str | None): End date in YYYY-MM-DD format.

    Returns:
        list[dict]: Transactions list (capped at 500):
            - id (int): Transaction ID.
            - tipo (str): 'entrada' or 'saida'.
            - valor (float): Amount.
            - data (str): Date of transaction.
            - conta (str): Bank account name.
            - categoria (str): Category description.
            - contrato_pagamento_id (int): Installment reference ID.
            - projeto_externo_id (int): Project ID.
            - projeto (str): Project name.
    """
    clausula, params = _periodo(data_inicio, data_fim, coluna="t.data")
    if tipo in ("entrada", "saida"):
        clausula += " AND t.tipo = %s"
        params.append(tipo)
    return await _q(
        f"""
        SELECT t.id, t.tipo, t.valor, t.data,
               cb.nome AS conta, cat.nome AS categoria,
               t.contrato_pagamento_id, t.projeto_externo_id, pe.nome AS projeto
        FROM transacao t
        LEFT JOIN conta_bancaria cb ON cb.id = t.conta_id
        LEFT JOIN categoria_transacao cat ON cat.id = t.categoria_id
        LEFT JOIN projeto_externo pe ON pe.id = t.projeto_externo_id
        WHERE 1=1 {clausula}
        ORDER BY t.data DESC
        LIMIT 500
        """,
        tuple(params) or None,
    )


@router.get("/financeiro/fluxo")
async def get_fluxo(
    data_inicio: str | None = Query(default=None),
    data_fim: str | None = Query(default=None),
):
    """GET /api/bdu/financeiro/fluxo

    Aggregates incoming (entrada) and outgoing (saida) transaction values by month (YYYY-MM).

    Args:
        data_inicio (str | None): Start date in YYYY-MM-DD format.
        data_fim (str | None): End date in YYYY-MM-DD format.

    Returns:
        list[dict]: Aggregated monthly values:
            - mes (str): Month in YYYY-MM format.
            - entrada (float): Sum of inputs.
            - saida (float): Sum of outputs.
    """
    clausula, params = _periodo(data_inicio, data_fim, coluna="t.data")
    return await _q(
        f"""
        SELECT DATE_FORMAT(t.data, '%Y-%m') AS mes,
               COALESCE(SUM(CASE WHEN t.tipo = 'entrada' THEN t.valor END), 0) AS entrada,
               COALESCE(SUM(CASE WHEN t.tipo = 'saida' THEN t.valor END), 0) AS saida
        FROM transacao t
        WHERE 1=1 {clausula}
        GROUP BY mes ORDER BY mes
        """,
        tuple(params) or None,
    )


@router.get("/financeiro/contas")
async def get_contas(
    data_inicio: str | None = Query(default=None),
    data_fim: str | None = Query(default=None),
):
    """GET /api/bdu/financeiro/contas

    Retrieves active bank accounts with calculated balance based on transaction type.

    Args:
        data_inicio (str | None): Start date for transactions (YYYY-MM-DD).
        data_fim (str | None): End date for transactions (YYYY-MM-DD).

    Returns:
        list[dict]: Bank accounts and balance:
            - conta (str): Account name.
            - saldo (float): Net balance (inputs - outputs) for the period.
    """
    # Filtro vai no ON (não no WHERE) para manter contas sem movimento no período.
    clausula, params = _periodo(data_inicio, data_fim, coluna="t.data")
    return await _q(
        f"""
        SELECT cb.nome AS conta,
               COALESCE(SUM(CASE WHEN t.tipo = 'entrada' THEN t.valor
                                 WHEN t.tipo = 'saida' THEN -t.valor END), 0) AS saldo
        FROM conta_bancaria cb
        LEFT JOIN transacao t ON t.conta_id = cb.id {clausula}
        WHERE cb.ativo = 1
        GROUP BY cb.id, cb.nome
        ORDER BY cb.nome
        """,
        tuple(params) or None,
    )


# ============================================================
# SERVIÇOS & PORTFÓLIO — TASK-028
# ============================================================
@router.get("/servicos/portfolio")
async def get_servicos_portfolio(
    data_inicio: str | None = Query(default=None),
    data_fim: str | None = Query(default=None),
):
    """GET /api/bdu/servicos/portfolio

    Lists services in the catalog along with metrics for opportunities and associated projects.

    Args:
        data_inicio (str | None): Start date for filtering opportunities (YYYY-MM-DD).
        data_fim (str | None): End date for filtering opportunities (YYYY-MM-DD).

    Returns:
        list[dict]: Catalog of services:
            - id (int): Service ID.
            - nome (str): Service name.
            - sigla (str): Service abbreviation.
            - coordenacao_id (int): Department ID.
            - coordenacao (str): Department name.
            - coordenacao_sigla (str): Department abbreviation.
            - projetos (int): Count of associated projects in `projeto_servico`.
            - oportunidades (int): Opportunities count associated with the parent department.
    """
    # ATENCAO: `oportunidades` e contado por COORDENACAO (nao ha vinculo servico->oportunidade
    # no banco), entao todo servico da mesma coordenacao repete o mesmo numero. NAO some este
    # campo por servico no frontend: agregue por coordenacao. `projetos` vem de projeto_servico,
    # que esta vazia -> 0 para todos enquanto a tabela nao for populada.
    # O recorte temporal (data_inicio/data_fim) filtra a DEMANDA por o.criado_em; o catalogo
    # de servicos (s.*) e atemporal e nao muda com o periodo.
    clausula, params = _periodo(data_inicio, data_fim)  # coluna padrao = o.criado_em
    return await _q(
        f"""
        SELECT s.id, s.nome, s.sigla,
               co.id AS coordenacao_id, co.nome AS coordenacao, co.sigla AS coordenacao_sigla,
               (SELECT COUNT(*) FROM projeto_servico ps WHERE ps.servico_id = s.id) AS projetos,
               (SELECT COUNT(*) FROM oportunidade o
                 WHERE o.coordenacao_id = s.coordenacao_id {clausula}) AS oportunidades
        FROM servico s
        JOIN coordenacao co ON co.id = s.coordenacao_id
        ORDER BY co.nome, s.nome
        """,
        tuple(params) or None,
    )


# ============================================================
# ANÁLISES TRANSVERSAIS — TASK-029
# ============================================================
@router.get("/transversais/facts")
async def get_transversais_facts():
    """GET /api/bdu/transversais/facts

    Retrieves a flattened matrix of projects, members, roles, coordinations, cells,
    customers, and contract values, allowing the frontend to aggregate freely.

    Returns:
        list[dict]: List of projects facts:
            - projeto_id (int): Project ID.
            - projeto (str): Project name.
            - descricao (str): Project description.
            - status (str): Project status.
            - valor (float): Associated contract value.
            - membro_id (int): Project member ID.
            - membro (str): Member name.
            - coordenacao (str): Coordination department name.
            - coordenacao_sigla (str): Department abbreviation.
            - cargo (str): Member project role.
            - celula (str): Member cell name.
            - cliente (str): Client name.
    """
    return await _q(
        """
        SELECT
          pe.id AS projeto_id, pe.nome AS projeto,
          pe.descricao AS descricao,
          pe.status AS status,
          COALESCE(c.valor_total, 0) AS valor,
          m.id AS membro_id, m.nome AS membro,
          co.nome AS coordenacao, co.sigla AS coordenacao_sigla,
          ca.nome AS cargo,
          cel.nome AS celula,
          cli.nome AS cliente
        FROM projeto_externo pe
        LEFT JOIN membro_projeto mp ON pe.id = mp.projeto_externo_id
        LEFT JOIN membro m ON m.id = mp.membro_id
        LEFT JOIN coordenacao co ON co.id = mp.coordenacao_id
        LEFT JOIN cargo ca ON ca.id = mp.cargo_id
        LEFT JOIN membro_celula mc ON mc.membro_id = m.id
        LEFT JOIN celula cel ON cel.id = mc.celula_id
        LEFT JOIN contrato c ON c.projeto_externo_id = pe.id
        LEFT JOIN cliente cli ON cli.id = c.cliente_id
        ORDER BY pe.nome
        """
    )
