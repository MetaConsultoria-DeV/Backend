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

    return [str(motivo) for motivo in parsed_motivos if motivo]


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
    motivos_por_coordenacao: dict[str, dict[str, int]] = {}
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
                if motivo not in motivos_por_coordenacao:
                    motivos_por_coordenacao[motivo] = {}
                for coordenacao in coordenacoes or ['Sem coordenação']:
                    motivos_por_coordenacao[motivo][coordenacao] = (
                        motivos_por_coordenacao[motivo].get(coordenacao, 0) + 1
                    )

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
    for motivo, coordenacoes in motivos_por_coordenacao.items():
        total = sum(coordenacoes.values())
        matriz_motivos.append({
            'motivo': motivo,
            'total': total,
            'coordenacoes': dict(sorted(coordenacoes.items())),
        })

    return {
        'motivos_por_coordenacao': sorted(
            matriz_motivos,
            key=lambda item: item['total'],
            reverse=True,
        ),
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
            key=lambda item: item['nota'],
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
        'pontos_atencao': sorted(pontos_atencao, key=lambda item: item['nota']),
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
async def get_dashboard_pape():
    try:
        latest_filter = '''
        NOT EXISTS (
            SELECT 1
            FROM acompanhamento_projeto ap2
            WHERE ap2.projeto_externo_id = ap.projeto_externo_id
              AND (
                ap2.data_resposta > ap.data_resposta
                OR (ap2.data_resposta = ap.data_resposta AND ap2.id > ap.id)
              )
        )
        '''

        total_respostas_query = 'SELECT COUNT(*) as total FROM acompanhamento_projeto'
        total_projetos_query = f'''
        SELECT COUNT(*) as total
        FROM acompanhamento_projeto ap
        WHERE {latest_filter}
        '''
        sat_query = f'''
        SELECT AVG(ap.satisfacao_cliente) as media
        FROM acompanhamento_projeto ap
        WHERE ap.satisfacao_cliente IS NOT NULL
          AND {latest_filter}
        '''
        met_query = f'''
        SELECT ap.modelo_gerenciamento, COUNT(*) as quantidade
        FROM acompanhamento_projeto ap
        WHERE {latest_filter}
        GROUP BY ap.modelo_gerenciamento
        '''
        cron_query = f'''
        SELECT ap.status_cronograma, COUNT(*) as quantidade
        FROM acompanhamento_projeto ap
        WHERE {latest_filter}
        GROUP BY ap.status_cronograma
        '''
        conclusao_query = f'''
        SELECT ap.pct_conclusao, COUNT(*) as quantidade
        FROM acompanhamento_projeto ap
        WHERE {latest_filter}
        GROUP BY ap.pct_conclusao
        ORDER BY FIELD(ap.pct_conclusao, '0-20%', '21-40%', '41-60%', '61-80%', '81-100%')
        '''
        motivos_query = f'''
        SELECT ap.motivos_atraso
        FROM acompanhamento_projeto ap
        WHERE {latest_filter}
          AND ap.status_cronograma IN ('Com risco de atraso', 'Atrasado')
          AND ap.motivos_atraso IS NOT NULL
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
        WHERE {latest_filter}
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
        WHERE {latest_filter}
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
        WHERE {latest_filter}
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
        WHERE {latest_filter}
        ORDER BY pe.nome
        '''

        total_respostas_result = await asyncio.to_thread(
            execute_query, total_respostas_query, fetch_one=True
        )
        total_projetos_result = await asyncio.to_thread(
            execute_query, total_projetos_query, fetch_one=True
        )
        sat_result = await asyncio.to_thread(execute_query, sat_query, fetch_one=True)
        met_result = await asyncio.to_thread(execute_query, met_query, fetch_all=True)
        cron_result = await asyncio.to_thread(execute_query, cron_query, fetch_all=True)
        conclusao_result = await asyncio.to_thread(
            execute_query, conclusao_query, fetch_all=True
        )
        motivos_rows = await asyncio.to_thread(execute_query, motivos_query, fetch_all=True)
        projetos_atuais = await asyncio.to_thread(execute_query, projetos_query, fetch_all=True)
        riscos_rows = await asyncio.to_thread(execute_query, riscos_query, fetch_all=True)
        metodo_escopo_rows = await asyncio.to_thread(
            execute_query, metodo_escopo_query, fetch_all=True
        )
        cliente_orientacao_rows = await asyncio.to_thread(
            execute_query, cliente_orientacao_query, fetch_all=True
        )

        total_respostas = total_respostas_result['total'] if total_respostas_result else 0
        total_projetos = total_projetos_result['total'] if total_projetos_result else 0
        media_satisfacao = round(sat_result['media'], 1) if sat_result and sat_result['media'] else 0
        metodologias = {row['modelo_gerenciamento']: row['quantidade'] for row in met_result} if met_result else {}
        cronograma = {row['status_cronograma']: row['quantidade'] for row in cron_result} if cron_result else {}
        conclusao = {row['pct_conclusao']: row['quantidade'] for row in conclusao_result} if conclusao_result else {}

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
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='0.0.0.0', port=8000)
