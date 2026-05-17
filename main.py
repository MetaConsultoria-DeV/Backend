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
    SELECT pe.id, pe.nome, c.numero as numero_contrato, c.valor_total
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


@app.get('/api/projetos/{projeto_id}')
async def get_projeto_detalhes(projeto_id: int):
    query = '''
    SELECT pe.id, pe.nome, pe.data_inicio, c.numero as numero_contrato,
           c.valor_total, c.data_inicio
    FROM projeto_externo pe
    JOIN contrato c ON c.projeto_externo_id = pe.id
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
                detail='Este projeto nÃ£o estÃ¡ vinculado Ã  gerente selecionada',
            )

        acomp_query = '''
        INSERT INTO acompanhamento_projeto (
            projeto_externo_id, contrato_id, data_resposta, modelo_gerenciamento,
            pct_conclusao, status_cronograma, motivos_atraso,
            capacitacao_equipe, eficacia_metodologia, nivel_retrabalho,
            comunicacao_cliente, orcamento_nao_necessario
        )
        SELECT %s, c.id, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        FROM contrato c
        WHERE c.projeto_externo_id = %s
        LIMIT 1
        '''

        motivos_str = json.dumps(data.motivos_atraso) if data.motivos_atraso else None
        orcamento_nao_necessario = 1 if data.suficiencia_orcamento == 'Não necessitou' else 0

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
                data.projeto_externo_id,
            ),
        )

        if not acomp_id:
            raise Exception('Nenhuma linha inserida em acompanhamento_projeto')

        if data.possui_orientador == 'Sim':
            orient_query = '''
            INSERT INTO acomp_orientador (acompanhamento_id, possui_orientador, nome_orientador)
            VALUES (%s, 1, %s)
            '''
            await asyncio.to_thread(
                execute_query, orient_query, (acomp_id, data.nome_orientador or 'Sem nome')
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


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='0.0.0.0', port=8000)
