import importlib
import sys
import unittest
from unittest.mock import patch


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
        self.assertIn('LOWER(cargo)', query)
        self.assertIn('%gerente%', query)
        self.assertIn('%projeto%', query)
        self.assertEqual(response, expected_rows)


if __name__ == '__main__':
    unittest.main()
