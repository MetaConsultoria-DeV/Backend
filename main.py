from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import asyncio
import httpx
import json
from models import Projeto, Coordenacao, Membro, PapeFormData
from database import execute_query, execute_insert
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title='PAPE API', version='1.0.0')

ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000').split(',')

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=['*'],
    allow_headers=['*'],
)

N8N_WEBHOOK_URL = os.getenv('N8N_WEBHOOK_URL', 'http://localhost:5678/webhook/pape')


@app.get('/api/health')
async def health():
    return {'status': 'ok'}


@app.get('/api/projetos', response_model=list[Projeto])
async def get_projetos(gerente_id: int | None = None):
    manager_filter = ''
    params = None
    if gerente_id is not None:
        manager_filter = '''
      AND EXISTS (
        SELECT 1
        FROM membro_projeto mp
        JOIN cargo cg ON cg.id = mp.cargo_id
        WHERE mp.projeto_externo_id = pe.id
          AND mp.membro_id = %s
          AND mp.data_saida IS NULL
          AND LOWER(cg.nome) LIKE '%gerente%'
          AND LOWER(cg.nome) LIKE '%projeto%'
      )
        '''
        params = (gerente_id,)

    query = '''
    SELECT pe.id, pe.nome, c.numero as numero_contrato, c.valor_total,
           pe.possui_orientador, pe.nome_orientador
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
    try:
        if params:
            resultado = await asyncio.to_thread(execute_query, query, params, fetch_all=True)
        else:
            resultado = await asyncio.to_thread(execute_query, query, fetch_all=True)
        return resultado or []
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def validate_project_manager(respondente_nome: str, projeto_externo_id: int) -> bool:
    query = '''
    SELECT mp.id
    FROM membro_projeto mp
    JOIN membro m ON m.id = mp.membro_id
    JOIN cargo c ON c.id = mp.cargo_id
    WHERE mp.projeto_externo_id = %s
      AND m.nome = %s
      AND mp.data_saida IS NULL
      AND LOWER(c.nome) LIKE '%gerente%'
      AND LOWER(c.nome) LIKE '%projeto%'
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
            
            # Map variations to canonical reasons
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
    counts: dict[str, int] = {}

    for row in rows:
        for motivo_label in parse_motivos_atraso(row.get('motivos_atraso')):
            counts[motivo_label] = counts.get(motivo_label, 0) + 1

    return [
        {'name': name, 'value': value}
        for name, value in sorted(counts.items(), key=lambda item: item[1], reverse=True)
    ]


def build_riscos_dashboard(rows: list[dict]) -> dict:
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

    # Initialize the grid with 0 for all canonical reasons and canonical coordinations
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
                # If there's an unknown motive (like 'Outro'), skip it or add it dynamically
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
    # Pre-ordered keys: canonical first
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
    if not items:
        return 0

    return round(sum(item['value'] for item in items) / len(items), 1)


def has_orientador(row: dict) -> bool:
    raw_value = row.get('possui_orientador')
    orientador = row.get('nome_orientador')

    if isinstance(raw_value, str):
        has_flag = raw_value.strip().lower() in ('1', 'sim', 'true')
    else:
        has_flag = bool(raw_value)

    return has_flag or bool(orientador)


def build_cliente_orientacao_dashboard(rows: list[dict]) -> dict:
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
    if not raw_value:
        return []

    if isinstance(raw_value, list):
        return [str(item).strip() for item in raw_value if str(item).strip()]

    return [item.strip() for item in str(raw_value).split(',') if item.strip()]


def normalize_yes(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'sim', 'true', 'yes')

    return bool(value)


def story_points_midpoint(value: str | None) -> int | None:
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
    if not value:
        return 'Sem data'

    if hasattr(value, 'strftime'):
        return value.strftime('%d/%m/%Y')

    try:
        return datetime.fromisoformat(str(value)).strftime('%d/%m/%Y')
    except ValueError:
        return str(value)


def build_detalhe_dashboard(rows: list[dict], selected_project_id: int | None = None) -> dict:
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
    query = '''
    SELECT pe.id, pe.nome, pe.data_inicio, c.numero as numero_contrato,
           c.valor_total, pe.possui_orientador, pe.nome_orientador
    FROM projeto_externo pe
    LEFT JOIN contrato c ON c.projeto_externo_id = pe.id
    WHERE pe.id = %s
    '''
    try:
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
        servicos, coordenacoes = await asyncio.gather(
            asyncio.to_thread(execute_query, servicos_query, (projeto_id,), fetch_all=True),
            asyncio.to_thread(execute_query, coordenacoes_query, (projeto_id,), fetch_all=True),
        )

        projeto['servicos'] = servicos or []
        projeto['coordenacoes'] = coordenacoes or []
        return projeto
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/api/coordenacoes', response_model=list[Coordenacao])
async def get_coordenacoes():
    query = 'SELECT id, nome FROM coordenacao ORDER BY nome'
    try:
        resultado = await asyncio.to_thread(execute_query, query, fetch_all=True)
        return resultado or []
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/api/membros', response_model=list[Membro])
async def get_membros():
    query = '''
    SELECT DISTINCT m.id, m.nome, m.email
    FROM membro m
    JOIN membro_cargo mc ON mc.membro_id = m.id
    JOIN cargo c ON c.id = mc.cargo_id
    WHERE LOWER(c.nome) LIKE '%gerente%'
      AND LOWER(c.nome) LIKE '%projeto%'
    ORDER BY m.nome
    '''
    try:
        resultado = await asyncio.to_thread(execute_query, query, fetch_all=True)
        return resultado or []
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def send_to_n8n(data: dict):
    try:
        async with httpx.AsyncClient() as client:
            await client.post(N8N_WEBHOOK_URL, json=data, timeout=30.0)
    except Exception as e:
        print(f'Erro ao enviar para n8n: {e}')


@app.post('/api/pape')
async def submit_pape(data: PapeFormData, background_tasks: BackgroundTasks):
    try:
        is_project_manager = await validate_project_manager(
            data.respondente_nome,
            data.projeto_externo_id,
        )
        if not is_project_manager:
            raise HTTPException(
                status_code=400,
                detail='Este projeto não está vinculado à gerente selecionada',
            )

        acomp_query = '''
        INSERT INTO acompanhamento_projeto (
            projeto_externo_id, contrato_id, data_resposta, modelo_gerenciamento,
            pct_conclusao, status_cronograma, motivos_atraso,
            capacitacao_equipe, eficacia_metodologia, nivel_retrabalho,
            comunicacao_cliente, orcamento_nao_necessario,
            primera_resposta, cliente_percebeu_valor, pct_marcos_prazo,
            variacao_escopo, impacto_cliente, abertura_cliente,
            satisfacao_cliente, suficiencia_orcamento_nota, dados_iniciais_adicionados
        )
        SELECT %s, c.id, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        FROM contrato c
        WHERE c.projeto_externo_id = %s
        LIMIT 1
        '''

        motivos_str = json.dumps(data.motivos_atraso) if data.motivos_atraso else None
        orcamento_nao_necessario = 1 if data.suficiencia_orcamento == 'Não necessitou' else 0
        suficiencia_nota = int(data.suficiencia_orcamento) if data.suficiencia_orcamento and data.suficiencia_orcamento != 'Não necessitou' else None
        
        dados_iniciais = {
            "data_inicio": data.data_inicio,
            "numero_contrato": data.numero_contrato,
            "valor_projeto": data.valor_projeto,
            "servicos_projeto": data.servicos_projeto,
            "coordenacoes": data.coordenacoes
        }
        dados_iniciais_str = json.dumps(dados_iniciais) if any(dados_iniciais.values()) else None

        acomp_id = await asyncio.to_thread(
            execute_insert,
            acomp_query,
            (
                data.projeto_externo_id,
                datetime.now().date(),
                data.modelo_gerenciamento,
                data.pct_conclusao,
                data.status_cronograma,
                motivos_str,
                data.capacitacao_equipe,
                data.eficacia_metodologia,
                data.nivel_retrabalho,
                data.comunicacao_cliente,
                orcamento_nao_necessario,
                1 if data.primeira_resposta == 'Sim' else 0,
                data.cliente_percebeu_valor,
                data.pct_marcos_prazo,
                data.variacao_escopo,
                data.impacto_cliente,
                data.abertura_cliente,
                data.satisfacao_cliente,
                suficiencia_nota,
                dados_iniciais_str,
                data.projeto_externo_id,
            ),
        )

        if not acomp_id:
            raise Exception('Nenhuma linha inserida em acompanhamento_projeto')

        await update_project_orientador_if_unknown(
            data.projeto_externo_id,
            data.possui_orientador,
            data.nome_orientador,
        )

        if data.possui_orientador == 'Sim':
            orient_query = '''
            INSERT INTO acomp_orientador (
                acompanhamento_id, possui_orientador, nome_orientador,
                efetividade_orientador, disponibilidade_orientador
            )
            VALUES (%s, 1, %s, %s, %s)
            '''
            await asyncio.to_thread(
                execute_query, orient_query, (
                    acomp_id, 
                    data.nome_orientador or 'Sem nome',
                    data.efetividade_orientador,
                    data.disponibilidade_orientador
                )
            )

        if data.modelo_gerenciamento == 'Ágil' and data.pct_story_points:
            sprint_query = '''
            INSERT INTO acomp_sprint (acompanhamento_id, pct_story_points)
            VALUES (%s, %s)
            '''
            await asyncio.to_thread(execute_query, sprint_query, (acomp_id, data.pct_story_points))

            if data.houve_impedimentos == 'Sim' and data.tipos_impedimentos:
                for impedimento in data.tipos_impedimentos:
                    imp_query = '''
                    INSERT INTO acomp_impedimento (acompanhamento_id, houve_impedimentos, tipo_impedimento)
                    VALUES (%s, 1, %s)
                    '''
                    await asyncio.to_thread(execute_query, imp_query, (acomp_id, impedimento))

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

    except HTTPException:
        raise
    except Exception as e:
        print(f'Erro ao submeter PAPE: {e}')
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/api/dashboard/pape')
async def get_dashboard_pape(
    projeto_id: int | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None
):
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
                  AND LOWER(cg.nome) LIKE '%projeto%'
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
            JSON_UNQUOTE(JSON_EXTRACT(ap.dados_iniciais_adicionados, '$.intervencao_pmo')) as intervencao_pmo,
            JSON_UNQUOTE(JSON_EXTRACT(ap.dados_iniciais_adicionados, '$.solicitou_1_1')) as one_on_one_pmo,
            COALESCE((
                SELECT GROUP_CONCAT(DISTINCT m.nome ORDER BY m.nome SEPARATOR ', ')
                FROM membro_projeto mp
                JOIN membro m ON m.id = mp.membro_id
                JOIN cargo cg ON cg.id = mp.cargo_id
                WHERE mp.projeto_externo_id = pe.id
                  AND mp.data_saida IS NULL
                  AND LOWER(cg.nome) LIKE '%gerente%'
                  AND LOWER(cg.nome) LIKE '%projeto%'
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
            JSON_UNQUOTE(JSON_EXTRACT(ap.dados_iniciais_adicionados, '$.intervencao_pmo')) as intervencao_pmo,
            JSON_UNQUOTE(JSON_EXTRACT(ap.dados_iniciais_adicionados, '$.solicitou_1_1')) as one_on_one_pmo,
            COALESCE((
                SELECT GROUP_CONCAT(DISTINCT m.nome ORDER BY m.nome SEPARATOR ', ')
                FROM membro_projeto mp
                JOIN membro m ON m.id = mp.membro_id
                JOIN cargo cg ON cg.id = mp.cargo_id
                WHERE mp.projeto_externo_id = pe.id
                  AND mp.data_saida IS NULL
                  AND LOWER(cg.nome) LIKE '%gerente%'
                  AND LOWER(cg.nome) LIKE '%projeto%'
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='0.0.0.0', port=8000)
