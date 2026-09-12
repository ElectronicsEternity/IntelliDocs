from typing import Any

from psycopg.rows import dict_row

from app.database.connection import get_connection


class DocumentRepository:
    """All document operations require the authenticated owner."""

    def create_uploaded(
        self,
        *,
        document_id: str,
        user_id: str,
        original_filename: str,
        storage_path: str,
        file_size: int,
        file_hash: str,
    ) -> dict[str, Any]:
        with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO documents (
                    id, owner_id, user_id, filename, original_filename,
                    storage_path, file_size, file_hash, title, file_extension,
                    processing_status, uploaded_at, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pdf',
                    'uploaded', NOW(), NOW(), NOW()
                )
                RETURNING id::text, original_filename, storage_path, file_size,
                          page_count, processing_status, processing_error,
                          created_at, updated_at
                """,
                (
                    document_id, user_id, user_id, original_filename,
                    original_filename, storage_path, file_size, file_hash,
                    original_filename.rsplit(".", 1)[0],
                ),
            )
            row = cur.fetchone()
            cur.execute(
                """
                INSERT INTO document_analysis (
                    document_id, owner_id, user_id, file_hash,
                    processing_status, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, 'uploaded', NOW(), NOW())
                """,
                (document_id, user_id, user_id, file_hash),
            )
            assert row is not None
            return dict(row)

    def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id::text, original_filename, storage_path, file_size,
                       page_count, processing_status, processing_error,
                       created_at, updated_at
                FROM documents
                WHERE user_id = %s
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def get_for_user(self, document_id: str, user_id: str) -> dict[str, Any] | None:
        with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id::text, original_filename, storage_path, file_size,
                       page_count, processing_status, processing_error,
                       created_at, updated_at
                FROM documents
                WHERE id = %s AND user_id = %s
                """,
                (document_id, user_id),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def set_status(
        self,
        document_id: str,
        user_id: str,
        status: str,
        *,
        error: str | None = None,
        page_count: int | None = None,
    ) -> None:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE documents
                SET processing_status = %s, processing_error = %s,
                    page_count = COALESCE(%s, page_count), updated_at = NOW()
                WHERE id = %s AND user_id = %s
                """,
                (status, error, page_count, document_id, user_id),
            )
            cur.execute(
                """
                UPDATE document_analysis
                SET processing_status = %s, error_message = %s, updated_at = NOW()
                WHERE document_id = %s AND user_id = %s
                """,
                (status, error, document_id, user_id),
            )

    def delete_for_user(self, document_id: str, user_id: str) -> bool:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM documents WHERE id = %s AND user_id = %s",
                (document_id, user_id),
            )
            return cur.rowcount == 1

    def totals_for_user(self, user_id: str) -> tuple[int, int]:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(file_size), 0)
                FROM documents WHERE user_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
            return (int(row[0]), int(row[1])) if row else (0, 0)
