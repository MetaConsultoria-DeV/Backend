"""
bdu.py — Endpoints read-only que alimentam o frontend BDU (Next.js).

Aditivo: não altera nenhuma rota existente nem o schema MySQL.
Apenas SELECTs parametrizados (LEFT JOIN + COALESCE) que degradam para
listas/zeros quando as tabelas estão vazias.

Padrões herdados de main.py: async + asyncio.to_thread(execute_query, ...).
Prefixo: /api/bdu
"""

import asyncio
from fastapi import APIRouter, Query

from database import execute_query

router = APIRouter(prefix="/api/bdu", tags=["bdu"])


async def _q(query: str, params=None):
    """Atalho: roda execute_query(fetch_all=True) numa thread e nunca devolve None."""
    rows = await asyncio.to_thread(execute_query, query, params, False, True)
    return rows or []


def _f(value) -> float:
    """Converte Decimal/None para float seguro (JSON)."""
    return float(value) if value is not None else 0.0


# ============================================================
# VISÃO GERAL (home) — TASK-023
# ============================================================
@router.get("/overview")
async def get_overview(
    data_inicio: str | None = Query(default=None),
    data_fim: str | None = Query(default=None),
):
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
    """Diretório: membro + cargos + célula + coordenações (agregados)."""
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
    clausula, params = _periodo(data_inicio, data_fim)
    return await _q(
        f"""
        SELECT o.id, o.fase_atual_nome AS fase, o.valor_fechado AS valor,
               o.status_terminal, o.criado_em, o.responsaveis,
               cli.nome AS cliente, co.nome AS coordenacao, co.sigla AS coordenacao_sigla,
               COALESCE(org.canonical_value, org.raw_value) AS origem,
               COALESCE(mp.canonical_value, mp.raw_value) AS motivo_perda
        FROM oportunidade o
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
async def get_origens():
    return await _q(
        """
        SELECT COALESCE(org.canonical_value, org.raw_value) AS nome, COUNT(*) AS qtd
        FROM oportunidade o
        JOIN dim_lead_origem org ON org.id = o.origem_id
        GROUP BY nome ORDER BY qtd DESC
        """
    )


@router.get("/comercial/motivos-perda")
async def get_motivos_perda():
    return await _q(
        """
        SELECT COALESCE(mp.canonical_value, mp.raw_value) AS nome, COUNT(*) AS qtd
        FROM oportunidade o
        JOIN dim_motivo_perda mp ON mp.id = o.motivo_perda_id
        WHERE o.status_terminal IN ('recusado', 'desistido')
        GROUP BY nome ORDER BY qtd DESC
        """
    )


@router.get("/comercial/clientes")
async def get_clientes_comercial():
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
async def get_contratos():
    return await _q(
        """
        SELECT c.id, c.numero, c.valor_total, c.quantidade_parcelas, c.fase_atual,
               cli.nome AS cliente, pe.nome AS projeto,
               (SELECT COUNT(*) FROM contrato_pagamento cp
                 WHERE cp.contrato_id = c.id AND cp.status = 'pago') AS parcelas_pagas,
               (SELECT COUNT(*) FROM contrato_pagamento cp WHERE cp.contrato_id = c.id) AS parcelas_total
        FROM contrato c
        LEFT JOIN cliente cli ON cli.id = c.cliente_id
        LEFT JOIN projeto_externo pe ON pe.id = c.projeto_externo_id
        ORDER BY c.valor_total DESC
        """
    )


@router.get("/financeiro/transacoes")
async def get_transacoes(
    tipo: str | None = Query(default=None),
    data_inicio: str | None = Query(default=None),
    data_fim: str | None = Query(default=None),
):
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
    """Entradas vs. saídas agregadas por mês (YYYY-MM)."""
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
async def get_servicos_portfolio():
    # ATENCAO: `oportunidades` e contado por COORDENACAO (nao ha vinculo servico->oportunidade
    # no banco), entao todo servico da mesma coordenacao repete o mesmo numero. NAO some este
    # campo por servico no frontend: agregue por coordenacao. `projetos` vem de projeto_servico,
    # que esta vazia -> 0 para todos enquanto a tabela nao for populada.
    return await _q(
        """
        SELECT s.id, s.nome, s.sigla,
               co.id AS coordenacao_id, co.nome AS coordenacao, co.sigla AS coordenacao_sigla,
               (SELECT COUNT(*) FROM projeto_servico ps WHERE ps.servico_id = s.id) AS projetos,
               (SELECT COUNT(*) FROM oportunidade o WHERE o.coordenacao_id = s.coordenacao_id) AS oportunidades
        FROM servico s
        JOIN coordenacao co ON co.id = s.coordenacao_id
        ORDER BY co.nome, s.nome
        """
    )


# ============================================================
# ANÁLISES TRANSVERSAIS — TASK-029
# ============================================================
@router.get("/transversais/facts")
async def get_transversais_facts():
    """
    "Fatos" projeto × membro × cargo × coordenação × célula × cliente × valor.
    O frontend agrega livremente (A × B × métrica), evitando lógica pesada no backend.

    Dimensões escolhidas pelo que está populado no banco (contexto-banco-agent):
    - `projeto_servico` está vazia → serviço não é dimensão viável.
    - As 5 coordenações pertencem à mesma célula → célula vem do membro
      (membro_celula), não da coordenação.
    - `membro_projeto.cargo_id` e `coordenacao_id` estão 100% preenchidos.
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
