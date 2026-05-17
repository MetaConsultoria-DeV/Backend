import importlib
import sys
import unittest
from unittest.mock import patch

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
            patch.object(self.main, 'execute_query', side_effect=[projeto_row, [], []]) as execute_query,
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


if __name__ == '__main__':
    unittest.main()
