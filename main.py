from fastapi import FastAPI, HTTPException, BackgroundTasks, Header, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import asyncio
import httpx
import json
import secrets
from contextlib import asynccontextmanager
from models import Projeto, Coordenacao, Membro, PapeFormData, ProjetoListItem, Servico, ServicosPorCoordenacao, MembrosPorCoordenacao, ProjetoUpdate, ProjetoCreate
from database import execute_query, execute_insert, transaction, init_pool, close_pool
from ingestion.router import router as ingestion_router
from routers.bdu import router as bdu_router

import os
from dotenv import load_dotenv
import logging

# Garante que carrega o arquivo .env do diretório onde o script está localizado
base_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(base_dir, '.env')
load_dotenv(dotenv_path)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('pape')


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Context manager to handle FastAPI application lifespan events.

    Initializes the MySQL connection pool on startup and closes it on shutdown
    to release all database connections.

    Args:
        app (FastAPI): The FastAPI application instance.
    """
    init_pool()
    yield
    close_pool()


# ENABLE_DOCS=0 desativa /docs, /redoc e /openapi.json em produção
_docs_enabled = os.getenv('ENABLE_DOCS', '1') == '1'
app = FastAPI(
    title='PAPE API',
    version='1.0.0',
    lifespan=lifespan,
    docs_url='/docs' if _docs_enabled else None,
    redoc_url='/redoc' if _docs_enabled else None,
    openapi_url='/openapi.json' if _docs_enabled else None,
)

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000').split(',')
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allow_headers=['Authorization', 'Content-Type'],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Global exception handler to capture and log any unhandled exceptions.

    Logs the exception with stack trace and returns a generic HTTP 500 error
    response to the client.

    Args:
        request (Request): The request that caused the exception.
        exc (Exception): The unhandled exception instance.

    Returns:
        JSONResponse: A standard HTTP 500 JSON response.
    """
    logger.exception('Erro não tratado em %s', request.url.path)
    return JSONResponse(status_code=500, content={'detail': 'Erro interno do servidor'})

# Ingestão Pipefy Financeiro — POST /internal/sync/pipefy-financeiro
app.include_router(ingestion_router)
# Endpoints read-only do BDU (frontend Next.js) — GET /api/bdu/*
app.include_router(bdu_router)

N8N_WEBHOOK_URL = os.getenv('N8N_WEBHOOK_URL', 'http://localhost:5678/webhook/pape')
ADMIN_API_TOKEN = os.getenv('ADMIN_API_TOKEN', '')


def require_admin_token(authorization: str | None = Header(default=None)) -> None:
    """Dependency to validate admin token header authentication.

    Requires an HTTP header containing 'Authorization: Bearer <ADMIN_API_TOKEN>'.
    Used to protect database mutating routes (POST, PUT, DELETE).

    Args:
        authorization (str | None): The Authorization header value. Defaults to Header(default=None).

    Raises:
        HTTPException: 503 Service Unavailable if backend token is not set.
        HTTPException: 401 Unauthorized if token is missing or invalid.
    """
    if not ADMIN_API_TOKEN:
        raise HTTPException(status_code=503, detail='Servidor sem ADMIN_API_TOKEN configurado')
    prefix = 'Bearer '
    provided = authorization[len(prefix):] if authorization and authorization.startswith(prefix) else ''
    if not provided or not secrets.compare_digest(provided, ADMIN_API_TOKEN):
        raise HTTPException(status_code=401, detail='Não autorizado')



@app.get('/api/health')
async def health():
    """GET /api/health

    Basic health check endpoint to verify backend status.

    Returns:
        dict: A dictionary indicating status. E.g. {'status': 'ok'}.
    """
    return {'status': 'ok'}


@app.get('/api/projetos', response_model=list[Projeto])
async def get_projetos(gerente_id: int | None = None):
    """GET /api/projetos

    Retrieves a list of projects with active or non-canceled contracts.
    Can be filtered to only return projects assigned to a specific project manager.

    Args:
        gerente_id (int | None): The database ID of the project manager. Defaults to None.

    Returns:
        list[dict]: A list of projects matching the criteria.
    """
    manager_filter = ''
    params = None
    if gerente_id is not None:
        # Filtra projetos onde o membro é gerente ativo (data_saida IS NULL)
        manager_filter = '''
      AND EXISTS (
        SELECT 1
        FROM membro_projeto mp
        JOIN cargo cg ON cg.id = mp.cargo_id
        WHERE mp.projeto_externo_id = pe.id
          AND mp.membro_id = %s
          AND mp.data_saida IS NULL
          AND LOWER(cg.nome) LIKE '%gerente%'
      )
        '''
        params = (gerente_id,)

    query = '''
    SELECT pe.id, pe.nome, c.numero as numero_contrato, c.valor_total,
           pe.possui_orientador, pe.nome_orientador, pe.status
    FROM projeto_externo pe
    LEFT JOIN contrato c ON c.projeto_externo_id = pe.id
    WHERE (
        c.id IS NULL
        OR (
        c.finalizado_em IS NULL
        AND (c.fase_atual IS NULL OR c.fase_atual NOT IN ('Concluido', 'Cancelado'))
        )
       )
    {manager_filter}
    ORDER BY pe.nome
    '''.format(manager_filter=manager_filter)
    if params:
        resultado = await asyncio.to_thread(execute_query, query, params, fetch_all=True)
    else:
        resultado = await asyncio.to_thread(execute_query, query, fetch_all=True)
    return resultado or []


@app.get('/api/projetos/all', response_model=list[ProjetoListItem])
async def get_all_projetos():
    """GET /api/projetos/all

    Retrieves a list of all projects in the database with their current status
    and project managers. Omit temporary contract numbers (starting with CONTRATO-TEMP).

    Returns:
        list[dict]: A list of project objects.
    """
    query = '''
    SELECT 
        pe.id, 
        pe.nome, 
        c.numero as numero_contrato,
        pe.status,
        (
            SELECT GROUP_CONCAT(DISTINCT m.nome ORDER BY m.nome SEPARATOR ', ')
            FROM membro_projeto mp
            JOIN membro m ON m.id = mp.membro_id
            JOIN cargo cg ON cg.id = mp.cargo_id
            WHERE mp.projeto_externo_id = pe.id
              AND mp.data_saida IS NULL
              AND LOWER(cg.nome) LIKE '%gerente%'
        ) as gerente
    FROM projeto_externo pe
    LEFT JOIN contrato c ON c.projeto_externo_id = pe.id
    ORDER BY pe.nome
    '''
    resultado = await asyncio.to_thread(execute_query, query, fetch_all=True)
    if not resultado:
        return []
    
    projetos = []
    for r in resultado:
        # Filtra números de contratos temporários
        projetos.append({
            'id': r['id'],
            'nome': r['nome'],
            'numero_contrato': r['numero_contrato'] if r['numero_contrato'] and not r['numero_contrato'].startswith('CONTRATO-TEMP') else None,
            'gerente': r['gerente'] or 'Sem gerente',
            'status': r['status']
        })
    return projetos


async def validate_project_manager(respondente_nome: str, projeto_externo_id: int) -> bool:
    """Checks if a member is currently assigned as an active manager for a project.

    Queries the `membro_projeto` table to match the member's name and verifies
    if they hold a role matching '%gerente%projeto%' with no departure date (data_saida is NULL).

    Args:
        respondente_nome (str): The name of the member.
        projeto_externo_id (int): The database ID of the project.

    Returns:
        bool: True if the member is an active manager of the project, False otherwise.
    """
    query = '''
    SELECT mp.id
    FROM membro_projeto mp
    JOIN membro m ON m.id = mp.membro_id
    JOIN cargo c ON c.id = mp.cargo_id
    WHERE mp.projeto_externo_id = %s
      AND m.nome = %s
      AND mp.data_saida IS NULL
      AND LOWER(c.nome) LIKE '%gerente%'
    LIMIT 1
    '''
    resultado = await asyncio.to_thread(
        execute_query,
        query,
        (projeto_externo_id, respondente_nome),
        fetch_one=True,
    )
    return bool(resultado)


async def update_project_orientador_if_unknown(
    projeto_externo_id: int,
    possui_orientador: str,
    nome_orientador: str | None,
) -> None:
    """Updates the technical advisor info of a project if it has not been defined yet.

    If `possui_orientador` is NULL in the database, this function will set the values
    for `possui_orientador` (1 or 0) and `nome_orientador` (string name or None).

    Args:
        projeto_externo_id (int): The database ID of the project.
        possui_orientador (str): Affirmation string ('Sim' or 'Não').
        nome_orientador (str | None): The name of the technical advisor.
    """
    query = '''
    UPDATE projeto_externo
    SET possui_orientador = %s,
        nome_orientador = %s
    WHERE id = %s
      AND possui_orientador IS NULL
    '''
    possui_orientador_value = 1 if possui_orientador == 'Sim' else 0
    nome_orientador_value = nome_orientador if possui_orientador_value else None
    await asyncio.to_thread(
        execute_query,
        query,
        (possui_orientador_value, nome_orientador_value, projeto_externo_id),
    )


def parse_motivos_atraso(raw_motivos) -> list[str]:
    """Decodes JSON-encoded delay reasons and normalizes them into canonical categories.

    Takes a JSON-string, list, or string of reasons, cleans unicode escapes, and maps
    known variations to their canonical forms (e.g., 'Escopo mal definido' becomes
    'Indefinição e(ou) fuga de escopo').

    Args:
        raw_motivos (Any): The raw motivos data from database/JSON.

    Returns:
        list[str]: A list of clean canonical delay reasons.
    """
    if not raw_motivos:
        return []

    try:
        parsed_motivos = json.loads(raw_motivos)
    except (TypeError, json.JSONDecodeError):
        parsed_motivos = [raw_motivos]

    if isinstance(parsed_motivos, str):
        parsed_motivos = [parsed_motivos]

    cleaned = []
    for motivo in parsed_motivos:
        if motivo:
            motivo_str = str(motivo).strip()
            replacements = {
                'u00e7': 'ç',
                'u00e3': 'ã',
                'u00e9': 'é',
                'u00ed': 'í',
                'u00f3': 'ó',
                'u00ea': 'ê',
                'u00e2': 'â',
                'u00e0': 'à',
                'u00fa': 'ú',
                'u00e1': 'á',
                'u00c7': 'Ç',
                'u00c3': 'Ã',
                'u00c9': 'É',
                'u00cd': 'Í',
                'u00d3': 'Ó',
                'u00ca': 'Ê',
                'u00c2': 'Â',
                'u00c0': 'À',
                'u00da': 'Ú',
                'u00c1': 'Á',
            }
            for search, replace in replacements.items():
                motivo_str = motivo_str.replace(search, replace)
            
            # Mapeamento para motivos canônicos de atraso
            norm_mapping = {
                "Escopo mal definido": "Indefinição e(ou) fuga de escopo",
                "Mudança de requisitos": "Indefinição e(ou) fuga de escopo",
                "Indefinição e(ou) fuga de escopo": "Indefinição e(ou) fuga de escopo",
                
                "Falta de recurso": "Falta de recursos (Ex: Ferramentas, orçamento...)",
                "Falta de recursos": "Falta de recursos (Ex: Ferramentas, orçamento...)",
                "Falta de recursos (Ex.: Ferramentas, orçamento...)": "Falta de recursos (Ex: Ferramentas, orçamento...)",
                "Falta de recursos (Ex: Ferramentas, orçamento...)": "Falta de recursos (Ex: Ferramentas, orçamento...)",
                
                "Cliente lento": "Comunicação com cliente",
                "Comunicação com cliente": "Comunicação com cliente",
                
                "Problemas com equipe": "Problemas com equipe",
                "Capacidade técnica": "Capacidade técnica"
            }
            motivo_str = norm_mapping.get(motivo_str, motivo_str)
            cleaned.append(motivo_str)

    return cleaned


def count_motivos_atraso(rows: list[dict]) -> list[dict]:
    """Counts the occurrences of delay reasons from a list of rows.

    Parses reasons from each row and aggregates the total counts, returning
    them sorted in descending order of frequency.

    Args:
        rows (list[dict]): A list of database rows containing 'motivos_atraso'.

    Returns:
        list[dict]: A list of objects with 'name' (reason) and 'value' (count) keys.
    """
    counts: dict[str, int] = {}

    for row in rows:
        for motivo_label in parse_motivos_atraso(row.get('motivos_atraso')):
            counts[motivo_label] = counts.get(motivo_label, 0) + 1

    return [
        {'name': name, 'value': value}
        for name, value in sorted(counts.items(), key=lambda item: item[1], reverse=True)
    ]


def build_riscos_dashboard(rows: list[dict]) -> dict:
    """Builds metrics and grids for the Risks section of the PAPE dashboard.

    Aggregates projects currently at risk of delay, generates a matrix of reasons
    distributed by department coordination, and lists scores for budget sufficiency,
    client communication, and team training.

    Args:
        rows (list[dict]): Latest responses for each project containing risk indicators.

    Returns:
        dict: Risk analytics containing:
            - motivos_por_coordenacao (list[dict]): Matrix of reasons by coordination department.
            - projetos_em_risco (list[dict]): List of detailed project risk descriptions.
            - suficiencia_orcamento (list[dict]): Budget scores sorted.
            - comunicacao_cliente (list[dict]): Communication scores sorted.
            - capacitacao_equipe (list[dict]): Training scores sorted.
    """
    CANONICAL_MOTIVOS = [
        "Capacidade técnica",
        "Comunicação com cliente",
        "Falta de recursos (Ex: Ferramentas, orçamento...)",
        "Indefinição e(ou) fuga de escopo",
        "Problemas com equipe"
    ]
    
    CANONICAL_COORDENACOES = [
        "Construção e Energia",
        "Desenvolvimento de Máquinas",
        "Gestão de Negócios",
        "Otimização de Processos",
        "Tecnologia e Desenvolvimento"
    ]

    # Inicializa a matriz de motivos por coordenação com 0
    motivos_por_coordenacao = {
        motivo: {coord: 0 for coord in CANONICAL_COORDENACOES}
        for motivo in CANONICAL_MOTIVOS
    }

    projetos_em_risco: list[dict] = []
    suficiencia_orcamento: list[dict] = []
    comunicacao_cliente: list[dict] = []
    capacitacao_equipe: list[dict] = []

    for row in rows:
        projeto = row.get('projeto') or 'Projeto sem nome'
        status = row.get('status_cronograma') or 'Sem status'
        coordenacoes_raw = row.get('coordenacao') or 'Sem coordenação'
        coordenacoes = [coord.strip() for coord in str(coordenacoes_raw).split(',') if coord.strip()]
        motivos = parse_motivos_atraso(row.get('motivos_atraso'))
        is_risk_status = status in ('Com risco de atraso', 'Atrasado')

        if is_risk_status:
            projetos_em_risco.append({
                'projeto': projeto,
                'status': status,
                'motivos': motivos,
                'coordenacao': coordenacoes_raw,
            })

            for motivo in motivos:
                # Se houver um motivo customizado, inicializa dinamicamente se necessário
                if motivo not in motivos_por_coordenacao:
                    if motivo and motivo not in ('Outro', ''):
                        motivos_por_coordenacao[motivo] = {coord: 0 for coord in CANONICAL_COORDENACOES}
                    else:
                        continue
                
                for coordenacao in coordenacoes or ['Sem coordenação']:
                    if coordenacao not in motivos_por_coordenacao[motivo]:
                        motivos_por_coordenacao[motivo][coordenacao] = 0
                    motivos_por_coordenacao[motivo][coordenacao] += 1

        if row.get('suficiencia_orcamento') is not None:
            suficiencia_orcamento.append({
                'name': projeto,
                'value': int(row['suficiencia_orcamento']),
            })

        if row.get('comunicacao_cliente') is not None:
            comunicacao_cliente.append({
                'name': projeto,
                'value': int(row['comunicacao_cliente']),
            })

        if row.get('capacitacao_equipe') is not None:
            capacitacao_equipe.append({
                'name': projeto,
                'value': int(row['capacitacao_equipe']),
            })

    matriz_motivos = []
    ordered_keys = CANONICAL_MOTIVOS + [k for k in motivos_por_coordenacao if k not in CANONICAL_MOTIVOS]
    
    for motivo in ordered_keys:
        if motivo not in motivos_por_coordenacao:
            continue
        coordenacoes_counts = motivos_por_coordenacao[motivo]
        total = sum(coordenacoes_counts.values())
        matriz_motivos.append({
            'motivo': motivo,
            'total': total,
            'coordenacoes': coordenacoes_counts,
        })

    return {
        'motivos_por_coordenacao': matriz_motivos,
        'projetos_em_risco': projetos_em_risco,
        'suficiencia_orcamento': sorted(suficiencia_orcamento, key=lambda item: item['value']),
        'comunicacao_cliente': sorted(comunicacao_cliente, key=lambda item: item['value']),
        'capacitacao_equipe': sorted(capacitacao_equipe, key=lambda item: item['value']),
    }


def parse_score(value) -> int | None:
    """Parses and validates a numerical score to ensure it falls within the 1-5 range.

    Args:
        value (Any): The raw score value.

    Returns:
        int | None: The validated score as an integer, or None if invalid.
    """
    if value is None or value == '':
        return None

    try:
        score = int(value)
    except (TypeError, ValueError):
        return None

    if score < 1 or score > 5:
        return None

    return score


def build_metodo_escopo_dashboard(rows: list[dict]) -> dict:
    """Builds metrics for methodology effectiveness, rework, scope definitions, and training.

    Calculates scores for rework levels, scope definition, team training, and methodology
    effectiveness, and identifies projects needing attention due to low scores (<= 2).

    Args:
        rows (list[dict]): Latest responses for each project.

    Returns:
        dict: Scope and methodology analytics containing:
            - retrabalho (list[dict]): Rework scores.
            - variacao_escopo (list[dict]): Scope definition scores.
            - capacitacao_equipe (list[dict]): Team training scores.
            - eficacia_metodologia (list[dict]): Methodology effectiveness scores.
            - pontos_atencao (list[dict]): Projects with low scores.
            - medias (dict): Average scores for each metric.
    """
    fields = [
        ('nivel_retrabalho', 'retrabalho', 'Retrabalho'),
        ('variacao_escopo', 'variacao_escopo', 'Escopo definido'),
        ('capacitacao_equipe', 'capacitacao_equipe', 'Capacitação da equipe'),
        ('eficacia_metodologia', 'eficacia_metodologia', 'Eficácia da metodologia'),
    ]
    series: dict[str, list[dict]] = {result_key: [] for _, result_key, _ in fields}
    pontos_atencao: list[dict] = []

    for row in rows:
        projeto = row.get('projeto') or 'Projeto sem nome'
        modelo = row.get('modelo_gerenciamento') or 'Sem modelo'

        for field, result_key, label in fields:
            score = parse_score(row.get(field))
            if score is None:
                continue

            series[result_key].append({
                'name': projeto,
                'value': score,
            })

            if score <= 2:
                pontos_atencao.append({
                    'projeto': projeto,
                    'indicador': label,
                    'nota': score,
                    'modelo': modelo,
                })

    medias = {}
    for result_key, values in series.items():
        if not values:
            medias[result_key] = 0
            continue
        medias[result_key] = round(
            sum(item['value'] for item in values) / len(values),
            1,
        )

    return {
        'retrabalho': sorted(series['retrabalho'], key=lambda item: (item['value'], item['name'])),
        'variacao_escopo': sorted(series['variacao_escopo'], key=lambda item: (item['value'], item['name'])),
        'capacitacao_equipe': sorted(series['capacitacao_equipe'], key=lambda item: (item['value'], item['name'])),
        'eficacia_metodologia': sorted(series['eficacia_metodologia'], key=lambda item: (item['value'], item['name'])),
        'pontos_atencao': sorted(
            pontos_atencao,
            key=lambda item: (item['indicador'], item['nota'], item['projeto']),
        ),
        'medias': medias,
    }


def average_score(items: list[dict]) -> float:
    """Calculates the average value from a list of dictionaries.

    Args:
        items (list[dict]): List of dictionaries with a 'value' key.

    Returns:
        float: Calculated mean rounded to one decimal place, or 0 if empty.
    """
    if not items:
        return 0

    return round(sum(item['value'] for item in items) / len(items), 1)


def has_orientador(row: dict) -> bool:
    """Determines if a project has technical advisory based on row properties.

    Checks flags like `possui_orientador` (Sim, 1, True) and technical advisor name.

    Args:
        row (dict): Database row representing a project or monitoring record.

    Returns:
        bool: True if the project has an advisor, False otherwise.
    """
    raw_value = row.get('possui_orientador')
    orientador = row.get('nome_orientador')

    if isinstance(raw_value, str):
        has_flag = raw_value.strip().lower() in ('1', 'sim', 'true')
    else:
        has_flag = bool(raw_value)

    return has_flag or bool(orientador)


def build_cliente_orientacao_dashboard(rows: list[dict]) -> dict:
    """Builds dashboard analytics for client relationships and technical advisor metrics.

    Computes client communication, trust, satisfaction, value perception, and aggregates
    technical advisor availability and effectiveness scores.

    Args:
        rows (list[dict]): Latest responses for each project.

    Returns:
        dict: Client relationship and technical advisor analytics containing:
            - comunicacao_cliente (list[dict]): Client communication scores.
            - confianca_cliente (list[dict]): Client trust scores.
            - satisfacao_cliente (list[dict]): Client satisfaction scores.
            - valorizacao_cliente (list[dict]): Client value perception scores.
            - orientadores (dict): Advisor effectiveness/availability lists.
            - impactos (list[dict]): Client impact descriptions.
            - pontos_atencao (list[dict]): Low-scoring client relation indicators.
            - quantidade_orientadores (int): Distinct active advisors count.
            - projetos_com_orientacao_pct (float): Percentage of projects with an advisor.
            - medias (dict): Average scores.
    """
    fields = [
        ('comunicacao_cliente', 'comunicacao_cliente', 'Comunicação efetiva'),
        ('abertura_cliente', 'confianca_cliente', 'Confiança do cliente'),
        ('satisfacao_cliente', 'satisfacao_cliente', 'Satisfação do cliente'),
        ('cliente_percebeu_valor', 'valorizacao_cliente', 'Valorização pelo cliente'),
    ]
    series: dict[str, list[dict]] = {result_key: [] for _, result_key, _ in fields}
    pontos_atencao: list[dict] = []
    impactos: list[dict] = []
    orientadores: dict[str, dict[str, list[int]]] = {}
    projetos_com_orientacao = 0

    for row in rows:
        projeto = row.get('projeto') or 'Projeto sem nome'
        orientador = row.get('nome_orientador') or 'Sem orientador'
        projeto_tem_orientador = has_orientador(row)

        if projeto_tem_orientador:
            projetos_com_orientacao += 1

        for field, result_key, label in fields:
            score = parse_score(row.get(field))
            if score is None:
                continue

            series[result_key].append({
                'name': projeto,
                'value': score,
            })

            if score <= 2:
                pontos_atencao.append({
                    'projeto': projeto,
                    'indicador': label,
                    'nota': score,
                    'orientador': orientador if projeto_tem_orientador else 'Sem orientador',
                })

        impactos.append({
            'projeto': projeto,
            'impacto_cliente': row.get('impacto_cliente') or 'Sem impacto informado',
            'cliente_percebeu_valor': parse_score(row.get('cliente_percebeu_valor')),
            'orientador': orientador if projeto_tem_orientador else 'Sem orientador',
        })

        if projeto_tem_orientador:
            orientadores.setdefault(orientador, {
                'efetividade': [],
                'disponibilidade': [],
            })
            efetividade = parse_score(row.get('efetividade_orientador'))
            disponibilidade = parse_score(row.get('disponibilidade_orientador'))

            if efetividade is not None:
                orientadores[orientador]['efetividade'].append(efetividade)
            if disponibilidade is not None:
                orientadores[orientador]['disponibilidade'].append(disponibilidade)

    orientador_efetividade = []
    orientador_disponibilidade = []
    for orientador, scores in orientadores.items():
        if scores['efetividade']:
            orientador_efetividade.append({
                'name': orientador,
                'value': round(sum(scores['efetividade']) / len(scores['efetividade']), 1),
            })
        if scores['disponibilidade']:
            orientador_disponibilidade.append({
                'name': orientador,
                'value': round(sum(scores['disponibilidade']) / len(scores['disponibilidade']), 1),
            })

    total_projetos = len(rows)
    projetos_com_orientacao_pct = (
        round((projetos_com_orientacao / total_projetos) * 100, 1)
        if total_projetos
        else 0
    )

    return {
        'comunicacao_cliente': sorted(series['comunicacao_cliente'], key=lambda item: (item['value'], item['name'])),
        'confianca_cliente': sorted(series['confianca_cliente'], key=lambda item: (item['value'], item['name'])),
        'satisfacao_cliente': sorted(series['satisfacao_cliente'], key=lambda item: (item['value'], item['name'])),
        'valorizacao_cliente': sorted(series['valorizacao_cliente'], key=lambda item: (item['value'], item['name'])),
        'orientadores': {
            'efetividade': sorted(orientador_efetividade, key=lambda item: item['value'], reverse=True),
            'disponibilidade': sorted(orientador_disponibilidade, key=lambda item: item['value'], reverse=True),
        },
        'impactos': impactos,
        'pontos_atencao': sorted(
            pontos_atencao,
            key=lambda item: (item['indicador'], item['nota'], item['projeto']),
        ),
        'quantidade_orientadores': len(orientadores),
        'projetos_com_orientacao_pct': projetos_com_orientacao_pct,
        'medias': {
            'comunicacao_cliente': average_score(series['comunicacao_cliente']),
            'confianca_cliente': average_score(series['confianca_cliente']),
            'satisfacao_cliente': average_score(series['satisfacao_cliente']),
            'valorizacao_cliente': average_score(series['valorizacao_cliente']),
            'efetividade_orientador': average_score(orientador_efetividade),
            'disponibilidade_orientador': average_score(orientador_disponibilidade),
        },
    }


def parse_csv_values(raw_value) -> list[str]:
    """Parses a raw CSV string or list into a clean list of strings.

    Args:
        raw_value (Any): Comma-separated string or list.

    Returns:
        list[str]: A list of clean trimmed strings.
    """
    if not raw_value:
        return []

    if isinstance(raw_value, list):
        return [str(item).strip() for item in raw_value if str(item).strip()]

    return [item.strip() for item in str(raw_value).split(',') if item.strip()]


def normalize_yes(value) -> bool:
    """Normalizes affirmative values into a boolean.

    Matches variations like '1', 'Sim', 'True', 'Yes'.

    Args:
        value (Any): The value to check.

    Returns:
        bool: True if it matches an affirmative, False otherwise.
    """
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'sim', 'true', 'yes')

    return bool(value)


def story_points_midpoint(value: str | None) -> int | None:
    """Maps a sprint story points percentage range to its midpoint integer value.

    Args:
        value (str | None): Range string (e.g. '21-40%').

    Returns:
        int | None: Midpoint integer value (e.g. 30), or None if invalid.
    """
    if not value:
        return None

    ranges = {
        '0-20%': 10,
        '21-40%': 30,
        '41-60%': 50,
        '61-80%': 70,
        '81-100%': 90,
    }
    return ranges.get(value)


def completion_midpoint(value: str | None) -> int | None:
    """Maps a project completion percentage range to its midpoint integer value.

    Args:
        value (str | None): Range string (e.g. '41-60%').

    Returns:
        int | None: Midpoint integer value (e.g. 50), or None if invalid.
    """
    if not value:
        return None

    ranges = {
        '0-20%': 10,
        '21-40%': 30,
        '41-60%': 50,
        '61-80%': 70,
        '81-100%': 90,
    }
    return ranges.get(value)


def build_agil_dashboard(rows: list[dict]) -> dict:
    """Builds Agile metrics dashboard analytics.

    Summarizes agile projects metrics such as story points ranges, sprint impediments,
    customer impact, PMO interventions, and 1-on-1 requirements.

    Args:
        rows (list[dict]): Agile monitoring rows.

    Returns:
        dict: Agile analytics containing:
            - story_points (list[dict]): Story points counts.
            - impedimentos (list[dict]): Impediment type counts.
            - impactos (list[dict]): Customer impact counts.
            - projetos (list[dict]): Detailed list of agile projects.
            - resumo (dict): Summaries metrics (averages, totals).
    """
    story_counts: dict[str, int] = {}
    impedimento_counts: dict[str, int] = {}
    impacto_counts: dict[str, int] = {}
    projetos: list[dict] = []
    story_midpoints: list[int] = []
    projetos_com_impedimento = 0
    intervencoes_pmo = 0
    solicitacoes_1_1 = 0

    for row in rows:
        projeto = row.get('projeto') or 'Projeto sem nome'
        pct_story_points = row.get('pct_story_points') or 'Sem sprint'
        impedimentos = parse_csv_values(row.get('impedimentos'))
        impacto_cliente = row.get('impacto_cliente') or 'Sem impacto informado'
        intervencao_pmo = row.get('intervencao_pmo') or 'Não informado'
        one_on_one_pmo = row.get('one_on_one_pmo') or 'Não informado'

        story_counts[pct_story_points] = story_counts.get(pct_story_points, 0) + 1
        impacto_counts[impacto_cliente] = impacto_counts.get(impacto_cliente, 0) + 1

        midpoint = story_points_midpoint(row.get('pct_story_points'))
        if midpoint is not None:
            story_midpoints.append(midpoint)

        if impedimentos:
            projetos_com_impedimento += 1
        for impedimento in impedimentos:
            impedimento_counts[impedimento] = impedimento_counts.get(impedimento, 0) + 1

        if normalize_yes(intervencao_pmo):
            intervencoes_pmo += 1
        if normalize_yes(one_on_one_pmo):
            solicitacoes_1_1 += 1

        projetos.append({
            'projeto': projeto,
            'gerente': row.get('gerente') or 'Sem gerente',
            'data_resposta': row.get('data_resposta'),
            'impacto_cliente': impacto_cliente,
            'pct_story_points': pct_story_points,
            'impedimentos': impedimentos,
            'intervencao_pmo': intervencao_pmo,
            'one_on_one_pmo': one_on_one_pmo,
        })

    return {
        'story_points': [
            {'name': name, 'value': value}
            for name, value in sorted(
                story_counts.items(),
                key=lambda item: story_points_midpoint(item[0]) or 0,
                reverse=True,
            )
        ],
        'impedimentos': [
            {'name': name, 'value': value}
            for name, value in sorted(impedimento_counts.items(), key=lambda item: item[1], reverse=True)
        ],
        'impactos': [
            {'name': name, 'value': value}
            for name, value in sorted(impacto_counts.items(), key=lambda item: item[1], reverse=True)
        ],
        'projetos': projetos,
        'resumo': {
            'total_projetos': len(projetos),
            'media_story_points': round(sum(story_midpoints) / len(story_midpoints), 1) if story_midpoints else 0,
            'projetos_com_impedimento': projetos_com_impedimento,
            'intervencoes_pmo': intervencoes_pmo,
            'solicitacoes_1_1': solicitacoes_1_1,
        },
    }


def format_dashboard_date(value) -> str:
    """Formats a datetime/date object or ISO string to standard DD/MM/YYYY format.

    Args:
        value (Any): Date value to format.

    Returns:
        str: Date string in DD/MM/YYYY format, or the string representation fallback.
    """
    if not value:
        return 'Sem data'

    if hasattr(value, 'strftime'):
        return value.strftime('%d/%m/%Y')

    try:
        return datetime.fromisoformat(str(value)).strftime('%d/%m/%Y')
    except ValueError:
        return str(value)


def build_detalhe_dashboard(rows: list[dict], selected_project_id: int | None = None) -> dict:
    """Builds detailed historical data for a specific project focus.

    Determines the focus project (defaults to the worst schedule status or highest
    completion if not specified) and aggregates its timeline history, metrics,
    delay reasons, and a summary list of all projects.

    Args:
        rows (list[dict]): Full database log of monitoring records.
        selected_project_id (int | None): Selected project ID for focus. Defaults to None.

    Returns:
        dict: Focus project analytics containing:
            - projeto_foco (dict): Basic focus project information.
            - metricas (dict): Focus project latest metrics.
            - andamento (list[dict]): Project progression range history midpoints.
            - motivos_atraso (list[dict]): Aggregated delay reasons for the project.
            - historico (list[dict]): Complete historical list of submissions.
            - projetos (list[dict]): Sorted list of all projects and status.
    """
    if not rows:
        return {
            'projeto_foco': None,
            'metricas': {},
            'andamento': [],
            'motivos_atraso': [],
            'historico': [],
            'projetos': [],
        }

    latest_by_project: dict[int | str, dict] = {}
    for row in rows:
        project_key = row.get('projeto_id') or row.get('projeto')
        current_latest = latest_by_project.get(project_key)

        if current_latest is None:
            latest_by_project[project_key] = row
            continue

        current_order = (str(current_latest.get('data_resposta') or ''), current_latest.get('id') or 0)
        candidate_order = (str(row.get('data_resposta') or ''), row.get('id') or 0)
        if candidate_order > current_order:
            latest_by_project[project_key] = row

    status_priority = {
        'Atrasado': 0,
        'Com risco de atraso': 1,
        'Dentro do prazo': 2,
        'Concluido': 3,
        'Concluído': 3,
    }
    latest_rows = list(latest_by_project.values())

    focus_row = None
    if selected_project_id is not None:
        try:
            sel_id = int(selected_project_id)
            for r in latest_rows:
                if r.get('projeto_id') == sel_id:
                    focus_row = r
                    break
        except (ValueError, TypeError):
            pass

    if focus_row is None:
        focus_row = sorted(
            latest_rows,
            key=lambda row: (
                status_priority.get(row.get('status_cronograma'), 9),
                -(completion_midpoint(row.get('pct_conclusao')) or 0),
                str(row.get('projeto') or ''),
            ),
        )[0]
    focus_key = focus_row.get('projeto_id') or focus_row.get('projeto')
    focus_history = [
        row
        for row in rows
        if (row.get('projeto_id') or row.get('projeto')) == focus_key
    ]
    focus_history = sorted(
        focus_history,
        key=lambda row: (str(row.get('data_resposta') or ''), row.get('id') or 0),
    )

    projeto_foco = {
        'projeto_id': focus_row.get('projeto_id'),
        'projeto': focus_row.get('projeto') or 'Projeto sem nome',
        'gerente': focus_row.get('gerente') or 'Sem gerente',
        'status_cronograma': focus_row.get('status_cronograma') or 'Sem status',
        'pct_conclusao': focus_row.get('pct_conclusao') or 'Sem conclusão',
        'data_resposta': focus_row.get('data_resposta'),
        'impacto_cliente': focus_row.get('impacto_cliente') or 'Sem impacto informado',
        'intervencao_pmo': focus_row.get('intervencao_pmo') or 'Não informado',
        'one_on_one_pmo': focus_row.get('one_on_one_pmo') or 'Não informado',
    }

    metricas = {
        'confianca_cliente': parse_score(focus_row.get('abertura_cliente')) or 0,
        'comunicacao_cliente': parse_score(focus_row.get('comunicacao_cliente')) or 0,
        'eficacia_metodologia': parse_score(focus_row.get('eficacia_metodologia')) or 0,
        'capacitacao_equipe': parse_score(focus_row.get('capacitacao_equipe')) or 0,
        'nivel_retrabalho': parse_score(focus_row.get('nivel_retrabalho')) or 0,
        'suficiencia_orcamento': parse_score(focus_row.get('suficiencia_orcamento')) or 0,
    }

    historico = []
    andamento = []
    for row in focus_history:
        historico.append({
            'data_resposta': str(row.get('data_resposta')) if row.get('data_resposta') else None,
            'status_cronograma': row.get('status_cronograma') or 'Sem status',
            'pct_conclusao': row.get('pct_conclusao') or 'Sem conclusão',
            'impacto_cliente': row.get('impacto_cliente') or 'Sem impacto informado',
            'intervencao_pmo': row.get('intervencao_pmo') or 'Não informado',
            'one_on_one_pmo': row.get('one_on_one_pmo') or 'Não informado',
            'confianca_cliente': parse_score(row.get('abertura_cliente')) or 0,
            'comunicacao_cliente': parse_score(row.get('comunicacao_cliente')) or 0,
            'eficacia_metodologia': parse_score(row.get('eficacia_metodologia')) or 0,
            'capacitacao_equipe': parse_score(row.get('capacitacao_equipe')) or 0,
            'nivel_retrabalho': parse_score(row.get('nivel_retrabalho')) or 0,
            'suficiencia_orcamento': parse_score(row.get('suficiencia_orcamento')) or 0,
            'motivos_atraso': parse_motivos_atraso(row.get('motivos_atraso')),
        })
        midpoint = completion_midpoint(row.get('pct_conclusao'))
        if midpoint is not None:
            andamento.append({
                'name': format_dashboard_date(row.get('data_resposta')),
                'value': midpoint,
            })

    projetos = [
        {
            'projeto_id': row.get('projeto_id'),
            'projeto': row.get('projeto') or 'Projeto sem nome',
            'gerente': row.get('gerente') or 'Sem gerente',
            'status_cronograma': row.get('status_cronograma') or 'Sem status',
            'pct_conclusao': row.get('pct_conclusao') or 'Sem conclusão',
            'data_resposta': row.get('data_resposta'),
        }
        for row in sorted(
            latest_rows,
            key=lambda row: (
                status_priority.get(row.get('status_cronograma'), 9),
                str(row.get('projeto') or ''),
            ),
        )
    ]

    return {
        'projeto_foco': projeto_foco,
        'metricas': metricas,
        'andamento': andamento,
        'motivos_atraso': count_motivos_atraso(focus_history),
        'historico': historico,
        'projetos': projetos,
    }


@app.get('/api/projetos/{projeto_id}')
async def get_projeto_detalhes(projeto_id: int):
    """GET /api/projetos/{projeto_id}

    Retrieves detailed info for a single project.
    Fetches the project description, linked contract details (value and contract number),
    associated services and department coordinations, active team members (with their roles
    and department affiliations), and a list of all historical monitoring logs.

    Args:
        projeto_id (int): The database ID of the project.

    Returns:
        dict: Detailed project data containing:
            - id (int): Project ID.
            - nome (str): Project name.
            - descricao (str): Project description.
            - data_inicio (str): Start date.
            - numero_contrato (str): Contract number.
            - valor_total (float): Contract total value.
            - possui_orientador (bool): Advisor flag.
            - nome_orientador (str): Advisor name.
            - status (str): Project status (ativo, finalizado, pausado).
            - servicos (list[dict]): Services associated with the project.
            - coordenacoes (list[dict]): Coordinations department names.
            - membros (list[dict]): Team members active in the project.
            - acompanhamentos (list[dict]): List of PAPE monitoring submissions history.
    """
    query = '''
    SELECT pe.id, pe.nome, pe.descricao, pe.descricao_projeto, pe.data_inicio, c.numero as numero_contrato,
           c.valor_total, pe.possui_orientador, pe.nome_orientador, pe.status
    FROM projeto_externo pe
    LEFT JOIN contrato c ON c.projeto_externo_id = pe.id
    WHERE pe.id = %s
    '''
    projeto = await asyncio.to_thread(execute_query, query, (projeto_id,), fetch_one=True)
    if not projeto:
        raise HTTPException(status_code=404, detail='Projeto não encontrado')

    servicos_query = '''
    SELECT s.id, s.nome
    FROM projeto_servico ps
    JOIN servico s ON s.id = ps.servico_id
    WHERE ps.projeto_externo_id = %s
    '''
    coordenacoes_query = '''
    SELECT DISTINCT c.id, c.nome
    FROM projeto_servico ps
    JOIN servico s ON s.id = ps.servico_id
    JOIN coordenacao c ON c.id = s.coordenacao_id
    WHERE ps.projeto_externo_id = %s
    '''
    membros_query = '''
    SELECT m.id, m.nome, m.email, cg.nome as cargo, co.id as coordenacao_id, co.nome as coordenacao, co.sigla as coordenacao_sigla
    FROM membro_projeto mp
    JOIN membro m ON m.id = mp.membro_id
    JOIN cargo cg ON cg.id = mp.cargo_id
    LEFT JOIN coordenacao co ON co.id = mp.coordenacao_id
    WHERE mp.projeto_externo_id = %s
      AND mp.data_saida IS NULL
    ORDER BY m.nome
    '''
    acompanhamentos_query = '''
    SELECT ap.id, ap.data_resposta, ap.modelo_gerenciamento, ap.pct_conclusao,
           ap.status_cronograma, ap.motivos_atraso, ap.capacitacao_equipe,
           ap.eficacia_metodologia, ap.nivel_retrabalho, ap.comunicacao_cliente,
           ap.suficiencia_orcamento_nota, ap.orcamento_nao_necessario,
           ap.cliente_percebeu_valor, ap.pct_marcos_prazo, ap.variacao_escopo,
           ap.impacto_cliente, ap.abertura_cliente, ap.satisfacao_cliente,
           ao.nome_orientador, ao.efetividade_orientador, ao.disponibilidade_orientador
    FROM acompanhamento_projeto ap
    LEFT JOIN acomp_orientador ao ON ao.acompanhamento_id = ap.id
    WHERE ap.projeto_externo_id = %s
    ORDER BY ap.data_resposta DESC, ap.id DESC
    '''

    servicos, coordenacoes, membros, acompanhamentos = await asyncio.gather(
        asyncio.to_thread(execute_query, servicos_query, (projeto_id,), fetch_all=True),
        asyncio.to_thread(execute_query, coordenacoes_query, (projeto_id,), fetch_all=True),
        asyncio.to_thread(execute_query, membros_query, (projeto_id,), fetch_all=True),
        asyncio.to_thread(execute_query, acompanhamentos_query, (projeto_id,), fetch_all=True)
    )

    projeto['servicos'] = servicos or []
    projeto['coordenacoes'] = coordenacoes or []
    projeto['membros'] = membros or []
    
    # Formatar campos complexos nos acompanhamentos (JSON de motivos de atraso)
    # Usar parse_motivos_atraso para garantir decodificação de unicode escapes
    for acomp in (acompanhamentos or []):
        acomp['motivos_atraso'] = parse_motivos_atraso(acomp.get('motivos_atraso'))

    projeto['acompanhamentos'] = acompanhamentos or []
    return projeto


@app.put('/api/projetos/{projeto_id}')
async def update_projeto(projeto_id: int, data: ProjetoUpdate, _auth: None = Depends(require_admin_token)):
    """PUT /api/projetos/{projeto_id}

    Updates fields of an existing project and its relational dependencies.
    Requires header admin token authentication.
    Validates contract uniqueness before modifying contracts. Updates associated
    services and dynamically syncs active project members, project manager, and technical advisor.

    Args:
        projeto_id (int): Database ID of the project to update.
        data (ProjetoUpdate): Pydantic body containing the update payload.
        _auth (None): Depends on require_admin_token dependency.

    Returns:
        dict: A dictionary indicating success. E.g. {'success': True, 'message': '...'}
    """
    check_query = 'SELECT id FROM projeto_externo WHERE id = %s'
    exists = await asyncio.to_thread(execute_query, check_query, (projeto_id,), fetch_one=True)
    if not exists:
        raise HTTPException(status_code=404, detail='Projeto não encontrado')

    # Número de contrato é UNIQUE global: se já pertence a OUTRO projeto, avisa
    # em vez de estourar erro 500 na constraint.
    numero_informado = (data.numero_contrato or '').strip()
    if numero_informado:
        dono = await asyncio.to_thread(
            execute_query,
            'SELECT projeto_externo_id FROM contrato WHERE numero = %s LIMIT 1',
            (numero_informado,),
            fetch_one=True,
        )
        if dono and dono['projeto_externo_id'] != projeto_id:
            raise HTTPException(
                status_code=400,
                detail=f'Número de contrato "{numero_informado}" já pertence a outro projeto.',
            )

    update_pe_query = '''
    UPDATE projeto_externo
    SET nome = %s,
        descricao_projeto = %s,
        data_inicio = %s,
        possui_orientador = %s,
        nome_orientador = %s,
        status = %s
    WHERE id = %s
    '''
    data_inicio = data.data_inicio if data.data_inicio else None
    nome_orientador = data.nome_orientador if data.possui_orientador == 1 else None
    status_val = data.status if data.status else 'ativo'

    await asyncio.to_thread(
        execute_query,
        update_pe_query,
        (data.nome, data.descricao_projeto, data_inicio, data.possui_orientador, nome_orientador, status_val, projeto_id)
    )

    contract_query = 'SELECT id FROM contrato WHERE projeto_externo_id = %s'
    contract = await asyncio.to_thread(execute_query, contract_query, (projeto_id,), fetch_one=True)

    if contract:
        # Campo vazio no form NÃO apaga: editar um projeto sem preencher número/valor
        # zerava o contrato sincronizado do Pipefy (valor_total = 0, numero = '').
        numero_novo = (data.numero_contrato or '').strip()
        update_c_query = '''
        UPDATE contrato
        SET numero = CASE WHEN %s = '' THEN numero ELSE %s END,
            valor_total = COALESCE(%s, valor_total)
        WHERE projeto_externo_id = %s
        '''
        await asyncio.to_thread(
            execute_query,
            update_c_query,
            (numero_novo, numero_novo, data.valor_total, projeto_id)
        )
    elif data.numero_contrato or data.valor_total:
        client_id = await get_cliente_placeholder()
        numero = (data.numero_contrato or '').strip() or f'CONTRATO-TEMP-{projeto_id}'

        insert_c_query = '''
        INSERT INTO contrato (cliente_id, projeto_externo_id, numero, valor_total)
        VALUES (%s, %s, %s, %s)
        '''
        await asyncio.to_thread(
            execute_query,
            insert_c_query,
            (client_id, projeto_id, numero, data.valor_total or 0.0)
        )

    if data.servicos_projeto is not None:
        await asyncio.to_thread(
            execute_query,
            'DELETE FROM projeto_servico WHERE projeto_externo_id = %s',
            (projeto_id,)
        )
        for servico_id in data.servicos_projeto:
            await asyncio.to_thread(
                execute_query,
                'INSERT IGNORE INTO projeto_servico (projeto_externo_id, servico_id) VALUES (%s, %s)',
                (projeto_id, servico_id),
            )

    if data.membros_projeto is not None:
        membros_ativos_query = '''
        SELECT membro_id, coordenacao_id 
        FROM membro_projeto 
        WHERE projeto_externo_id = %s AND cargo_id != 31 AND data_saida IS NULL
        '''
        membros_ativos = await asyncio.to_thread(execute_query, membros_ativos_query, (projeto_id,), fetch_all=True)
        db_membros = {f"{m['membro_id']}-{m['coordenacao_id']}" for m in membros_ativos} if membros_ativos else set()
        
        req_membros = set()
        for chave in data.membros_projeto:
            partes = chave.split('-')
            if len(partes) == 2:
                try:
                    m_id = int(partes[0])
                    c_id = int(partes[1])
                    if c_id == 0:
                        c_id = await get_coordenacao_do_membro(m_id)
                        if c_id is None:
                            continue
                    req_membros.add(f"{m_id}-{c_id}")
                except ValueError:
                    continue

        membros_remover = db_membros - req_membros
        for chave in membros_remover:
            m_id, c_id = map(int, chave.split('-'))
            await asyncio.to_thread(
                execute_query,
                '''UPDATE membro_projeto 
                   SET data_saida = CURRENT_DATE() 
                   WHERE projeto_externo_id = %s AND membro_id = %s AND coordenacao_id = %s AND cargo_id != 31 AND data_saida IS NULL''',
                (projeto_id, m_id, c_id)
            )

        membros_adicionar = req_membros - db_membros
        for chave in membros_adicionar:
            m_id, c_id = map(int, chave.split('-'))
            cargo_id = await get_cargo_consultor_do_membro(m_id)
            await asyncio.to_thread(
                execute_query,
                '''INSERT INTO membro_projeto (membro_id, projeto_externo_id, coordenacao_id, cargo_id, data_entrada)
                   VALUES (%s, %s, %s, %s, CURRENT_DATE())''',
                (m_id, projeto_id, c_id, cargo_id)
            )

    if data.gerente_projeto is not None:
        current_gerente_query = '''
        SELECT mp.membro_id, m.nome 
        FROM membro_projeto mp 
        JOIN membro m ON m.id = mp.membro_id 
        WHERE mp.projeto_externo_id = %s AND mp.cargo_id = 31 AND mp.data_saida IS NULL
        '''
        current_gerente = await asyncio.to_thread(execute_query, current_gerente_query, (projeto_id,), fetch_one=True)
        current_gerente_nome = current_gerente['nome'] if current_gerente else None
        current_gerente_id = current_gerente['membro_id'] if current_gerente else None

        novo_gerente_nome = data.gerente_projeto.strip() if data.gerente_projeto else None
        
        if novo_gerente_nome != current_gerente_nome:
            if current_gerente_id:
                await asyncio.to_thread(
                    execute_query,
                    '''UPDATE membro_projeto 
                       SET data_saida = CURRENT_DATE() 
                       WHERE projeto_externo_id = %s AND membro_id = %s AND cargo_id = 31 AND data_saida IS NULL''',
                    (projeto_id, current_gerente_id)
                )
            
            if novo_gerente_nome:
                novo_gerente = await asyncio.to_thread(
                    execute_query,
                    'SELECT id FROM membro WHERE nome = %s LIMIT 1',
                    (novo_gerente_nome,),
                    fetch_one=True,
                )
                if novo_gerente:
                    n_id = novo_gerente['id']
                    coordenacao_id = await get_coordenacao_do_membro(n_id)
                    if coordenacao_id:
                        await asyncio.to_thread(
                            execute_query,
                            '''INSERT INTO membro_projeto (membro_id, projeto_externo_id, coordenacao_id, cargo_id, data_entrada)
                               VALUES (%s, %s, %s, 31, CURRENT_DATE())''',
                            (n_id, projeto_id, coordenacao_id)
                        )

    return {'success': True, 'message': 'Projeto atualizado com sucesso'}



def _delete_projeto_tx(projeto_id: int) -> bool:
    """Apaga o projeto e todas as dependências numa única transação. Retorna False se não existe.

    Importante: acompanhamento_projeto e contrato_pagamento referenciam o contrato
    via contrato_id (FK RESTRICT, NOT NULL). Por inconsistências de dados (ex.: um
    contrato que migrou de projeto), pode existir uma linha ligada ao contrato deste
    projeto mas com projeto_externo_id de OUTRO projeto. Por isso a limpeza é feita
    por projeto_externo_id OU pelos contratos do projeto (contrato_id IN ...), senão
    o DELETE FROM contrato falha com erro 1451 (fk_acomp_contrato / fk_cp_contrato).

    Args:
        projeto_id (int): Database ID of the project.

    Returns:
        bool: True if project exists and deleted, False otherwise.
    """
    with transaction() as conn:
        cur = conn.cursor()
        cur.execute('SELECT id FROM projeto_externo WHERE id = %s', (projeto_id,))
        if not cur.fetchone():
            return False
        # Solta transações que apontam para pagamentos deste projeto (por projeto OU por contrato)
        cur.execute(
            '''UPDATE transacao SET contrato_pagamento_id = NULL
               WHERE contrato_pagamento_id IN (
                   SELECT id FROM contrato_pagamento
                   WHERE projeto_externo_id = %s
                      OR contrato_id IN (SELECT id FROM contrato WHERE projeto_externo_id = %s))''',
            (projeto_id, projeto_id),
        )
        cur.execute('UPDATE transacao SET projeto_externo_id = NULL WHERE projeto_externo_id = %s', (projeto_id,))
        # Filhos do contrato (RESTRICT): apagar por projeto OU pelos contratos do projeto
        cur.execute(
            '''DELETE FROM acompanhamento_projeto
               WHERE projeto_externo_id = %s
                  OR contrato_id IN (SELECT id FROM contrato WHERE projeto_externo_id = %s)''',
            (projeto_id, projeto_id),
        )
        cur.execute(
            '''DELETE FROM contrato_pagamento
               WHERE projeto_externo_id = %s
                  OR contrato_id IN (SELECT id FROM contrato WHERE projeto_externo_id = %s)''',
            (projeto_id, projeto_id),
        )
        # Filhos diretos do projeto
        cur.execute('DELETE FROM membro_projeto WHERE projeto_externo_id = %s', (projeto_id,))
        cur.execute('DELETE FROM projeto_servico WHERE projeto_externo_id = %s', (projeto_id,))
        # Agora o contrato e o projeto
        cur.execute('DELETE FROM contrato WHERE projeto_externo_id = %s', (projeto_id,))
        cur.execute('DELETE FROM projeto_externo WHERE id = %s', (projeto_id,))
        return True


@app.delete('/api/projetos/{projeto_id}')
async def delete_projeto(projeto_id: int, _auth: None = Depends(require_admin_token)):
    """DELETE /api/projetos/{projeto_id}

    Deletes a project and all associated cascading dependencies atomically.
    Requires header admin token authentication.

    Args:
        projeto_id (int): Database ID of the project to delete.
        _auth (None): Depends on require_admin_token dependency.

    Returns:
        dict: E.g. {'success': True, 'message': '...'}
    """
    existe = await asyncio.to_thread(_delete_projeto_tx, projeto_id)
    if not existe:
        raise HTTPException(status_code=404, detail='Projeto não encontrado')
    return {'success': True, 'message': 'Projeto excluído com sucesso'}


def _delete_acompanhamento_tx(acompanhamento_id: int) -> bool:
    """Deletes a PAPE monitoring record and conditional tables in a transaction.

    Args:
        acompanhamento_id (int): Database ID of the monitoring record.

    Returns:
        bool: True if record exists and deleted, False otherwise.
    """
    with transaction() as conn:
        cur = conn.cursor()
        cur.execute('SELECT id FROM acompanhamento_projeto WHERE id = %s', (acompanhamento_id,))
        if not cur.fetchone():
            return False
        cur.execute('DELETE FROM acomp_orientador WHERE acompanhamento_id = %s', (acompanhamento_id,))
        cur.execute('DELETE FROM acomp_sprint WHERE acompanhamento_id = %s', (acompanhamento_id,))
        cur.execute('DELETE FROM acomp_impedimento WHERE acompanhamento_id = %s', (acompanhamento_id,))
        cur.execute('DELETE FROM acompanhamento_projeto WHERE id = %s', (acompanhamento_id,))
        return True


@app.delete('/api/acompanhamentos/{acompanhamento_id}')
async def delete_acompanhamento(acompanhamento_id: int, _auth: None = Depends(require_admin_token)):
    """DELETE /api/acompanhamentos/{acompanhamento_id}

    Deletes an individual project monitoring record.
    Requires header admin token authentication.

    Args:
        acompanhamento_id (int): Database ID of the record to delete.
        _auth (None): Depends on require_admin_token dependency.

    Returns:
        dict: E.g. {'success': True, 'message': '...'}
    """
    existe = await asyncio.to_thread(_delete_acompanhamento_tx, acompanhamento_id)
    if not existe:
        raise HTTPException(status_code=404, detail='Acompanhamento não encontrado')
    return {'success': True, 'message': 'Acompanhamento excluído com sucesso'}



@app.get('/api/coordenacoes', response_model=list[Coordenacao])
async def get_coordenacoes():
    """GET /api/coordenacoes

    Retrieves a list of all coordination departments in the organization.

    Returns:
        list[dict]: List of coordination departments:
            - id (int): Coordination ID.
            - nome (str): Coordination name.
    """
    query = 'SELECT id, nome FROM coordenacao ORDER BY nome'
    resultado = await asyncio.to_thread(execute_query, query, fetch_all=True)
    return resultado or []


@app.get('/api/servicos', response_model=list[ServicosPorCoordenacao])
async def get_servicos():
    """GET /api/servicos

    Retrieves all services offered in the catalog, grouped under their
    respective parent coordination department.

    Returns:
        list[dict]: Services grouped by coordination department.
    """
    query = '''
    SELECT s.id, s.nome, s.sigla,
           c.id as coordenacao_id, c.nome as coordenacao_nome, c.sigla as coordenacao_sigla
    FROM servico s
    JOIN coordenacao c ON c.id = s.coordenacao_id
    ORDER BY c.nome, s.nome
    '''
    resultado = await asyncio.to_thread(execute_query, query, fetch_all=True)
    if not resultado:
        return []
    grupos = {}
    for r in resultado:
        cid = r['coordenacao_id']
        if cid not in grupos:
            grupos[cid] = {
                'coordenacao_id': cid,
                'coordenacao_nome': r['coordenacao_nome'],
                'coordenacao_sigla': r['coordenacao_sigla'],
                'servicos': []
            }
        grupos[cid]['servicos'].append({
            'id': r['id'],
            'nome': r['nome'],
            'sigla': r['sigla']
        })
    return list(grupos.values())



@app.get('/api/membros', response_model=list[Membro])
async def get_membros():
    """GET /api/membros

    Retrieves a list of active team members who hold project manager roles.

    Returns:
        list[dict]: List of project managers:
            - id (int): Member ID.
            - nome (str): Manager name.
            - email (str): Manager email.
    """
    query = '''
    SELECT DISTINCT m.id, m.nome, m.email
    FROM membro m
    JOIN membro_projeto mp ON mp.membro_id = m.id
    JOIN cargo c ON c.id = mp.cargo_id
    WHERE mp.data_saida IS NULL
      AND LOWER(c.nome) LIKE '%gerente%'
    ORDER BY m.nome
    '''
    resultado = await asyncio.to_thread(execute_query, query, fetch_all=True)
    return resultado or []


@app.get('/api/membros-por-coordenacao', response_model=list[MembrosPorCoordenacao])
async def get_membros_por_coordenacao():
    """GET /api/membros-por-coordenacao

    Retrieves all members grouped under their respective coordination departments.
    Adds a fallback department group (id=0) for members without department assignments.

    Returns:
        list[dict]: Members grouped by coordination department.
    """
    query = '''
    SELECT m.id, m.nome, m.email,
           c.id as coordenacao_id, c.nome as coordenacao_nome, c.sigla as coordenacao_sigla
    FROM membro m
    LEFT JOIN membro_coordenacao mc ON mc.membro_id = m.id
    LEFT JOIN coordenacao c ON c.id = mc.coordenacao_id
    ORDER BY c.nome, m.nome
    '''
    resultado = await asyncio.to_thread(execute_query, query, fetch_all=True)
    grupos = {}
    
    # Grupo inicial para membros sem coordenação cadastrada
    grupos[0] = {
        'coordenacao_id': 0,
        'coordenacao_nome': 'Outros Departamentos / Presidência',
        'coordenacao_sigla': 'OUTROS',
        'membros': []
    }
    
    for r in resultado:
        membro_data = {'id': r['id'], 'nome': r['nome'], 'email': r['email']}
        if r['coordenacao_id'] is not None:
            cid = r['coordenacao_id']
            if cid not in grupos:
                grupos[cid] = {
                    'coordenacao_id': cid,
                    'coordenacao_nome': r['coordenacao_nome'],
                    'coordenacao_sigla': r['coordenacao_sigla'],
                    'membros': []
                }
            if membro_data not in grupos[cid]['membros']:
                grupos[cid]['membros'].append(membro_data)
        else:
            if membro_data not in grupos[0]['membros']:
                grupos[0]['membros'].append(membro_data)
                
    if not grupos[0]['membros']:
        del grupos[0]
        
    return list(grupos.values())



async def send_to_n8n(data: dict):
    """Asynchronously dispatches form submission payloads to an external n8n webhook.

    Args:
        data (dict): Payload containing form submission details.
    """
    try:
        async with httpx.AsyncClient() as client:
            await client.post(N8N_WEBHOOK_URL, json=data, timeout=30.0)
    except Exception:
        logger.exception('Erro ao enviar para n8n')


def _submit_pape_tx(data: PapeFormData) -> int:
    """Inserts PAPE monitoring form submission details atomically within a transaction.

    Handles creation of the primary `acompanhamento_projeto` record, and inserts into
    sub-tables like `acomp_orientador` (if the project has a technical advisor),
    `acomp_sprint` (if using Agile methodology), and `acomp_impedimento` (if sprint
    impediments occurred).

    Args:
        data (PapeFormData): validated PAPE form submission model.

    Returns:
        int: The database auto-increment ID (acomp_id) of the inserted monitoring record.
    """
    motivos_str = json.dumps(data.motivos_atraso) if data.motivos_atraso else None
    orcamento_nao_necessario = 1 if data.suficiencia_orcamento == 'Não necessitou' else 0
    suficiencia_nota = (
        int(data.suficiencia_orcamento)
        if data.suficiencia_orcamento and data.suficiencia_orcamento != 'Não necessitou'
        else None
    )
    dados_iniciais = {
        'descricao_projeto': data.descricao_projeto, 'data_inicio': data.data_inicio,
        'numero_contrato': data.numero_contrato, 'valor_projeto': data.valor_projeto,
        'servicos_projeto': data.servicos_projeto, 'coordenacoes': data.coordenacoes,
    }
    dados_iniciais_str = json.dumps(dados_iniciais) if any(dados_iniciais.values()) else None

    with transaction() as conn:
        cur = conn.cursor(dictionary=True)
        # contrato_id é opcional: NULL quando o projeto não tem contrato
        cur.execute(
            'SELECT id AS contrato_id FROM contrato WHERE projeto_externo_id = %s LIMIT 1',
            (data.projeto_externo_id,),
        )
        row = cur.fetchone()
        contrato_id = row['contrato_id'] if row else None

        cur.execute(
            '''INSERT INTO acompanhamento_projeto (
                projeto_externo_id, contrato_id, data_resposta, modelo_gerenciamento,
                pct_conclusao, status_cronograma, motivos_atraso,
                capacitacao_equipe, eficacia_metodologia, nivel_retrabalho,
                comunicacao_cliente, orcamento_nao_necessario,
                primeira_resposta, cliente_percebeu_valor, pct_marcos_prazo,
                variacao_escopo, impacto_cliente, abertura_cliente,
                satisfacao_cliente, suficiencia_orcamento_nota, dados_iniciais_adicionais
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (
                data.projeto_externo_id, contrato_id, datetime.now().date(), data.modelo_gerenciamento,
                data.pct_conclusao, data.status_cronograma, motivos_str,
                data.capacitacao_equipe, data.eficacia_metodologia, data.nivel_retrabalho,
                data.comunicacao_cliente, orcamento_nao_necessario,
                1 if data.primeira_resposta == 'Sim' else 0, data.cliente_percebeu_valor, data.pct_marcos_prazo,
                data.variacao_escopo, data.impacto_cliente, data.abertura_cliente,
                data.satisfacao_cliente, suficiencia_nota, dados_iniciais_str,
            ),
        )
        acomp_id = cur.lastrowid
        if data.possui_orientador == 'Sim':
            cur.execute(
                '''INSERT INTO acomp_orientador (acompanhamento_id, possui_orientador, nome_orientador,
                       efetividade_orientador, disponibilidade_orientador) VALUES (%s, 1, %s, %s, %s)''',
                (acomp_id, data.nome_orientador or 'Sem nome', data.efetividade_orientador, data.disponibilidade_orientador),
            )
        if data.modelo_gerenciamento == 'Ágil' and data.pct_story_points:
            cur.execute(
                'INSERT INTO acomp_sprint (acompanhamento_id, pct_story_points) VALUES (%s, %s)',
                (acomp_id, data.pct_story_points),
            )
            if data.houve_impedimentos == 'Sim' and data.tipos_impedimentos:
                for imp in data.tipos_impedimentos:
                    cur.execute(
                        'INSERT INTO acomp_impedimento (acompanhamento_id, houve_impedimentos, tipo_impedimento) VALUES (%s, 1, %s)',
                        (acomp_id, imp),
                    )
        return acomp_id


@app.post('/api/pape')
async def submit_pape(data: PapeFormData, background_tasks: BackgroundTasks):
    """POST /api/pape

    Handles new project monitoring responses from project managers.
    Validates that the respondent is indeed the active project manager. Inserts
    monitoring records atomically, updates the project's advisor info if unset,
    and schedules background webhook dispatch tasks to n8n.

    Args:
        data (PapeFormData): The validated form submission schema.
        background_tasks (BackgroundTasks): FastAPI background task manager.

    Returns:
        dict: E.g. {'success': True, 'message': '...', 'acompanhamento_id': int}
    """
    is_project_manager = await validate_project_manager(
        data.respondente_nome,
        data.projeto_externo_id,
    )
    if not is_project_manager:
        raise HTTPException(
            status_code=400,
            detail='Este projeto não está vinculado à gerente selecionada',
        )

    acomp_id = await asyncio.to_thread(_submit_pape_tx, data)

    await update_project_orientador_if_unknown(
        data.projeto_externo_id,
        data.possui_orientador,
        data.nome_orientador,
    )

    n8n_payload = {
        'acompanhamento_id': acomp_id,
        'data_resposta': datetime.now().isoformat(),
        **data.model_dump(),
    }
    background_tasks.add_task(send_to_n8n, n8n_payload)

    return {
        'success': True,
        'message': 'Formulário enviado com sucesso',
        'acompanhamento_id': acomp_id,
    }


@app.get('/api/dashboard/pape')
async def get_dashboard_pape(
    projeto_id: int | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None
):
    """GET /api/dashboard/pape

    Retrieves aggregated project metrics for the PAPE dashboard.
    Fetches satisfaction metrics, project schedule status counts, completion ranges,
    delay reasons, agile sprint progress, client relationship indices, technical advisor
    effectiveness, and historical details. Can be filtered by date range and selected project.

    Args:
        projeto_id (int | None): ID of the project to focus on in detailed breakdown. Defaults to None.
        data_inicio (str | None): Filter start date in YYYY-MM-DD format. Defaults to None.
        data_fim (str | None): Filter end date in YYYY-MM-DD format. Defaults to None.

    Returns:
        dict: Aggregated dashboard analytics:
            - total_projetos (int): Count of distinct active projects.
            - total_respostas (int): Count of total monitoring submissions in the period.
            - media_satisfacao (float): Average client satisfaction score.
            - metodologias (dict): Count of projects by management model.
            - status_cronograma (dict): Count of projects by schedule status.
            - pct_conclusao (dict): Count of projects by completion range.
            - motivos_atraso (list): Sorted counts of delay reasons.
            - projetos_atuais (list): List of active projects with latest status.
            - riscos (dict): Aggregated risk indicators.
            - metodo_escopo (dict): Scope and methodology metrics.
            - cliente_orientacao (dict): Client relation and technical advisor metrics.
            - agil (dict): Agile project metrics.
            - detalhe (dict): Focus project detailed metrics.
            - datas_disponiveis (list): List of dates with monitoring responses in descending order.
    """
    try:
        sub_params = []
        sub_date_filters = ""
        if data_inicio:
            sub_date_filters += " AND ap2.data_resposta >= %s"
            sub_params.append(data_inicio)
        if data_fim:
            sub_date_filters += " AND ap2.data_resposta <= %s"
            sub_params.append(data_fim)

        outer_params = []
        outer_date_filters = ""
        if data_inicio:
            outer_date_filters += " AND ap.data_resposta >= %s"
            outer_params.append(data_inicio)
        if data_fim:
            outer_date_filters += " AND ap.data_resposta <= %s"
            outer_params.append(data_fim)

        latest_filter = f'''
        NOT EXISTS (
            SELECT 1
            FROM acompanhamento_projeto ap2
            WHERE ap2.projeto_externo_id = ap.projeto_externo_id
              {sub_date_filters}
              AND (
                ap2.data_resposta > ap.data_resposta
                OR (ap2.data_resposta = ap.data_resposta AND ap2.id > ap.id)
              )
        )
        '''

        total_respostas_query = f'SELECT COUNT(*) as total FROM acompanhamento_projeto ap WHERE 1=1 {outer_date_filters}'
        total_projetos_query = f'''
        SELECT COUNT(*) as total
        FROM acompanhamento_projeto ap
        WHERE {latest_filter} {outer_date_filters}
        '''
        sat_query = f'''
        SELECT AVG(ap.satisfacao_cliente) as media
        FROM acompanhamento_projeto ap
        WHERE ap.satisfacao_cliente IS NOT NULL
          AND {latest_filter} {outer_date_filters}
        '''
        met_query = f'''
        SELECT ap.modelo_gerenciamento, COUNT(*) as quantidade
        FROM acompanhamento_projeto ap
        WHERE {latest_filter} {outer_date_filters}
        GROUP BY ap.modelo_gerenciamento
        '''
        cron_query = f'''
        SELECT ap.status_cronograma, COUNT(*) as quantidade
        FROM acompanhamento_projeto ap
        WHERE {latest_filter} {outer_date_filters}
        GROUP BY ap.status_cronograma
        '''
        conclusao_query = f'''
        SELECT ap.pct_conclusao, COUNT(*) as quantidade
        FROM acompanhamento_projeto ap
        WHERE {latest_filter} {outer_date_filters}
        GROUP BY ap.pct_conclusao
        ORDER BY FIELD(ap.pct_conclusao, '0-20%', '21-40%', '41-60%', '61-80%', '81-100%')
        '''
        motivos_query = f'''
        SELECT ap.motivos_atraso
        FROM acompanhamento_projeto ap
        WHERE {latest_filter}
          AND ap.status_cronograma IN ('Com risco de atraso', 'Atrasado')
          AND ap.motivos_atraso IS NOT NULL {outer_date_filters}
        '''
        projetos_query = f'''
        SELECT
            ap.projeto_externo_id as id,
            pe.nome as projeto,
            ap.status_cronograma,
            ap.pct_conclusao,
            ap.modelo_gerenciamento,
            ap.data_resposta,
            ap.satisfacao_cliente,
            ap.impacto_cliente,
            COALESCE((
                SELECT GROUP_CONCAT(DISTINCT m.nome ORDER BY m.nome SEPARATOR ', ')
                FROM membro_projeto mp
                JOIN membro m ON m.id = mp.membro_id
                JOIN cargo cg ON cg.id = mp.cargo_id
                WHERE mp.projeto_externo_id = pe.id
                  AND mp.data_saida IS NULL
                  AND LOWER(cg.nome) LIKE '%gerente%'
            ), 'Sem gerente') as gerente,
            COALESCE((
                SELECT GROUP_CONCAT(DISTINCT co.nome ORDER BY co.nome SEPARATOR ', ')
                FROM membro_projeto mp
                JOIN coordenacao co ON co.id = mp.coordenacao_id
                WHERE mp.projeto_externo_id = pe.id
                  AND mp.data_saida IS NULL
            ), 'Sem coordenação') as coordenacao
        FROM acompanhamento_projeto ap
        JOIN projeto_externo pe ON pe.id = ap.projeto_externo_id
        WHERE {latest_filter} {outer_date_filters}
        ORDER BY
            FIELD(ap.status_cronograma, 'Atrasado', 'Com risco de atraso', 'Dentro do prazo', 'Concluido'),
            ap.data_resposta DESC,
            pe.nome
        LIMIT 12
        '''
        riscos_query = f'''
        SELECT
            pe.nome as projeto,
            ap.status_cronograma,
            ap.motivos_atraso,
            ap.comunicacao_cliente,
            ap.capacitacao_equipe,
            COALESCE(ap.suficiencia_orcamento_nota, ap.suficiencia_orcamento) as suficiencia_orcamento,
            COALESCE((
                SELECT GROUP_CONCAT(DISTINCT co.nome ORDER BY co.nome SEPARATOR ', ')
                FROM membro_projeto mp
                JOIN coordenacao co ON co.id = mp.coordenacao_id
                WHERE mp.projeto_externo_id = pe.id
                  AND mp.data_saida IS NULL
            ), 'Sem coordenação') as coordenacao
        FROM acompanhamento_projeto ap
        JOIN projeto_externo pe ON pe.id = ap.projeto_externo_id
        WHERE {latest_filter} {outer_date_filters}
        ORDER BY
            FIELD(ap.status_cronograma, 'Atrasado', 'Com risco de atraso', 'Dentro do prazo', 'Concluido'),
            pe.nome
        '''
        metodo_escopo_query = f'''
        SELECT
            pe.nome as projeto,
            ap.modelo_gerenciamento,
            ap.nivel_retrabalho,
            ap.variacao_escopo,
            ap.capacitacao_equipe,
            ap.eficacia_metodologia
        FROM acompanhamento_projeto ap
        JOIN projeto_externo pe ON pe.id = ap.projeto_externo_id
        WHERE {latest_filter} {outer_date_filters}
        ORDER BY pe.nome
        '''
        cliente_orientacao_query = f'''
        SELECT
            pe.nome as projeto,
            ap.comunicacao_cliente,
            ap.abertura_cliente,
            ap.satisfacao_cliente,
            ap.cliente_percebeu_valor,
            ap.impacto_cliente,
            COALESCE(ao.possui_orientador, pe.possui_orientador, 0) as possui_orientador,
            COALESCE(ao.nome_orientador, pe.nome_orientador) as nome_orientador,
            ao.efetividade_orientador,
            ao.disponibilidade_orientador
        FROM acompanhamento_projeto ap
        JOIN projeto_externo pe ON pe.id = ap.projeto_externo_id
        LEFT JOIN acomp_orientador ao ON ao.acompanhamento_id = ap.id
        WHERE {latest_filter} {outer_date_filters}
        ORDER BY pe.nome
        '''
        agil_query = f'''
        SELECT
            pe.nome as projeto,
            ap.data_resposta,
            ap.impacto_cliente,
            acs.pct_story_points,
            COALESCE(imp.impedimentos, '') as impedimentos,
            JSON_UNQUOTE(JSON_EXTRACT(ap.dados_iniciais_adicionais, '$.intervencao_pmo')) as intervencao_pmo,
            JSON_UNQUOTE(JSON_EXTRACT(ap.dados_iniciais_adicionais, '$.solicitou_1_1')) as one_on_one_pmo,
            COALESCE((
                SELECT GROUP_CONCAT(DISTINCT m.nome ORDER BY m.nome SEPARATOR ', ')
                FROM membro_projeto mp
                JOIN membro m ON m.id = mp.membro_id
                JOIN cargo cg ON cg.id = mp.cargo_id
                WHERE mp.projeto_externo_id = pe.id
                  AND mp.data_saida IS NULL
                  AND LOWER(cg.nome) LIKE '%gerente%'
            ), 'Sem gerente') as gerente
        FROM acompanhamento_projeto ap
        JOIN projeto_externo pe ON pe.id = ap.projeto_externo_id
        LEFT JOIN acomp_sprint acs ON acs.acompanhamento_id = ap.id
        LEFT JOIN (
            SELECT acompanhamento_id, GROUP_CONCAT(tipo_impedimento ORDER BY tipo_impedimento SEPARATOR ', ') as impedimentos
            FROM acomp_impedimento
            GROUP BY acompanhamento_id
        ) imp ON imp.acompanhamento_id = ap.id
        WHERE {latest_filter} {outer_date_filters}
          AND (
            ap.modelo_gerenciamento IN ('Ágil', 'Agil')
            OR acs.pct_story_points IS NOT NULL
          )
        ORDER BY ap.data_resposta DESC, pe.nome
        '''
        detalhe_query = f'''
        SELECT
            ap.id,
            ap.projeto_externo_id as projeto_id,
            pe.nome as projeto,
            ap.data_resposta,
            ap.status_cronograma,
            ap.pct_conclusao,
            ap.impacto_cliente,
            ap.motivos_atraso,
            ap.comunicacao_cliente,
            ap.abertura_cliente,
            ap.eficacia_metodologia,
            ap.capacitacao_equipe,
            ap.nivel_retrabalho,
            COALESCE(ap.suficiencia_orcamento_nota, ap.suficiencia_orcamento) as suficiencia_orcamento,
            JSON_UNQUOTE(JSON_EXTRACT(ap.dados_iniciais_adicionais, '$.intervencao_pmo')) as intervencao_pmo,
            JSON_UNQUOTE(JSON_EXTRACT(ap.dados_iniciais_adicionais, '$.solicitou_1_1')) as one_on_one_pmo,
            COALESCE((
                SELECT GROUP_CONCAT(DISTINCT m.nome ORDER BY m.nome SEPARATOR ', ')
                FROM membro_projeto mp
                JOIN membro m ON m.id = mp.membro_id
                JOIN cargo cg ON cg.id = mp.cargo_id
                WHERE mp.projeto_externo_id = pe.id
                  AND mp.data_saida IS NULL
                  AND LOWER(cg.nome) LIKE '%gerente%'
            ), 'Sem gerente') as gerente
        FROM acompanhamento_projeto ap
        JOIN projeto_externo pe ON pe.id = ap.projeto_externo_id
        WHERE 1=1 {outer_date_filters}
        ORDER BY pe.nome, ap.data_resposta, ap.id
        '''

        total_respostas_result = await asyncio.to_thread(
            execute_query, total_respostas_query, tuple(outer_params) if outer_params else None, fetch_one=True
        )
        total_projetos_result = await asyncio.to_thread(
            execute_query, total_projetos_query, tuple(sub_params + outer_params) if (sub_params or outer_params) else None, fetch_one=True
        )
        sat_result = await asyncio.to_thread(
            execute_query, sat_query, tuple(sub_params + outer_params) if (sub_params or outer_params) else None, fetch_one=True
        )
        met_result = await asyncio.to_thread(
            execute_query, met_query, tuple(sub_params + outer_params) if (sub_params or outer_params) else None, fetch_all=True
        )
        cron_result = await asyncio.to_thread(
            execute_query, cron_query, tuple(sub_params + outer_params) if (sub_params or outer_params) else None, fetch_all=True
        )
        conclusao_result = await asyncio.to_thread(
            execute_query, conclusao_query, tuple(sub_params + outer_params) if (sub_params or outer_params) else None, fetch_all=True
        )
        motivos_rows = await asyncio.to_thread(
            execute_query, motivos_query, tuple(sub_params + outer_params) if (sub_params or outer_params) else None, fetch_all=True
        )
        projetos_atuais = await asyncio.to_thread(
            execute_query, projetos_query, tuple(sub_params + outer_params) if (sub_params or outer_params) else None, fetch_all=True
        )
        riscos_rows = await asyncio.to_thread(
            execute_query, riscos_query, tuple(sub_params + outer_params) if (sub_params or outer_params) else None, fetch_all=True
        )
        metodo_escopo_rows = await asyncio.to_thread(
            execute_query, metodo_escopo_query, tuple(sub_params + outer_params) if (sub_params or outer_params) else None, fetch_all=True
        )
        cliente_orientacao_rows = await asyncio.to_thread(
            execute_query, cliente_orientacao_query, tuple(sub_params + outer_params) if (sub_params or outer_params) else None, fetch_all=True
        )
        agil_rows = await asyncio.to_thread(
            execute_query, agil_query, tuple(sub_params + outer_params) if (sub_params or outer_params) else None, fetch_all=True
        )
        detalhe_rows = await asyncio.to_thread(
            execute_query, detalhe_query, tuple(outer_params) if outer_params else None, fetch_all=True
        )
        datas_disponiveis_query = 'SELECT DISTINCT data_resposta FROM acompanhamento_projeto ORDER BY data_resposta DESC'
        datas_disponiveis_result = await asyncio.to_thread(
            execute_query, datas_disponiveis_query, fetch_all=True
        )

        total_respostas = total_respostas_result['total'] if total_respostas_result else 0
        total_projetos = total_projetos_result['total'] if total_projetos_result else 0
        media_satisfacao = round(sat_result['media'], 1) if sat_result and sat_result['media'] else 0
        metodologias = {row['modelo_gerenciamento']: row['quantidade'] for row in met_result} if met_result else {}
        cronograma = {row['status_cronograma']: row['quantidade'] for row in cron_result} if cron_result else {}
        conclusao = {row['pct_conclusao']: row['quantidade'] for row in conclusao_result} if conclusao_result else {}
        datas_disponiveis = [
            str(row['data_resposta'])
            for row in datas_disponiveis_result
            if row.get('data_resposta')
        ] if datas_disponiveis_result else []

        return {
            'total_projetos': total_projetos,
            'total_respostas': total_respostas,
            'media_satisfacao': media_satisfacao,
            'metodologias': metodologias,
            'status_cronograma': cronograma,
            'pct_conclusao': conclusao,
            'motivos_atraso': count_motivos_atraso(motivos_rows or []),
            'projetos_atuais': projetos_atuais or [],
            'riscos': build_riscos_dashboard(riscos_rows or []),
            'metodo_escopo': build_metodo_escopo_dashboard(metodo_escopo_rows or []),
            'cliente_orientacao': build_cliente_orientacao_dashboard(cliente_orientacao_rows or []),
            'agil': build_agil_dashboard(agil_rows or []),
            'detalhe': build_detalhe_dashboard(detalhe_rows or [], projeto_id),
            'datas_disponiveis': datas_disponiveis,
        }
    except Exception:
        raise


def parse_valor_projeto(valor_str: str | None) -> float:
    """Converts a Brazilian formatted currency string ('1.000,00') to float.

    Args:
        valor_str (str | None): Brazilian-formatted currency string.

    Returns:
        float: Parsed numeric value.
    """
    if not valor_str:
        return 0.0
    try:
        return float(valor_str.replace('.', '').replace(',', '.'))
    except (ValueError, AttributeError):
        return 0.0


async def get_cargo_consultor_do_membro(membro_id: int) -> int:
    """Retrieves the project consultant cargo ID (10 or 11) for a member.

    Queries `membro_cargo` for cargo ID 10 (Consultor de Projetos) or 11.
    Defaults to 10 if none is found.

    Args:
        membro_id (int): Database ID of the member.

    Returns:
        int: Cargo ID.
    """
    result = await asyncio.to_thread(
        execute_query,
        'SELECT cargo_id FROM membro_cargo WHERE membro_id = %s AND cargo_id IN (10, 11) LIMIT 1',
        (membro_id,),
        fetch_one=True,
    )
    return result['cargo_id'] if result else 10


async def get_coordenacao_do_membro(membro_id: int) -> int | None:
    """Retrieves the primary department coordination ID for a member.

    Args:
        membro_id (int): Database ID of the member.

    Returns:
        int | None: Department coordination ID, or None if not assigned.
    """
    result = await asyncio.to_thread(
        execute_query,
        'SELECT coordenacao_id FROM membro_coordenacao WHERE membro_id = %s LIMIT 1',
        (membro_id,),
        fetch_one=True,
    )
    return result['coordenacao_id'] if result else None


async def get_cliente_placeholder() -> int:
    """Retrieves or creates a fallback client object when a project is created without one.

    Ensures that temporary projects or forms have a valid client reference.
    When a contract is synced later from Pipefy, it gets swapped for the actual client.

    Returns:
        int: Database ID of the placeholder client.
    """
    row = await asyncio.to_thread(
        execute_query,
        'SELECT id FROM cliente WHERE nome = %s LIMIT 1',
        ('Cliente não informado',),
        fetch_one=True,
    )
    if row:
        return row['id']
    novo = await asyncio.to_thread(
        execute_insert,
        'INSERT INTO cliente (nome) VALUES (%s)',
        ('Cliente não informado',),
    )
    if not novo:
        raise Exception('Falha ao criar client placeholder')
    return novo


@app.post('/api/projetos')
async def create_projeto(data: ProjetoCreate, _auth: None = Depends(require_admin_token)):
    """POST /api/projetos

    Creates a new project record and links its relations.
    Requires header admin token authentication.
    Validates that the contract number is globally unique before saving.
    Inserts a new `projeto_externo` record and then initiates relationship mappings
    for contracts, services, consultores, and managers.

    Args:
        data (ProjetoCreate): The project creation request body.
        _auth (None): Depends on require_admin_token dependency.

    Returns:
        dict: E.g. {'success': True, 'projeto_id': int}
    """
    try:
        # Validar número de contrato antes de qualquer INSERT
        if data.numero_contrato and data.numero_contrato.strip():
            existing = await asyncio.to_thread(
                execute_query,
                'SELECT id FROM contrato WHERE numero = %s LIMIT 1',
                (data.numero_contrato.strip(),),
                fetch_one=True,
            )
            if existing:
                raise HTTPException(
                    status_code=400,
                    detail=f'Número de contrato "{data.numero_contrato.strip()}" já está cadastrado. Use um número diferente.',
                )

        # 1. Criar projeto_externo
        possui_orientador_value = 1 if data.possui_orientador == 'Sim' else 0
        nome_orientador_value = data.nome_orientador if possui_orientador_value else None
        data_inicio = data.data_inicio or None

        projeto_id = await asyncio.to_thread(
            execute_insert,
            '''INSERT INTO projeto_externo (nome, descricao_projeto, data_inicio, possui_orientador, nome_orientador)
               VALUES (%s, %s, %s, %s, %s)''',
            (data.nome_projeto, data.descricao_projeto, data_inicio, possui_orientador_value, nome_orientador_value),
        )

        if not projeto_id:
            raise Exception('Falha ao criar projeto_externo')

        try:
            await _create_projeto_relations(projeto_id, data, data_inicio)
        except Exception:
            # Desfaz o projeto para evitar registro órfão
            await asyncio.to_thread(
                execute_query,
                'DELETE FROM projeto_externo WHERE id = %s',
                (projeto_id,),
            )
            raise

        return {'success': True, 'projeto_id': projeto_id}
    except Exception:
        raise


async def _create_projeto_relations(projeto_id: int, data: ProjetoCreate, data_inicio: str | None) -> None:
    """Helper function to insert related contract, service, and member details for a new project.

    Args:
        projeto_id (int): Database ID of the newly created project.
        data (ProjetoCreate): The project creation request payload.
        data_inicio (str | None): Start date of the project.
    """
    # 2. Criar contrato com cliente placeholder (o sync do Pipefy completa depois)
    cliente_id = await get_cliente_placeholder()
    numero = data.numero_contrato.strip() if data.numero_contrato else f'CONTRATO-TEMP-{projeto_id}'
    valor = parse_valor_projeto(data.valor_projeto)
    await asyncio.to_thread(
        execute_insert,
        'INSERT INTO contrato (cliente_id, projeto_externo_id, numero, valor_total) VALUES (%s, %s, %s, %s)',
        (cliente_id, projeto_id, numero, valor),
    )

    # 3. Vincular serviços
    for servico_id in (data.servicos_projeto or []):
        await asyncio.to_thread(
            execute_query,
            'INSERT IGNORE INTO projeto_servico (projeto_externo_id, servico_id) VALUES (%s, %s)',
            (projeto_id, servico_id),
        )

    # 4. Vincular consultores — cargo vem de membro_cargo (10 ou 11), default 10
    for chave in (data.membros_projeto or []):
        partes = chave.split('-')
        if len(partes) != 2:
            continue
        try:
            membro_id = int(partes[0])
            coordenacao_id = int(partes[1])
        except ValueError:
            continue
        # coordenacao_id=0 é o placeholder para "Outros Departamentos" — busca a real
        if coordenacao_id == 0:
            coordenacao_id = await get_coordenacao_do_membro(membro_id)
            if coordenacao_id is None:
                continue
        cargo_id = await get_cargo_consultor_do_membro(membro_id)
        await asyncio.to_thread(
            execute_query,
            '''INSERT INTO membro_projeto (membro_id, projeto_externo_id, coordenacao_id, cargo_id, data_entrada)
               VALUES (%s, %s, %s, %s, %s)''',
            (membro_id, projeto_id, coordenacao_id, cargo_id, data_inicio),
        )

    # 5. Vincular gerente — cargo_id 31 (Gerente de Projeto)
    if data.gerente_projeto:
        gerente = await asyncio.to_thread(
            execute_query,
            'SELECT id FROM membro WHERE nome = %s LIMIT 1',
            (data.gerente_projeto,),
            fetch_one=True,
        )
        if gerente:
            coordenacao_id = await get_coordenacao_do_membro(gerente['id'])
            if coordenacao_id:
                await asyncio.to_thread(
                    execute_query,
                    '''INSERT INTO membro_projeto (membro_id, projeto_externo_id, coordenacao_id, cargo_id, data_entrada)
                       VALUES (%s, %s, %s, %s, %s)''',
                    (gerente['id'], projeto_id, coordenacao_id, 31, data_inicio),
                )


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='0.0.0.0', port=8000)
