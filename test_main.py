import importlib
import sys
import unittest
from unittest.mock import patch, MagicMock
from contextlib import contextmanager

from fastapi.testclient import TestClient



def import_main_without_database():
    sys.modules.pop('main', None)
    sys.modules.pop('database', None)
    with patch('mysql.connector.pooling.MySQLConnectionPool'):
        return importlib.import_module('main')


class MembrosEndpointTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.main = import_main_without_database()

    async def test_get_membros_filters_project_managers_by_cargo(self):
        expected_rows = [
            {'id': 1, 'nome': 'Ana Silva', 'email': 'ana@example.com'},
        ]

        async def run_sync(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch.object(self.main, 'execute_query', return_value=expected_rows) as execute_query,
            patch.object(self.main.asyncio, 'to_thread', side_effect=run_sync),
        ):
            response = await self.main.get_membros()

        query = execute_query.call_args.args[0]
        self.assertIn('FROM membro m', query)
        self.assertIn('JOIN membro_cargo mc ON mc.membro_id = m.id', query)
        self.assertIn('JOIN cargo c ON c.id = mc.cargo_id', query)
        self.assertIn('LOWER(c.nome)', query)
        self.assertIn('%gerente%', query)
        self.assertIn('%projeto%', query)
        self.assertEqual(response, expected_rows)


class MembrosPorCoordenacaoEndpointTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.main = import_main_without_database()

    async def test_get_membros_por_coordenacao_groups_properly(self):
        expected_rows = [
            {
                'id': 1,
                'nome': 'Ana Silva',
                'email': 'ana@example.com',
                'coordenacao_id': 2,
                'coordenacao_nome': 'Tecnologia e Desenvolvimento',
                'coordenacao_sigla': 'TD',
            },
            {
                'id': 2,
                'nome': 'Bruno Souza',
                'email': 'bruno@example.com',
                'coordenacao_id': None,
                'coordenacao_nome': None,
                'coordenacao_sigla': None,
            },
        ]

        async def run_sync(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch.object(self.main, 'execute_query', return_value=expected_rows) as execute_query,
            patch.object(self.main.asyncio, 'to_thread', side_effect=run_sync),
        ):
            response = await self.main.get_membros_por_coordenacao()

        query = execute_query.call_args.args[0]
        self.assertIn('FROM membro m', query)
        self.assertIn('LEFT JOIN membro_coordenacao mc ON mc.membro_id = m.id', query)
        self.assertIn('LEFT JOIN coordenacao c ON c.id = mc.coordenacao_id', query)
        
        self.assertEqual(len(response), 2)
        group_td = next(g for g in response if g['coordenacao_id'] == 2)
        group_outros = next(g for g in response if g['coordenacao_id'] == 0)

        self.assertEqual(group_td['coordenacao_sigla'], 'TD')
        self.assertEqual(group_td['membros'][0]['nome'], 'Ana Silva')

        self.assertEqual(group_outros['coordenacao_sigla'], 'OUTROS')
        self.assertEqual(group_outros['membros'][0]['nome'], 'Bruno Souza')


class ProjetosEndpointTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.main = import_main_without_database()

    async def test_get_projetos_includes_projects_without_contract_data(self):
        expected_rows = [
            {
                'id': 1,
                'nome': 'Monitora Petrogarra',
                'numero_contrato': None,
                'valor_total': None,
                'possui_orientador': None,
                'nome_orientador': None,
            },
        ]

        async def run_sync(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch.object(self.main, 'execute_query', return_value=expected_rows) as execute_query,
            patch.object(self.main.asyncio, 'to_thread', side_effect=run_sync),
        ):
            response = await self.main.get_projetos()

        query = execute_query.call_args.args[0]
        self.assertIn('FROM projeto_externo pe', query)
        self.assertIn('LEFT JOIN contrato c ON c.projeto_externo_id = pe.id', query)
        self.assertIn('c.fase_atual IS NULL', query)
        self.assertEqual(response, expected_rows)

    async def test_get_projetos_can_filter_by_manager_id(self):
        expected_rows = [
            {
                'id': 2,
                'nome': 'BN Cinderela 2.0',
                'numero_contrato': None,
                'valor_total': None,
                'possui_orientador': 1,
                'nome_orientador': 'Dra. Camila',
            },
        ]

        async def run_sync(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch.object(self.main, 'execute_query', return_value=expected_rows) as execute_query,
            patch.object(self.main.asyncio, 'to_thread', side_effect=run_sync),
        ):
            response = await self.main.get_projetos(gerente_id=7)

        query, params = execute_query.call_args.args[:2]
        self.assertIn('EXISTS', query)
        self.assertIn('FROM membro_projeto mp', query)
        self.assertIn('JOIN cargo cg ON cg.id = mp.cargo_id', query)
        self.assertIn('mp.membro_id = %s', query)
        self.assertIn('mp.data_saida IS NULL', query)
        self.assertIn('%gerente%', query)
        self.assertIn('%projeto%', query)
        self.assertEqual(params, (7,))
        self.assertEqual(response, expected_rows)

    def test_projetos_response_accepts_missing_contract_fields(self):
        expected_rows = [
            {
                'id': 1,
                'nome': 'Monitora Petrogarra',
                'numero_contrato': None,
                'valor_total': None,
                'possui_orientador': None,
                'nome_orientador': None,
            },
        ]

        async def run_sync(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch.object(self.main, 'execute_query', return_value=expected_rows),
            patch.object(self.main.asyncio, 'to_thread', side_effect=run_sync),
        ):
            response = TestClient(self.main.app).get('/api/projetos')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected_rows)

    async def test_get_projeto_detalhes_returns_orientador_state_without_contract(self):
        projeto_row = {
            'id': 1,
            'nome': 'Monitora Petrogarra',
            'data_inicio': None,
            'numero_contrato': None,
            'valor_total': None,
            'possui_orientador': 0,
            'nome_orientador': None,
        }

        async def run_sync(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch.object(self.main, 'execute_query', side_effect=[projeto_row, [], [], [], []]) as execute_query,
            patch.object(self.main.asyncio, 'to_thread', side_effect=run_sync),
        ):
            response = await self.main.get_projeto_detalhes(1)

        query = execute_query.call_args_list[0].args[0]
        self.assertIn('pe.possui_orientador', query)
        self.assertIn('pe.nome_orientador', query)
        self.assertIn('LEFT JOIN contrato c ON c.projeto_externo_id = pe.id', query)
        self.assertEqual(response['possui_orientador'], 0)
        self.assertEqual(response['nome_orientador'], None)


class SubmitPapeValidationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.main = import_main_without_database()

    async def test_validate_project_manager_checks_selected_project_and_respondent(self):
        async def run_sync(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch.object(self.main, 'execute_query', return_value={'id': 1}) as execute_query,
            patch.object(self.main.asyncio, 'to_thread', side_effect=run_sync),
        ):
            is_valid = await self.main.validate_project_manager('Ana Silva', 3)

        query, params = execute_query.call_args.args[:2]
        self.assertIn('FROM membro_projeto mp', query)
        self.assertIn('JOIN membro m ON m.id = mp.membro_id', query)
        self.assertIn('JOIN cargo c ON c.id = mp.cargo_id', query)
        self.assertIn('mp.projeto_externo_id = %s', query)
        self.assertIn('m.nome = %s', query)
        self.assertIn('mp.data_saida IS NULL', query)
        self.assertEqual(params, (3, 'Ana Silva'))
        self.assertTrue(is_valid)

    async def test_validate_project_manager_rejects_non_manager(self):
        async def run_sync(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch.object(self.main, 'execute_query', return_value=None),
            patch.object(self.main.asyncio, 'to_thread', side_effect=run_sync),
        ):
            is_valid = await self.main.validate_project_manager('Ana Silva', 99)

        self.assertFalse(is_valid)

    async def test_update_project_orientador_if_unknown_saves_first_answer(self):
        async def run_sync(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch.object(self.main, 'execute_query', return_value=1) as execute_query,
            patch.object(self.main.asyncio, 'to_thread', side_effect=run_sync),
        ):
            await self.main.update_project_orientador_if_unknown(3, 'Sim', 'Dra. Camila')

        query, params = execute_query.call_args.args[:2]
        self.assertIn('UPDATE projeto_externo', query)
        self.assertIn('WHERE id = %s', query)
        self.assertIn('possui_orientador IS NULL', query)
        self.assertEqual(params, (1, 'Dra. Camila', 3))


class DashboardPapeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.main = import_main_without_database()

    def test_count_motivos_atraso_accepts_json_lists_and_plain_text(self):
        rows = [
            {'motivos_atraso': '["Comunicação com cliente", "Capacidade técnica"]'},
            {'motivos_atraso': '["Comunicação com cliente"]'},
            {'motivos_atraso': 'Falta de recursos'},
            {'motivos_atraso': None},
        ]

        result = self.main.count_motivos_atraso(rows)

        self.assertEqual(
            result,
            [
                {'name': 'Comunicação com cliente', 'value': 2},
                {'name': 'Capacidade técnica', 'value': 1},
                {'name': 'Falta de recursos (Ex: Ferramentas, orçamento...)', 'value': 1},
            ],
        )

    def test_build_riscos_dashboard_groups_motivos_and_scores(self):
        rows = [
            {
                'projeto': 'AM do Amor',
                'status_cronograma': 'Atrasado',
                'motivos_atraso': '["Comunicação com cliente", "Capacidade técnica"]',
                'coordenacao': 'Gestão de Negócios',
                'suficiencia_orcamento': 2,
                'comunicacao_cliente': 3,
                'capacitacao_equipe': 4,
            },
            {
                'projeto': 'Valida Bruninho',
                'status_cronograma': 'Com risco de atraso',
                'motivos_atraso': '["Comunicação com cliente"]',
                'coordenacao': 'Tecnologia e Desenvolvimento, Gestão de Negócios',
                'suficiencia_orcamento': 4,
                'comunicacao_cliente': 2,
                'capacitacao_equipe': 5,
            },
        ]

        result = self.main.build_riscos_dashboard(rows)

        self.assertEqual(result['motivos_por_coordenacao'][0]['motivo'], 'Capacidade técnica')
        self.assertEqual(result['motivos_por_coordenacao'][0]['total'], 1)
        self.assertEqual(result['motivos_por_coordenacao'][1]['motivo'], 'Comunicação com cliente')
        self.assertEqual(result['motivos_por_coordenacao'][1]['total'], 3)
        self.assertEqual(result['motivos_por_coordenacao'][1]['coordenacoes']['Gestão de Negócios'], 2)
        self.assertEqual(len(result['projetos_em_risco']), 2)
        self.assertEqual(result['suficiencia_orcamento'][0], {'name': 'AM do Amor', 'value': 2})
        self.assertEqual(result['comunicacao_cliente'][0], {'name': 'Valida Bruninho', 'value': 2})

    def test_build_metodo_escopo_dashboard_orders_scores_and_attention_points(self):
        rows = [
            {
                'projeto': 'AM do Amor',
                'modelo_gerenciamento': 'Agil',
                'nivel_retrabalho': 5,
                'variacao_escopo': None,
                'capacitacao_equipe': 4,
                'eficacia_metodologia': 2,
            },
            {
                'projeto': 'Miller P(AI)',
                'modelo_gerenciamento': 'Hibrido',
                'nivel_retrabalho': 2,
                'variacao_escopo': 4,
                'capacitacao_equipe': 3,
                'eficacia_metodologia': 1,
            },
            {
                'projeto': 'FEMEA no Mar',
                'modelo_gerenciamento': 'Tradicional',
                'nivel_retrabalho': 4,
                'variacao_escopo': 1,
                'capacitacao_equipe': 2,
                'eficacia_metodologia': 5,
            },
        ]

        result = self.main.build_metodo_escopo_dashboard(rows)

        self.assertEqual(result['retrabalho'][0], {'name': 'Miller P(AI)', 'value': 2})
        self.assertEqual(result['variacao_escopo'][0], {'name': 'FEMEA no Mar', 'value': 1})
        self.assertEqual(result['eficacia_metodologia'][0], {'name': 'Miller P(AI)', 'value': 1})
        self.assertEqual(result['medias']['variacao_escopo'], 2.5)
        self.assertEqual(result['pontos_atencao'][0]['projeto'], 'FEMEA no Mar')
        self.assertEqual(result['pontos_atencao'][0]['indicador'], 'Capacitação da equipe')

    def test_build_cliente_orientacao_dashboard_aggregates_client_and_advisor_scores(self):
        rows = [
            {
                'projeto': 'AM do Amor',
                'comunicacao_cliente': 4,
                'abertura_cliente': 5,
                'satisfacao_cliente': 5,
                'cliente_percebeu_valor': 3,
                'impacto_cliente': 'Moderado',
                'possui_orientador': 1,
                'nome_orientador': 'Cristiano Saad',
                'efetividade_orientador': 5,
                'disponibilidade_orientador': 4,
            },
            {
                'projeto': 'Miller P(AI)',
                'comunicacao_cliente': 2,
                'abertura_cliente': 3,
                'satisfacao_cliente': 3,
                'cliente_percebeu_valor': 4,
                'impacto_cliente': 'Leve',
                'possui_orientador': 1,
                'nome_orientador': 'Jose Kimio',
                'efetividade_orientador': 4,
                'disponibilidade_orientador': 5,
            },
            {
                'projeto': 'FEMEA no Mar',
                'comunicacao_cliente': 3,
                'abertura_cliente': 2,
                'satisfacao_cliente': 2,
                'cliente_percebeu_valor': None,
                'impacto_cliente': None,
                'possui_orientador': 0,
                'nome_orientador': None,
                'efetividade_orientador': None,
                'disponibilidade_orientador': None,
            },
        ]

        result = self.main.build_cliente_orientacao_dashboard(rows)

        self.assertEqual(result['comunicacao_cliente'][0], {'name': 'Miller P(AI)', 'value': 2})
        self.assertEqual(result['confianca_cliente'][0], {'name': 'FEMEA no Mar', 'value': 2})
        self.assertEqual(result['quantidade_orientadores'], 2)
        self.assertEqual(result['projetos_com_orientacao_pct'], 66.7)
        self.assertEqual(result['orientadores']['efetividade'][0], {'name': 'Cristiano Saad', 'value': 5.0})
        self.assertEqual(result['pontos_atencao'][0]['projeto'], 'Miller P(AI)')
        self.assertEqual(result['pontos_atencao'][0]['indicador'], 'Comunicação efetiva')

    def test_build_agil_dashboard_groups_story_points_and_impediments(self):
        rows = [
            {
                'projeto': 'Miller P(AI)',
                'gerente': 'Bryan Vidal',
                'data_resposta': '2026-03-21',
                'impacto_cliente': 'Leve',
                'pct_story_points': '81-100%',
                'impedimentos': 'Dependencia externa, Capacidade técnica',
                'intervencao_pmo': 'Não',
                'one_on_one_pmo': 'Sim',
            },
            {
                'projeto': 'AM do Amor',
                'gerente': 'Naylan Cardoso',
                'data_resposta': '2026-03-10',
                'impacto_cliente': 'Moderado',
                'pct_story_points': '41-60%',
                'impedimentos': None,
                'intervencao_pmo': 'Sim',
                'one_on_one_pmo': 'Não',
            },
        ]

        result = self.main.build_agil_dashboard(rows)

        self.assertEqual(result['story_points'][0], {'name': '81-100%', 'value': 1})
        self.assertEqual(result['impedimentos'][0], {'name': 'Dependencia externa', 'value': 1})
        self.assertEqual(result['projetos'][0]['projeto'], 'Miller P(AI)')
        self.assertEqual(result['projetos'][0]['impedimentos'], ['Dependencia externa', 'Capacidade técnica'])
        self.assertEqual(result['resumo']['media_story_points'], 70.0)
        self.assertEqual(result['resumo']['projetos_com_impedimento'], 1)
        self.assertEqual(result['resumo']['solicitacoes_1_1'], 1)

    def test_build_detalhe_dashboard_focuses_priority_project_history(self):
        rows = [
            {
                'id': 1,
                'projeto_id': 10,
                'projeto': 'Protege Católica',
                'gerente': 'Victor Hugo',
                'data_resposta': '2026-01-07',
                'status_cronograma': 'Com risco de atraso',
                'pct_conclusao': '0-20%',
                'impacto_cliente': 'Moderado',
                'motivos_atraso': '["Comunicação com cliente"]',
                'comunicacao_cliente': 3,
                'abertura_cliente': 2,
                'eficacia_metodologia': 2,
                'capacitacao_equipe': 2,
                'nivel_retrabalho': 2,
                'suficiencia_orcamento': 3,
                'intervencao_pmo': 'Não',
                'one_on_one_pmo': 'Não',
            },
            {
                'id': 2,
                'projeto_id': 10,
                'projeto': 'Protege Católica',
                'gerente': 'Victor Hugo',
                'data_resposta': '2026-03-26',
                'status_cronograma': 'Atrasado',
                'pct_conclusao': '61-80%',
                'impacto_cliente': 'Moderado',
                'motivos_atraso': '["Capacidade técnica", "Comunicação com cliente"]',
                'comunicacao_cliente': 2,
                'abertura_cliente': 2,
                'eficacia_metodologia': 1,
                'capacitacao_equipe': 2,
                'nivel_retrabalho': 2,
                'suficiencia_orcamento': 3,
                'intervencao_pmo': 'Não',
                'one_on_one_pmo': 'Sim',
            },
            {
                'id': 3,
                'projeto_id': 11,
                'projeto': 'AM do Amor',
                'gerente': 'Naylan Cardoso',
                'data_resposta': '2026-03-10',
                'status_cronograma': 'Dentro do prazo',
                'pct_conclusao': '41-60%',
                'impacto_cliente': 'Leve',
                'motivos_atraso': None,
                'comunicacao_cliente': 4,
                'abertura_cliente': 5,
                'eficacia_metodologia': 4,
                'capacitacao_equipe': 4,
                'nivel_retrabalho': 5,
                'suficiencia_orcamento': 4,
                'intervencao_pmo': 'Não',
                'one_on_one_pmo': 'Não',
            },
        ]

        result = self.main.build_detalhe_dashboard(rows)

        self.assertEqual(result['projeto_foco']['projeto'], 'Protege Católica')
        self.assertEqual(result['projeto_foco']['status_cronograma'], 'Atrasado')
        self.assertEqual(result['andamento'], [
            {'name': '07/01/2026', 'value': 10},
            {'name': '26/03/2026', 'value': 70},
        ])
        self.assertEqual(result['metricas']['eficacia_metodologia'], 1)
        self.assertEqual(result['motivos_atraso'][0], {'name': 'Comunicação com cliente', 'value': 2})
        self.assertEqual(len(result['historico']), 2)

    async def test_get_dashboard_pape_uses_latest_project_answers(self):
        expected_results = [
            {'total': 12},
            {'total': 8},
            {'media': 4.25},
            [{'modelo_gerenciamento': 'Ágil', 'quantidade': 3}],
            [{'status_cronograma': 'Atrasado', 'quantidade': 2}],
            [{'pct_conclusao': '61-80%', 'quantidade': 2}],
            [{'motivos_atraso': '["Comunicação com cliente"]'}],
            [{'id': 1, 'projeto': 'AM do Amor'}],
            [
                {
                    'projeto': 'AM do Amor',
                    'status_cronograma': 'Atrasado',
                    'motivos_atraso': '["Comunicação com cliente"]',
                    'coordenacao': 'Gestão de Negócios',
                    'suficiencia_orcamento': 2,
                    'comunicacao_cliente': 3,
                    'capacitacao_equipe': 4,
                }
            ],
            [
                {
                    'projeto': 'AM do Amor',
                    'modelo_gerenciamento': 'Agil',
                    'nivel_retrabalho': 5,
                    'variacao_escopo': None,
                    'capacitacao_equipe': 4,
                    'eficacia_metodologia': 2,
                }
            ],
            [
                {
                    'projeto': 'AM do Amor',
                    'comunicacao_cliente': 4,
                    'abertura_cliente': 5,
                    'satisfacao_cliente': 5,
                    'cliente_percebeu_valor': 3,
                    'impacto_cliente': 'Moderado',
                    'possui_orientador': 1,
                    'nome_orientador': 'Cristiano Saad',
                    'efetividade_orientador': 5,
                    'disponibilidade_orientador': 4,
                }
            ],
            [
                {
                    'projeto': 'Miller P(AI)',
                    'gerente': 'Bryan Vidal',
                    'data_resposta': '2026-03-21',
                    'impacto_cliente': 'Leve',
                    'pct_story_points': '81-100%',
                    'impedimentos': 'Dependencia externa',
                    'intervencao_pmo': 'Não',
                    'one_on_one_pmo': 'Sim',
                }
            ],
            [
                {
                    'id': 2,
                    'projeto_id': 10,
                    'projeto': 'Protege Católica',
                    'gerente': 'Victor Hugo',
                    'data_resposta': '2026-03-26',
                    'status_cronograma': 'Atrasado',
                    'pct_conclusao': '61-80%',
                    'impacto_cliente': 'Moderado',
                    'motivos_atraso': '["Capacidade técnica"]',
                    'comunicacao_cliente': 2,
                    'abertura_cliente': 2,
                    'eficacia_metodologia': 1,
                    'capacitacao_equipe': 2,
                    'nivel_retrabalho': 2,
                    'suficiencia_orcamento': 3,
                    'intervencao_pmo': 'Não',
                    'one_on_one_pmo': 'Sim',
                }
            ],
            [
                {'data_resposta': '2026-05-30'},
                {'data_resposta': '2026-05-15'},
            ],
        ]

        async def run_sync(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch.object(self.main, 'execute_query', side_effect=expected_results) as execute_query,
            patch.object(self.main.asyncio, 'to_thread', side_effect=run_sync),
        ):
            response = await self.main.get_dashboard_pape()

        dashboard_queries = '\n'.join(call.args[0] for call in execute_query.call_args_list)
        self.assertIn('NOT EXISTS', dashboard_queries)
        self.assertIn('ap2.projeto_externo_id = ap.projeto_externo_id', dashboard_queries)
        self.assertIn('GROUP BY ap.status_cronograma', dashboard_queries)
        self.assertEqual(response['total_respostas'], 12)
        self.assertEqual(response['total_projetos'], 8)
        self.assertEqual(response['media_satisfacao'], 4.2)
        self.assertEqual(response['motivos_atraso'], [{'name': 'Comunicação com cliente', 'value': 1}])
        self.assertEqual(response['projetos_atuais'], [{'id': 1, 'projeto': 'AM do Amor'}])
        self.assertEqual(response['riscos']['suficiencia_orcamento'], [{'name': 'AM do Amor', 'value': 2}])
        self.assertEqual(response['metodo_escopo']['retrabalho'], [{'name': 'AM do Amor', 'value': 5}])
        self.assertEqual(response['cliente_orientacao']['quantidade_orientadores'], 1)
        self.assertEqual(response['agil']['resumo']['solicitacoes_1_1'], 1)
        self.assertEqual(response['detalhe']['projeto_foco']['projeto'], 'Protege Católica')
        self.assertEqual(response['datas_disponiveis'], ['2026-05-30', '2026-05-15'])


class UpdateProjetoEndpointTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.main = import_main_without_database()
        self.main.ADMIN_API_TOKEN = 'token-de-teste'
        self.client = TestClient(self.main.app)
        self.auth = {'Authorization': 'Bearer token-de-teste'}

    async def test_update_projeto_unauthorized_without_token(self):
        response = self.client.put('/api/projetos/10', json={
            'nome': 'Projeto Teste',
            'descricao_projeto': 'Desc',
            'data_inicio': '2026-05-01',
            'numero_contrato': '123',
            'valor_total': 1500.0,
            'possui_orientador': 0,
            'nome_orientador': None
        })
        self.assertEqual(response.status_code, 401)

    async def test_update_projeto_not_found(self):
        async def run_sync(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch.object(self.main, 'execute_query', return_value=None) as execute_query,
            patch.object(self.main.asyncio, 'to_thread', side_effect=run_sync),
        ):
            response = self.client.put('/api/projetos/999', headers=self.auth, json={
                'nome': 'Projeto Teste',
                'descricao_projeto': 'Desc',
                'data_inicio': '2026-05-01',
                'numero_contrato': '123',
                'valor_total': 1500.0,
                'possui_orientador': 0,
                'nome_orientador': None
            })

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['detail'], 'Projeto não encontrado')

    async def test_update_projeto_success_updates_contract(self):
        async def run_sync(func, *args, **kwargs):
            return func(*args, **kwargs)

        mock_returns = [
            {'id': 10},
            1,
            {'id': 5},
            1
        ]

        with (
            patch.object(self.main, 'execute_query', side_effect=mock_returns) as execute_query,
            patch.object(self.main.asyncio, 'to_thread', side_effect=run_sync),
        ):
            response = self.client.put('/api/projetos/10', headers=self.auth, json={
                'nome': 'Projeto Editado',
                'descricao_projeto': 'Desc Editada',
                'data_inicio': '2026-05-01',
                'numero_contrato': '123-ABC',
                'valor_total': 25000.0,
                'possui_orientador': 1,
                'nome_orientador': 'Orientador Teste'
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'success': True, 'message': 'Projeto atualizado com sucesso'})
        
        self.assertEqual(execute_query.call_count, 4)
        queries = [call.args[0] for call in execute_query.call_args_list]
        self.assertIn('SELECT id FROM projeto_externo', queries[0])
        self.assertIn('UPDATE projeto_externo', queries[1])
        self.assertIn('SELECT id FROM contrato', queries[2])
        self.assertIn('UPDATE contrato', queries[3])




class DeleteProjetoEndpointTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.main = import_main_without_database()
        self.main.ADMIN_API_TOKEN = 'token-de-teste'
        self.client = TestClient(self.main.app)
        self.auth = {'Authorization': 'Bearer token-de-teste'}

    async def test_delete_projeto_unauthorized_without_token(self):
        response = self.client.delete('/api/projetos/10')
        self.assertEqual(response.status_code, 401)

    async def test_delete_projeto_not_found_returns_404(self):
        async def run_sync(func, *args, **kwargs):
            return func(*args, **kwargs)

        cursor = MagicMock()
        cursor.fetchone.return_value = None  # projeto não existe
        conn = MagicMock()
        conn.cursor.return_value = cursor

        @contextmanager
        def fake_tx():
            yield conn

        with (
            patch.object(self.main, 'transaction', fake_tx),
            patch.object(self.main.asyncio, 'to_thread', side_effect=run_sync),
        ):
            response = self.client.delete('/api/projetos/999', headers=self.auth)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['detail'], 'Projeto não encontrado')

    async def test_delete_projeto_success_runs_in_one_transaction(self):
        async def run_sync(func, *args, **kwargs):
            return func(*args, **kwargs)

        cursor = MagicMock()
        cursor.fetchone.return_value = {'id': 10}  # projeto existe
        conn = MagicMock()
        conn.cursor.return_value = cursor

        @contextmanager
        def fake_tx():
            yield conn

        with (
            patch.object(self.main, 'transaction', fake_tx),
            patch.object(self.main.asyncio, 'to_thread', side_effect=run_sync),
        ):
            response = self.client.delete('/api/projetos/10', headers=self.auth)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'success': True, 'message': 'Projeto excluído com sucesso'})
        # Todas as escritas no MESMO cursor (mesma conexão/transação):
        executed = ' '.join(call.args[0] for call in cursor.execute.call_args_list)
        self.assertIn('DELETE FROM projeto_externo WHERE id', executed)
        self.assertIn('DELETE FROM acompanhamento_projeto', executed)
        self.assertIn('UPDATE transacao', executed)



class AdminTokenTest(unittest.TestCase):
    def setUp(self):
        self.main = import_main_without_database()

    def test_rejects_when_token_not_configured(self):
        self.main.ADMIN_API_TOKEN = ''
        with self.assertRaises(self.main.HTTPException) as ctx:
            self.main.require_admin_token(authorization='Bearer qualquer')
        self.assertEqual(ctx.exception.status_code, 503)

    def test_rejects_missing_token(self):
        self.main.ADMIN_API_TOKEN = 'token-de-teste'
        with self.assertRaises(self.main.HTTPException) as ctx:
            self.main.require_admin_token(authorization=None)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_rejects_wrong_token(self):
        self.main.ADMIN_API_TOKEN = 'token-de-teste'
        with self.assertRaises(self.main.HTTPException) as ctx:
            self.main.require_admin_token(authorization='Bearer errado')
        self.assertEqual(ctx.exception.status_code, 401)

    def test_accepts_valid_token(self):
        self.main.ADMIN_API_TOKEN = 'token-de-teste'
        self.assertIsNone(self.main.require_admin_token(authorization='Bearer token-de-teste'))


class ErrorLeakTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.main = import_main_without_database()
        self.client = TestClient(self.main.app, raise_server_exceptions=False)

    def test_db_error_is_not_exposed(self):
        async def run_sync(func, *args, **kwargs):
            return func(*args, **kwargs)

        def boom(*args, **kwargs):
            raise RuntimeError('detalhe-secreto-do-banco')

        with (
            patch.object(self.main, 'execute_query', side_effect=boom),
            patch.object(self.main.asyncio, 'to_thread', side_effect=run_sync),
        ):
            response = self.client.get('/api/coordenacoes')

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()['detail'], 'Erro interno do servidor')
        self.assertNotIn('detalhe-secreto-do-banco', response.text)


class TransactionTest(unittest.TestCase):
    def setUp(self):
        import importlib, sys
        sys.modules.pop('database', None)
        with patch('mysql.connector.pooling.MySQLConnectionPool'):
            self.database = importlib.import_module('database')

    def test_commits_and_closes_on_success(self):
        conn = self.database._pool.get_connection.return_value
        conn.reset_mock()
        with self.database.transaction() as c:
            self.assertIs(c, conn)
        conn.commit.assert_called_once()
        conn.rollback.assert_not_called()
        conn.close.assert_called_once()

    def test_rolls_back_on_exception(self):
        conn = self.database._pool.get_connection.return_value
        conn.reset_mock()
        with self.assertRaises(ValueError):
            with self.database.transaction():
                raise ValueError('falhou no meio')
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()
        conn.close.assert_called_once()


class SubmitPapeTransactionTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.main = import_main_without_database()

    async def test_submit_succeeds_without_contract(self):
        cursor = MagicMock()
        # 1ª query: lookup do contrato_id -> None (projeto sem contrato)
        # 2ª query: INSERT do acompanhamento -> lastrowid 123
        cursor.fetchone.return_value = {'contrato_id': None}
        cursor.lastrowid = 123
        conn = MagicMock()
        conn.cursor.return_value = cursor

        @contextmanager
        def fake_tx():
            yield conn

        async def fake_validate(nome, pid):
            return True

        with (
            patch.object(self.main, 'transaction', fake_tx),
            patch.object(self.main, 'validate_project_manager', side_effect=fake_validate),
            patch.object(self.main, 'update_project_orientador_if_unknown', side_effect=lambda *a, **k: None),
        ):
            self.main.update_project_orientador_if_unknown = \
                lambda *a, **k: __import__('asyncio').sleep(0)
            acomp_id = self.main._submit_pape_tx(self._payload())

        self.assertEqual(acomp_id, 123)
        executed = ' '.join(call.args[0] for call in cursor.execute.call_args_list)
        self.assertIn('INSERT INTO acompanhamento_projeto', executed)

    def _payload(self):
        return self.main.PapeFormData(
            respondente_nome='Ana Silva',
            projeto_externo_id=1,
            primeira_resposta='Não',
            possui_orientador='Não',
            modelo_gerenciamento='Tradicional',
            pct_conclusao='41-60%',
            status_cronograma='Dentro do prazo',
            capacitacao_equipe=4, eficacia_metodologia=4, nivel_retrabalho=2,
            comunicacao_cliente=4, abertura_cliente=4, satisfacao_cliente=4,
        )


if __name__ == '__main__':
    unittest.main()





