import mysql.connector
from mysql.connector import Error
from mysql.connector.pooling import MySQLConnectionPool
import os
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_USER = os.getenv('DB_USER', 'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'banco_de_dados')
DB_PORT = int(os.getenv('DB_PORT', 3306))

_pool = MySQLConnectionPool(
    pool_name='pape_pool',
    pool_size=5,
    host=DB_HOST,
    user=DB_USER,
    password=DB_PASSWORD,
    database=DB_NAME,
    port=DB_PORT,
)


def get_db_connection():
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
    except Error as e:
        print(f'Erro ao executar query: {e}')
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
    except Error as e:
        print(f'Erro ao executar insert: {e}')
        if connection:
            connection.rollback()
        raise
    finally:
        if connection and connection.is_connected():
            connection.close()
