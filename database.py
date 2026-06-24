"""Database connection and execution utilities.

This module sets up a MySQL connection pool using mysql-connector-python and
provides helpers for executing queries, inserting data safely, and managing
atomic transactions with automatic rollback and resource cleanup.
"""
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
    """Initializes the MySQL connection pool.

    The pool size is configured via the DB_POOL_SIZE environment variable
    (defaults to 5). Uses global state to maintain a singleton pool.

    Returns:
        MySQLConnectionPool: The initialized connection pool instance.
    """
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
    """Closes the connection pool by clearing the global reference.

    Since the mysql-connector-python pool doesn't expose an explicit close() method,
    releasing the global pool reference allows garbage collection to release the
    underlying connections.
    """
    # mysql-connector não expõe close() do pool; soltar a referência libera as conexões.
    global _pool
    _pool = None


def get_db_connection():
    """Retrieves a database connection from the connection pool.

    If the connection pool hasn't been initialized yet, this function calls `init_pool()`
    to set it up.

    Returns:
        mysql.connector.connection.MySQLConnection: A connection from the pool.
    """
    if _pool is None:
        init_pool()
    return _pool.get_connection()


def execute_query(query: str, params=None, fetch_one=False, fetch_all=False):
    """Executes a database query (SELECT, UPDATE, DELETE) and manages connection lifecycle.

    For SELECT queries, it returns results as dictionaries if fetch_one or fetch_all is True.
    For write operations, it commits the changes and returns the row count.
    In case of database errors, it rolls back changes, logs the exception, and raises.

    Args:
        query (str): The SQL statement to be executed.
        params (tuple, optional): Parameters to bind to the query to prevent SQL injection.
            Defaults to None.
        fetch_one (bool, optional): If True, returns a single row as a dictionary.
            Defaults to False.
        fetch_all (bool, optional): If True, returns all matching rows as a list of dictionaries.
            Defaults to False.

    Returns:
        dict | list[dict] | int | None:
            - A dictionary if `fetch_one` is True (or None if no row is found).
            - A list of dictionaries if `fetch_all` is True (or empty list if no rows are found).
            - The count of affected rows (int) for write queries (INSERT/UPDATE/DELETE).
            
    Raises:
        Error: If any MySQL exception occurs.
    """
    connection = None
    try:
        # Obter conexão do pool
        connection = get_db_connection()
        # cursor(dictionary=True) mapeia colunas aos seus respectivos nomes no dicionário de resposta
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
            # Caso seja escrita (UPDATE/DELETE/INSERT não capturado por execute_insert), realiza commit
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
        # Garante que a conexão retorne ao pool
        if connection and connection.is_connected():
            connection.close()


def execute_insert(query: str, params=None) -> int:
    """Executes an INSERT query and returns the last inserted row ID.

    This function prevents race conditions that could happen when executing a separate
    SELECT query to find the auto-increment ID.

    Args:
        query (str): The SQL INSERT statement.
        params (tuple, optional): Parameters to bind to the query to prevent SQL injection.
            Defaults to None.

    Returns:
        int: The ID of the last inserted row (lastrowid).

    Raises:
        Error: If any MySQL exception occurs.
    """
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
    de forma atômica.

    Yields:
        mysql.connector.connection.MySQLConnection: A base de dados conexão.
    """
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

