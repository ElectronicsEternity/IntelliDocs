# ========================================
# File: database.py
# ========================================

from typing import Any, Optional

from app.database.connection import get_connection


class Database:

    def execute(
        self,
        query: Any,
        params: Optional[tuple] = None,
    ) -> None:

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
            conn.commit()


    def executemany(
        self,
        query: Any,
        values: list[tuple],
    ) -> None:

        if not values:
            return

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(query, values)
            conn.commit()


    def fetch_one(
        self,
        query: Any,
        params: Optional[tuple] = None,
    ) -> Optional[tuple]:

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchone()


    def fetch_all(
        self,
        query: Any,
        params: Optional[tuple] = None,
    ) -> list[tuple]:

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchall()


    def exists(
        self,
        query: str,
        params: Optional[tuple] = None,
    ) -> bool:

        result = self.fetch_one(query, params)
        return result is not None