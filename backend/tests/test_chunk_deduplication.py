from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

from app.models.chunk import Chunk
from app.models.chunk_metadata import TextChunkMetadata, TableChunkMetadata, TableField
from app.rag.chunk_deduplicator import deduplicate_chunks
from app.indexing.document_indexer import DocumentIndexer
from app.constants import DOCUMENT_STATUS_NEW


def chunk(identity='first', text='Exact content', page=1):
    metadata = TextChunkMetadata((page,), ('Section A',), page, 0, page, 20)
    return Chunk(identity, 'doc', 'node-a', 9, page, 'text', text, 2, metadata)


def test_exact_duplicate_preserves_first_citation_and_resequences():
    first = chunk()
    duplicate = replace(first, id='duplicate', node_id='node-b',
                        metadata=replace(first.metadata, hierarchy_path=('Section B',)))
    last = chunk('last', 'Different content')
    result = deduplicate_chunks([first, duplicate, last])
    assert result == [first, last]
    assert first.metadata.hierarchy_path == ('Section A',)
    assert [c.chunk_number for c in result] == [1, 2]


def test_distinct_source_locations_documents_and_wording_are_preserved():
    first = chunk()
    variants = [chunk('other-page', page=2),
                replace(first, id='other-offset', metadata=replace(first.metadata, start_character=30)),
                replace(first, id='other-doc', document_id='another-doc'),
                chunk('case', 'exact content'), chunk('space', 'Exact  content')]
    assert len(deduplicate_chunks([first, *variants])) == 6
    assert deduplicate_chunks([]) == []


def test_tables_deduplicate_only_with_matching_geometry():
    metadata = TableChunkMetadata((1,), 1, 1, 1, [TableField('Value', 1, 1, 1, 1, 1, 1)])
    first = replace(chunk(), content_type='table', metadata=metadata)
    duplicate = replace(first, id='duplicate')
    other = replace(first, id='other-table', metadata=replace(metadata, table_number=2))
    assert deduplicate_chunks([first, duplicate, other]) == [first, other]


def test_indexer_deduplicates_before_persistence_and_embedding():
    indexer = DocumentIndexer.__new__(DocumentIndexer)
    indexer.vector_store = Mock()
    indexer.embedder = Mock()
    indexer.get_document_analysis = Mock(return_value=SimpleNamespace(
        processing_status=DOCUMENT_STATUS_NEW, recommended_chunk_size=100))
    first = chunk()
    indexer._build_chunks = Mock(return_value=[first, replace(first, id='duplicate')])
    indexer.update_document_status = Mock()
    document = SimpleNamespace(id='doc', owner_id='owner', file_hash='hash')
    indexer.index_document(document, nodes=[])
    indexer.vector_store.add_chunk.assert_called_once_with(first, 'owner')
    indexer.embedder.generate_embedding.assert_called_once_with(
        first.text, user_id='owner', document_id='doc', activity='chunk_embedding')
    indexer.vector_store.add_embedding.assert_called_once()
