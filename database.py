import mysql.connector
from mysql.connector import Error
from mysql.connector.pooling import MySQLConnectionPool
import os
from dotenv import load_dotenv
import logging
from contextlib import contextmanager


logger = logging.getLogger('pape.db')


# Garante que carrega o arquivo .env do diretório onde o script está localizado
base_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(base_dir, '.env')
load_dotenv(dotenv_path)

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_USER = os.getenv('DB_USER', 'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'banco_de_dados')
DB_PORT = int(os.getenv('DB_PORT', 3306))

_pool = None


def init_pool():
    global _pool
    if _pool is None:
        _pool = MySQLConnectionPool(
            pool_name='pape_pool',
            pool_size=int(os.getenv('DB_POOL_SIZE', 5)),
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT,
        )
    return _pool


def close_pool():
    # mysql-connector não expõe close() do pool; soltar a referência libera as conexões.
    global _pool
    _pool = None


def get_db_connection():
    if _pool is None:
        init_pool()
    return _pool.get_connection()


def execute_query(query: str, params=None, fetch_one=False, fetch_all=False):
    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        if fetch_one:
            result = cursor.fetchone()
        elif fetch_all:
            result = cursor.fetchall()
        else:
            connection.commit()
            result = cursor.rowcount

        cursor.close()
        return result
    except Error:
        logger.exception('Erro ao executar query')
        if connection:
            connection.rollback()
        raise
    finally:
        if connection and connection.is_connected():
            connection.close()


def execute_insert(query: str, params=None) -> int:
    """Executa INSERT e retorna lastrowid — evita race condition de SELECT separado."""
    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        connection.commit()
        lastrowid = cursor.lastrowid
        cursor.close()
        return lastrowid
    except Error:
        logger.exception('Erro ao executar insert')
        if connection:
            connection.rollback()
        raise
    finally:
        if connection and connection.is_connected():
            connection.close()


@contextmanager
def transaction():
    """Abre uma conexão do pool e garante commit/rollback/close únicos.
    Use o objeto connection devolvido para criar cursores e executar várias escritas
    de forma atômica."""
    connection = get_db_connection()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        if connection.is_connected():
            connection.close()

