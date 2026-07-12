from app.services.sync_service import _normalize_lake_label


def test_normalize_lake_label_removes_macron_from_state_name():
    assert _normalize_lake_label("Bihār") == "Bihar"
