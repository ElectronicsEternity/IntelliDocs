# ========================================
# File: connection.py
# ========================================

import psycopg

from app.config import settings


def get_connection():
    if settings.DATABASE_URL:
        return psycopg.connect(settings.DATABASE_URL)
    return psycopg.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        dbname=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
    )
