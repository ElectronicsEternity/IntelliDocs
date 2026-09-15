from unittest.mock import Mock

from app.indexing.hierarchy_importer import HierarchyImporter


def test_hierarchy_import_is_scoped_to_authenticated_owner(monkeypatch):
    importer = HierarchyImporter(db=object())
    repository = Mock(owner_id=None)
    importer.repository = repository
    monkeypatch.setattr(importer, "build_nodes", lambda **_kwargs: [])

    importer.import_hierarchy(
        document_id="document-a",
        hierarchy={},
        owner_id="user-a",
    )

    assert repository.owner_id == "user-a"
    repository.bulk_create.assert_called_once_with([])
