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

    def test_projetos_response_accepts_missing_contract_fields(self):
        expected_rows = [
            {
                'id': 1,
                'nome': 'Monitora Petrogarra',
                'numero_contrato': None,
                'valor_total': None,
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


if __name__ == '__main__':
    unittest.main()
