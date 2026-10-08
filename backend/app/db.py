import psycopg
from pgvector.psycopg import register_vector
from app.config import settings

def get_conn():
    conn = psycopg.connect(settings.database_url, autocommit=True)
    register_vector(conn)
    return conn