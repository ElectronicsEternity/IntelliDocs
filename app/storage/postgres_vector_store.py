# ========================================
# File: postgres_vector_store.py
# ========================================
#
# Purpose
# -------
# Persist documents, chunks, and embeddings.
#
# Responsibilities
# ----------------
# - Store structured chunk metadata.
# - Run vector similarity retrieval.
# - Expand similar or exact nodes through descendants.
# - Maintain document processing state.
#
# ========================================

from dataclasses import asdict

from psycopg import sql
from psycopg.types.json import Jsonb

from app.constants import (
    CURRENT_EMBEDDING_VERSION,
    SIMILARITY_THRESHOLD,
    TOP_K,
)
from app.database.connection import get_connection
from app.models.document_analysis import DocumentAnalysis


# ==========================================================
# PostgreSQL Vector Store
# ==========================================================

class PostgresVectorStore:

    def __init__(self):
        self.connection = get_connection()

    # Store document metadata.
    def add_document(self, document) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT INTO documents (
                id, owner_id, filename, title,
                file_hash, uploaded_at,
                document_type, language
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                document.id,
                document.owner_id,
                document.filename,
                document.title,
                document.file_hash,
                document.uploaded_at,
                document.document_type,
                document.language,
            ),
        )
        self.connection.commit()
        cursor.close()

    def commit(self) -> None:
        self.connection.commit()

    # Store one chunk with its retrieval structure.
    def add_chunk(self, chunk) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT INTO chunks (
                id, document_id, node_id,
                chunk_number, page_number,
                content_type, token_count,
                text, metadata
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            """,
            (
                chunk.id,
                chunk.document_id,
                chunk.node_id,
                chunk.chunk_number,
                chunk.page_number,
                chunk.content_type,
                chunk.token_count,
                chunk.text,
                Jsonb(asdict(chunk.metadata)),
            ),
        )
        cursor.close()

    def close(self) -> None:
        self.connection.close()

    def add_embedding(
        self,
        chunk_id,
        embedding,
    ) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT INTO embeddings (chunk_id, embedding)
            VALUES (%s, %s)
            """,
            (chunk_id, embedding),
        )
        cursor.close()

    # Store one searchable hierarchy-node embedding.
    def add_node_embedding(
        self,
        node_id: str,
        search_text: str,
        embedding,
    ) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT INTO node_embeddings (
                node_id, search_text, embedding,
                embedding_version
            )
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (node_id) DO UPDATE
            SET search_text = EXCLUDED.search_text,
                embedding = EXCLUDED.embedding,
                embedding_version = EXCLUDED.embedding_version
            """,
            (
                node_id,
                search_text,
                embedding,
                CURRENT_EMBEDDING_VERSION,
            ),
        )
        cursor.close()

    # Find chunks by embedding similarity.
    def search(
        self,
        owner_id: str,
        embedding,
        top_k: int = TOP_K,
    ) -> list[dict]:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT
                c.id, c.document_id, c.node_id,
                c.content_type, c.text, c.metadata,
                COALESCE(d.title, d.filename),
                d.filename, n.node_type, n.identifier,
                n.title,
                1 - (e.embedding <=> %s::vector)
                    AS similarity
            FROM embeddings e
            JOIN chunks c ON c.id = e.chunk_id
            JOIN documents d ON d.id = c.document_id
            LEFT JOIN document_nodes n ON n.id = c.node_id
            WHERE d.owner_id = %s
            AND 1 - (e.embedding <=> %s::vector) >= %s
            ORDER BY similarity DESC
            LIMIT %s
            """,
            (
                embedding,
                owner_id,
                embedding,
                SIMILARITY_THRESHOLD,
                top_k,
            ),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [self._map_search_row(row) for row in rows]

    # Find similar nodes and rank their descendant chunks.
    def search_node_hierarchy(
        self,
        owner_id: str,
        embedding,
        top_k: int = TOP_K,
    ) -> list[dict]:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            WITH RECURSIVE matched_nodes AS (
                SELECT
                    ne.node_id AS id,
                    1 - (
                        ne.embedding <=> %s::vector
                    ) AS node_similarity
                FROM node_embeddings ne
                JOIN document_nodes n ON n.id = ne.node_id
                JOIN documents d ON d.id = n.document_id
                WHERE d.owner_id = %s
                AND ne.embedding_version = %s
                AND 1 - (
                    ne.embedding <=> %s::vector
                ) >= %s
                ORDER BY node_similarity DESC
                LIMIT %s
            ), hierarchy AS (
                SELECT
                    id AS root_id,
                    id AS node_id,
                    node_similarity
                FROM matched_nodes
                UNION ALL
                SELECT
                    h.root_id,
                    child.id,
                    h.node_similarity
                FROM hierarchy h
                JOIN document_nodes child
                    ON child.parent_id = h.node_id
            ), ranked_nodes AS (
                SELECT
                    node_id,
                    MAX(node_similarity) AS node_similarity
                FROM hierarchy
                GROUP BY node_id
            )
            SELECT
                c.id, c.document_id, c.node_id,
                c.content_type, c.text, c.metadata,
                COALESCE(d.title, d.filename),
                d.filename, n.node_type, n.identifier,
                n.title,
                1 - (e.embedding <=> %s::vector)
                    AS similarity,
                rn.node_similarity
            FROM ranked_nodes rn
            JOIN chunks c ON c.node_id = rn.node_id
            JOIN embeddings e ON e.chunk_id = c.id
            JOIN documents d ON d.id = c.document_id
            LEFT JOIN document_nodes n ON n.id = c.node_id
            WHERE 1 - (e.embedding <=> %s::vector) >= %s
            ORDER BY rn.node_similarity DESC, similarity DESC
            LIMIT %s
            """,
            (
                embedding,
                owner_id,
                CURRENT_EMBEDDING_VERSION,
                embedding,
                SIMILARITY_THRESHOLD,
                top_k,
                embedding,
                embedding,
                SIMILARITY_THRESHOLD,
                top_k,
            ),
        )
        rows = cursor.fetchall()
        cursor.close()
        results = []

        # Add node similarity to the shared result shape.
        for row in rows:
            result = self._map_search_row(row)
            result["node_similarity"] = float(row[12])
            results.append(result)

        return results

    # Find explicit identifiers and include descendants.
    def search_exact_identifier(
        self,
        owner_id: str,
        query: str,
        embedding,
        top_k: int = TOP_K,
    ) -> list[dict]:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            WITH RECURSIVE matched_nodes AS (
                SELECT n.id
                FROM document_nodes n
                JOIN documents d ON d.id = n.document_id
                WHERE d.owner_id = %s
                AND n.identifier IS NOT NULL
                AND btrim(n.identifier) <> ''
                AND (
                    -- Accept the original punctuated reference.
                    (
                        right(btrim(n.identifier), 1)
                            !~ '[[:alnum:]]'
                        AND lower(%s) LIKE (
                            '%%' || lower(
                                replace(
                                    n.node_type,
                                    '_',
                                    ' '
                                )
                            ) || ' ' || lower(
                                btrim(n.identifier)
                            ) || '%%'
                        )
                    )
                    -- Also accept a normalized whole reference.
                    OR (
                        ' ' || btrim(
                            regexp_replace(
                                lower(%s),
                                '[^[:alnum:]]+',
                                ' ',
                                'g'
                            )
                        ) || ' '
                    ) LIKE (
                        '%% ' || lower(
                            replace(
                                n.node_type,
                                '_',
                                ' '
                            )
                        ) || ' ' || btrim(
                            regexp_replace(
                                lower(btrim(n.identifier)),
                                '[^[:alnum:]]+',
                                ' ',
                                'g'
                            )
                        ) || ' %%'
                    )
                )
            ), hierarchy AS (
                SELECT id AS root_id, id AS node_id
                FROM matched_nodes
                UNION ALL
                SELECT h.root_id, child.id
                FROM hierarchy h
                JOIN document_nodes child
                    ON child.parent_id = h.node_id
            )
            SELECT DISTINCT
                c.id, c.document_id, c.node_id,
                c.content_type, c.text, c.metadata,
                COALESCE(d.title, d.filename),
                d.filename, n.node_type, n.identifier,
                n.title,
                1 - (e.embedding <=> %s::vector)
                    AS similarity
            FROM hierarchy h
            JOIN chunks c ON c.node_id = h.node_id
            JOIN embeddings e ON e.chunk_id = c.id
            JOIN documents d ON d.id = c.document_id
            LEFT JOIN document_nodes n ON n.id = c.node_id
            -- Exact structure decides eligibility.
            -- Similarity only orders the matching chunks.
            ORDER BY similarity DESC
            LIMIT %s
            """,
            (
                owner_id,
                query,
                query,
                embedding,
                top_k,
            ),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [self._map_search_row(row) for row in rows]

    # Convert a retrieval row into named values.
    def _map_search_row(self, row: tuple) -> dict:
        return {
            "chunk_id": str(row[0]),
            "document_id": str(row[1]),
            "node_id": (
                str(row[2]) if row[2] is not None else None
            ),
            "content_type": row[3],
            "text": row[4],
            "metadata": row[5],
            "document_title": row[6],
            "document_name": row[7],
            "node_type": row[8],
            "identifier": row[9],
            "node_title": row[10],
            "similarity": float(row[11]),
        }

    # Store document analysis.
    def add_document_analysis(self, analysis) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT INTO document_analysis (
                document_id, owner_id, file_hash,
                processing_status,
                recommended_chunk_size,
                page_mapping_version,
                chunking_version,
                embedding_version,
                created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            """,
            (
                analysis.document_id,
                analysis.owner_id,
                analysis.file_hash,
                analysis.processing_status,
                analysis.recommended_chunk_size,
                analysis.page_mapping_version,
                analysis.chunking_version,
                analysis.embedding_version,
                analysis.created_at,
                analysis.updated_at,
            ),
        )
        self.connection.commit()
        cursor.close()

    # Load analysis for one owner and file hash.
    def get_document_analysis(
        self,
        owner_id: str,
        file_hash: str,
    ) -> DocumentAnalysis | None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT
                document_id, owner_id, file_hash,
                processing_status,
                recommended_chunk_size,
                created_at, updated_at,
                page_mapping_version,
                chunking_version,
                embedding_version
            FROM document_analysis
            WHERE owner_id = %s AND file_hash = %s
            LIMIT 1
            """,
            (owner_id, file_hash),
        )
        row = cursor.fetchone()
        cursor.close()

        if row is None:
            return None

        return DocumentAnalysis(
            document_id=str(row[0]),
            owner_id=row[1],
            file_hash=row[2],
            processing_status=row[3],
            recommended_chunk_size=row[4],
            created_at=row[5],
            updated_at=row[6],
            page_mapping_version=row[7],
            chunking_version=row[8],
            embedding_version=row[9],
        )

    # Update only the processing status.
    def update_document_status(
        self,
        document_id: str,
        processing_status: str,
    ) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            UPDATE document_analysis
            SET processing_status = %s,
                updated_at = NOW()
            WHERE document_id = %s
            """,
            (processing_status, document_id),
        )
        self.connection.commit()
        cursor.close()

    # Update the recommended legacy chunk size.
    def update_recommended_chunk_size(
        self,
        document_id: str,
        recommended_chunk_size: int,
    ) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            UPDATE document_analysis
            SET recommended_chunk_size = %s,
                updated_at = NOW()
            WHERE document_id = %s
            """,
            (recommended_chunk_size, document_id),
        )
        self.connection.commit()
        cursor.close()

    # Update analysis after legacy size calculation.
    def update_document_analysis(
        self,
        document_id: str,
        recommended_chunk_size: int,
        processing_status: str,
    ) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            UPDATE document_analysis
            SET recommended_chunk_size = %s,
                processing_status = %s,
                updated_at = NOW()
            WHERE document_id = %s
            """,
            (
                recommended_chunk_size,
                processing_status,
                document_id,
            ),
        )
        self.connection.commit()
        cursor.close()

    # Update one processing logic version.
    def _update_version(
        self,
        document_id: str,
        column_name: str,
        version: int,
    ) -> None:
        allowed_columns = {
            "page_mapping_version",
            "chunking_version",
            "embedding_version",
        }

        if column_name not in allowed_columns:
            raise ValueError("Unknown version column.")

        cursor = self.connection.cursor()
        query = sql.SQL(
            """
            UPDATE document_analysis
            SET {} = %s, updated_at = NOW()
            WHERE document_id = %s
            """
        ).format(
            sql.Identifier(column_name)
        )
        cursor.execute(query, (version, document_id))
        self.connection.commit()
        cursor.close()

    def update_page_mapping_version(
        self,
        document_id: str,
        version: int,
    ) -> None:
        self._update_version(
            document_id,
            "page_mapping_version",
            version,
        )

    def update_chunking_version(
        self,
        document_id: str,
        version: int,
    ) -> None:
        self._update_version(
            document_id,
            "chunking_version",
            version,
        )

    def update_embedding_version(
        self,
        document_id: str,
        version: int,
    ) -> None:
        self._update_version(
            document_id,
            "embedding_version",
            version,
        )
