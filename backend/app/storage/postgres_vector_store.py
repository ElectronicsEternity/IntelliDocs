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
    CURRENT_ROUTING_PROFILE_VERSION,
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
                id, owner_id, user_id, filename, original_filename, title,
                file_hash, uploaded_at, created_at, updated_at,
                document_type, language, file_size, file_extension,
                processing_status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, 'uploaded')
            """,
            (
                document.id,
                document.owner_id,
                document.owner_id,
                document.filename,
                document.filename,
                document.title,
                document.file_hash,
                document.uploaded_at,
                document.uploaded_at,
                document.uploaded_at,
                document.document_type,
                document.language,
                document.file_size,
                document.file_extension,
            ),
        )
        self.connection.commit()
        cursor.close()

    def commit(self) -> None:
        self.connection.commit()

    # Store one chunk with its retrieval structure.
    def add_chunk(self, chunk, owner_id: str) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT INTO chunks (
                id, document_id, user_id, node_id,
                chunk_number, page_number,
                content_type, token_count,
                text, metadata
            )
            SELECT %s, %s, %s, %s, %s,
                   %s, %s, %s, %s, %s
            WHERE EXISTS (
                SELECT 1 FROM documents
                WHERE id = %s AND user_id = %s
            )
            """,
            (
                chunk.id,
                chunk.document_id,
                owner_id,
                chunk.node_id,
                chunk.chunk_number,
                chunk.page_number,
                chunk.content_type,
                chunk.token_count,
                chunk.text,
                Jsonb(asdict(chunk.metadata)),
                chunk.document_id,
                owner_id,
            ),
        )
        cursor.close()

    def close(self) -> None:
        self.connection.close()

    def add_embedding(
        self,
        chunk_id,
        embedding,
        owner_id: str,
    ) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT INTO embeddings (chunk_id, user_id, embedding)
            SELECT %s, %s, %s
            WHERE EXISTS (
                SELECT 1 FROM chunks WHERE id = %s AND user_id = %s
            )
            """,
            (chunk_id, owner_id, embedding, chunk_id, owner_id),
        )
        cursor.close()

    # Store one searchable hierarchy-node embedding.
    def add_node_embedding(
        self,
        node_id: str,
        search_text: str,
        embedding,
        owner_id: str,
    ) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT INTO node_embeddings (
                node_id, user_id, search_text, embedding,
                embedding_version
            )
            SELECT %s, %s, %s, %s, %s
            WHERE EXISTS (
                SELECT 1 FROM document_nodes n
                JOIN documents d ON d.id = n.document_id
                WHERE n.id = %s AND d.user_id = %s
            )
            ON CONFLICT (node_id) DO UPDATE
            SET search_text = EXCLUDED.search_text,
                embedding = EXCLUDED.embedding,
                embedding_version = EXCLUDED.embedding_version
            """,
            (
                node_id,
                owner_id,
                search_text,
                embedding,
                CURRENT_EMBEDDING_VERSION,
                node_id,
                owner_id,
            ),
        )
        cursor.close()

    # Persist the description embedding and hierarchy-title topics used only
    # for document selection before normal chunk retrieval begins.
    def upsert_document_routing_profile(
        self,
        *,
        document_id: str,
        owner_id: str,
        description: str,
        description_embedding,
        topics: list[str],
    ) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT INTO document_routing_profiles (
                document_id, user_id, description, description_embedding,
                topics, profile_version, updated_at
            )
            SELECT %s, %s, %s, %s, %s, %s, now()
            WHERE EXISTS (
                SELECT 1 FROM documents WHERE id = %s AND user_id = %s
            )
            ON CONFLICT (document_id) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                description = EXCLUDED.description,
                description_embedding = EXCLUDED.description_embedding,
                topics = EXCLUDED.topics,
                profile_version = EXCLUDED.profile_version,
                updated_at = now()
            """,
            (
                document_id,
                owner_id,
                description,
                description_embedding,
                Jsonb(topics),
                CURRENT_ROUTING_PROFILE_VERSION,
                document_id,
                owner_id,
            ),
        )
        cursor.close()

    # Return every owned document with its routing signals. A left join keeps
    # older documents searchable until the user reprocesses them.
    def list_document_routing_candidates(self, *, owner_id: str, embedding) -> list[dict]:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT
                d.id,
                COALESCE(d.title, d.filename),
                d.filename,
                COALESCE(rp.topics, '[]'::jsonb),
                CASE
                    WHEN rp.description_embedding IS NULL THEN 0.0
                    ELSE 1 - (rp.description_embedding <=> %s::vector)
                END AS description_similarity
            FROM documents d
            LEFT JOIN document_routing_profiles rp
                ON rp.document_id = d.id
               AND rp.user_id = d.user_id
               AND rp.profile_version = %s
            WHERE d.user_id = %s
              AND d.processing_status = 'ready'
            ORDER BY d.created_at DESC
            """,
            (embedding, CURRENT_ROUTING_PROFILE_VERSION, owner_id),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [
            {
                "document_id": str(row[0]),
                "document_title": row[1],
                "filename": row[2],
                "topics": row[3],
                "description_similarity": float(row[4] or 0.0),
            }
            for row in rows
        ]

    # Find chunks by embedding similarity.
    def search(
        self,
        owner_id: str,
        embedding,
        top_k: int = TOP_K,
        document_id: str | None = None,
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
            WHERE d.user_id = %s
            AND (%s::uuid IS NULL OR d.id = %s::uuid)
            AND 1 - (e.embedding <=> %s::vector) >= %s
            ORDER BY similarity DESC
            LIMIT %s
            """,
            (
                embedding,
                owner_id,
                document_id,
                document_id,
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
        document_id: str | None = None,
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
                WHERE d.user_id = %s
                AND (%s::uuid IS NULL OR d.id = %s::uuid)
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
            WHERE d.user_id = %s
            AND (%s::uuid IS NULL OR d.id = %s::uuid)
            AND 1 - (e.embedding <=> %s::vector) >= %s
            ORDER BY rn.node_similarity DESC, similarity DESC
            LIMIT %s
            """,
            (
                embedding,
                owner_id,
                document_id,
                document_id,
                CURRENT_EMBEDDING_VERSION,
                embedding,
                SIMILARITY_THRESHOLD,
                top_k,
                embedding,
                owner_id,
                document_id,
                document_id,
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
        document_id: str | None = None,
    ) -> list[dict]:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            WITH RECURSIVE candidate_nodes AS (
                -- A bilingual or multi-document corpus can contain several
                -- nodes with the same structural identifier. Measure every
                -- exact candidate before choosing one version of each anchor.
                SELECT
                    n.id,
                    lower(replace(n.node_type, '_', ' ')) AS anchor_type,
                    btrim(
                        regexp_replace(
                            lower(btrim(n.identifier)),
                            '[^[:alnum:]]+',
                            ' ',
                            'g'
                        )
                    ) AS anchor_identifier,
                    1 - (
                        ne.embedding <=> %s::vector
                    ) AS anchor_similarity
                FROM document_nodes n
                JOIN documents d ON d.id = n.document_id
                JOIN node_embeddings ne ON ne.node_id = n.id
                WHERE d.user_id = %s
                AND (%s::uuid IS NULL OR d.id = %s::uuid)
                AND ne.embedding_version = %s
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
            ), matched_nodes AS (
                -- Keep the best language/document version for each distinct
                -- identifier mentioned in the question. Multiple explicit
                -- anchors, such as Sections 4 and 6, therefore remain valid.
                SELECT id, anchor_similarity
                FROM (
                    SELECT
                        candidate_nodes.*,
                        row_number() OVER (
                            PARTITION BY anchor_type, anchor_identifier
                            ORDER BY anchor_similarity DESC
                        ) AS anchor_rank
                    FROM candidate_nodes
                ) ranked_candidates
                WHERE anchor_rank = 1
            ), hierarchy AS (
                -- Preserve depth-first hierarchy order so the complete
                -- anchor is presented as one coherent evidence bundle.
                SELECT
                    mn.id AS root_id,
                    mn.id AS node_id,
                    mn.anchor_similarity,
                    ARRAY[n.sequence_no] AS hierarchy_order
                FROM matched_nodes mn
                JOIN document_nodes n ON n.id = mn.id
                UNION ALL
                SELECT
                    h.root_id,
                    child.id,
                    h.anchor_similarity,
                    h.hierarchy_order || child.sequence_no
                FROM hierarchy h
                JOIN document_nodes child
                    ON child.parent_id = h.node_id
            )
            SELECT
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
            WHERE d.user_id = %s
            AND (%s::uuid IS NULL OR d.id = %s::uuid)
            -- Exact structure decides eligibility.
            -- Hierarchy order keeps the anchor and all children together;
            -- semantic similarity was already used to choose the best anchor.
            ORDER BY
                h.anchor_similarity DESC,
                h.hierarchy_order,
                c.chunk_number
            LIMIT %s
            """,
            (
                embedding,
                owner_id,
                document_id,
                document_id,
                CURRENT_EMBEDDING_VERSION,
                query,
                query,
                embedding,
                owner_id,
                document_id,
                document_id,
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
                document_id, owner_id, user_id, file_hash,
                processing_status,
                recommended_chunk_size,
                page_mapping_version,
                chunking_version,
                embedding_version,
                created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            """,
            (
                analysis.document_id,
                analysis.owner_id,
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
            WHERE user_id = %s AND file_hash = %s
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
        owner_id: str,
    ) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            UPDATE document_analysis
            SET processing_status = %s,
                updated_at = NOW()
            WHERE document_id = %s AND user_id = %s
            """,
            (processing_status, document_id, owner_id),
        )
        self.connection.commit()
        cursor.close()

    # Update the recommended legacy chunk size.
    def update_recommended_chunk_size(
        self,
        document_id: str,
        recommended_chunk_size: int,
        owner_id: str,
    ) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            UPDATE document_analysis
            SET recommended_chunk_size = %s,
                updated_at = NOW()
            WHERE document_id = %s AND user_id = %s
            """,
            (recommended_chunk_size, document_id, owner_id),
        )
        self.connection.commit()
        cursor.close()

    # Update analysis after legacy size calculation.
    def update_document_analysis(
        self,
        document_id: str,
        recommended_chunk_size: int,
        processing_status: str,
        owner_id: str,
    ) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            UPDATE document_analysis
            SET recommended_chunk_size = %s,
                processing_status = %s,
                updated_at = NOW()
            WHERE document_id = %s AND user_id = %s
            """,
            (
                recommended_chunk_size,
                processing_status,
                document_id,
                owner_id,
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
        owner_id: str,
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
            WHERE document_id = %s AND user_id = %s
            """
        ).format(
            sql.Identifier(column_name)
        )
        cursor.execute(query, (version, document_id, owner_id))
        self.connection.commit()
        cursor.close()

    def update_page_mapping_version(
        self,
        document_id: str,
        version: int,
        owner_id: str,
    ) -> None:
        self._update_version(
            document_id,
            "page_mapping_version",
            version,
            owner_id,
        )

    def update_chunking_version(
        self,
        document_id: str,
        version: int,
        owner_id: str,
    ) -> None:
        self._update_version(
            document_id,
            "chunking_version",
            version,
            owner_id,
        )

    def update_embedding_version(
        self,
        document_id: str,
        version: int,
        owner_id: str,
    ) -> None:
        self._update_version(
            document_id,
            "embedding_version",
            version,
            owner_id,
        )
