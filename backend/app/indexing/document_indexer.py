# ========================================
# File: document_indexer.py
# ========================================

from datetime import datetime, timezone

from app.constants import (
    CURRENT_CHUNKING_VERSION,
    CURRENT_EMBEDDING_VERSION,
    DOCUMENT_STATUS_NEW,
    DOCUMENT_STATUS_PROFILED,
    DOCUMENT_STATUS_ANALYZED,
    DOCUMENT_STATUS_CHUNKED,
    DOCUMENT_STATUS_EMBEDDED,
    DOCUMENT_STATUS_INDEXED,
    DOCUMENT_STATUS_FAILED
)

from app.models.document_analysis import DocumentAnalysis

from app.indexing.node_scope_extractor import (
    NodeScopeExtractor,
)
from app.indexing.table_node_linker import TableNodeLinker

from app.rag.chunk_analyzer import ChunkAnalyzer
from app.rag.chunker import Chunker
from app.rag.embedder import Embedder
from app.rag.tokenizer import Tokenizer

from app.storage.postgres_vector_store import (
    PostgresVectorStore,
)


class DocumentIndexer:

    def __init__(self):

        self.chunker = Chunker()
        self.embedder = Embedder()
        self.chunk_analyzer = ChunkAnalyzer()
        self.tokenizer = Tokenizer()
        self.vector_store = PostgresVectorStore()
        self.scope_extractor = NodeScopeExtractor()
        self.table_node_linker = TableNodeLinker()


    def get_document_analysis(
        self,
        owner_id: str,
        file_hash: str
    ):
        return (
            self.vector_store
            .get_document_analysis(
                owner_id,
                file_hash
            )
        )


    # Create the document and its processing record once.
    def register_document(self, document) -> bool:
        analysis = self.get_document_analysis(
            document.owner_id,
            document.file_hash,
        )

        # Do not ingest the same owner and file twice.
        if analysis is not None:
            document.id = analysis.document_id
            print(
                f"Document already registered: "
                f"{document.filename}"
            )
            return False

        now = datetime.now(timezone.utc)
        analysis = DocumentAnalysis(
            document_id=document.id,
            owner_id=document.owner_id,
            file_hash=document.file_hash,
            processing_status=DOCUMENT_STATUS_NEW,
            recommended_chunk_size=None,
            created_at=now,
            updated_at=now,
        )

        # Persist the parent before dependent records.
        self.vector_store.add_document(document)
        self.vector_store.add_document_analysis(analysis)
        return True


    def index_document(
        self,
        document,
        nodes=None,
        normalized_tables=None,
    ):

        analysis = None

        try:

            analysis = (
                self.get_document_analysis(
                    document.owner_id,
                    document.file_hash
                )
            )

            if analysis is None:
                self.register_document(document)
                analysis = self.get_document_analysis(
                    document.owner_id,
                    document.file_hash,
                )

            # Require a valid record before indexing children.
            if analysis is None:
                raise RuntimeError(
                    "Document registration did not complete."
                )

            allowed_statuses = {
                DOCUMENT_STATUS_NEW,
                DOCUMENT_STATUS_PROFILED,
                DOCUMENT_STATUS_ANALYZED,
                "uploaded",
                "processing",
            }

            # Avoid inserting duplicate chunks on later runs.
            if (
                analysis.processing_status
                not in allowed_statuses
            ):
                print(
                    f"Document indexing skipped at status "
                    f"{analysis.processing_status}: "
                    f"{document.filename}"
                )
                return

            recommended_chunk_size = (
                analysis.recommended_chunk_size
            )

            # Analyze page sizes only for legacy chunking.
            if nodes is None:
                page_token_counts = []

                for page in document.pages:
                    page_token_counts.append(
                        self.tokenizer.count_tokens(
                            page.text
                        )
                    )

                recommended_chunk_size = (
                    self.chunk_analyzer.recommend_chunk_size(
                        page_token_counts
                    )
                )
                self.update_document_analysis(
                    document.id,
                    recommended_chunk_size,
                    DOCUMENT_STATUS_ANALYZED,
                    document.owner_id,
                )
            else:
                self.update_document_status(
                    document.id,
                    DOCUMENT_STATUS_ANALYZED,
                    document.owner_id,
                )

            chunks = self._build_chunks(
                document=document,
                nodes=nodes,
                normalized_tables=normalized_tables,
                recommended_chunk_size=(
                    recommended_chunk_size
                ),
            )

            self.update_document_status(
                document.id,
                DOCUMENT_STATUS_CHUNKED,
                document.owner_id,
            )

            for chunk in chunks:

                self.vector_store.add_chunk(
                    chunk,
                    document.owner_id,
                )

                embedding = (
                    self.embedder.generate_embedding(
                        chunk.text
                    )
                )

                self.vector_store.add_embedding(
                    chunk.id,
                    embedding,
                    document.owner_id,
                )

            # Embed hierarchy labels once during ingestion.
            if nodes is not None:
                for node in nodes:
                    search_text = (
                        self._build_node_search_text(node)
                    )

                    if search_text is None:
                        continue

                    node_embedding = (
                        self.embedder.generate_embedding(
                            search_text
                        )
                    )
                    self.vector_store.add_node_embedding(
                        node_id=node.id,
                        search_text=search_text,
                        embedding=node_embedding,
                        owner_id=document.owner_id,
                    )

            self.vector_store.commit()

            # Record the completed chunk logic version.
            self.vector_store.update_chunking_version(
                document.id,
                CURRENT_CHUNKING_VERSION,
                document.owner_id,
            )

            self.update_document_status(
                document.id,
                DOCUMENT_STATUS_EMBEDDED,
                document.owner_id,
            )

            # Record the embedding input version after storage.
            self.vector_store.update_embedding_version(
                document.id,
                CURRENT_EMBEDDING_VERSION,
                document.owner_id,
            )

            self.update_document_status(
                document.id,
                DOCUMENT_STATUS_INDEXED,
                document.owner_id,
            )

        except Exception:
            if analysis:
                self.update_document_status(
                    document.id,
                    DOCUMENT_STATUS_FAILED,
                    document.owner_id,
                )
            raise

    # Combine meaningful node values for embedding.
    def _build_node_search_text(self, node) -> str | None:
        identifier = (node.identifier or "").strip()
        title = (node.title or "").strip()

        # Skip nodes containing only a generic node type.
        if not identifier and not title:
            return None

        node_type = node.node_type.replace("_", " ").strip()
        parts = [node_type]

        if identifier:
            parts.append(identifier)

        if title:
            parts.append(title)

        return " ".join(parts)

    # Select structured chunking when mapped nodes exist.
    def _build_chunks(
        self,
        document,
        nodes,
        normalized_tables,
        recommended_chunk_size,
    ):
        # Retain legacy ingestion until hierarchy is supplied.
        if nodes is None:
            return self.chunker.chunk_document(
                document,
                recommended_chunk_size,
            )

        scopes = self.scope_extractor.extract_node_scopes(
            document=document,
            nodes=nodes,
        )
        chunks = self.chunker.chunk_node_scopes(
            document=document,
            scopes=scopes,
        )

        # Text-only documents need no table processing.
        if not normalized_tables:
            return self.chunker.order_chunks_by_hierarchy(
                chunks=chunks,
                nodes=nodes,
            )

        table_node_ids = self.table_node_linker.link_tables(
            normalized_tables=normalized_tables,
            nodes=nodes,
        )
        table_chunks = self.chunker.chunk_tables(
            document=document,
            normalized_tables=normalized_tables,
            table_node_ids=table_node_ids,
            starting_chunk_number=len(chunks) + 1,
        )
        chunks.extend(table_chunks)
        return self.chunker.order_chunks_by_hierarchy(
            chunks=chunks,
            nodes=nodes,
        )


    def update_document_analysis(
        self,
        document_id: str,
        recommended_chunk_size: int,
        processing_status: str,
        owner_id: str,
    ):

        self.vector_store.update_document_analysis(
            document_id,
            recommended_chunk_size,
            processing_status,
            owner_id,
        )


    def update_document_status(
        self,
        document_id: str,
        processing_status: str,
        owner_id: str,
    ):

        self.vector_store.update_document_status(
            document_id,
            processing_status,
            owner_id,
        )


    # Record the PageMapper logic version just applied.
    def update_page_mapping_version(
        self,
        document_id: str,
        version: int,
        owner_id: str,
    ) -> None:
        self.vector_store.update_page_mapping_version(
            document_id,
            version,
            owner_id,
        )


    # Release the long-lived PostgreSQL connection.
    def close(self) -> None:
        self.vector_store.close()
