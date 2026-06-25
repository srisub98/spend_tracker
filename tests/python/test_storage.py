"""Provider-partitioned upload storage."""
import os

from services.storage import provider_slug, upload_path


def test_provider_slug_prefers_institution():
    assert provider_slug({"institution": "Capital One", "name": "x", "type": "savings"}) == "capital-one"


def test_provider_slug_fallbacks():
    assert provider_slug({"institution": None, "name": "Chase Checking", "type": "checking"}) == "chase-checking"
    assert provider_slug({"institution": "", "name": "", "type": "credit"}) == "credit"
    assert provider_slug(None) == "other"


def test_upload_path_partitions_by_provider(monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config, "UPLOAD_FOLDER", str(tmp_path))
    p = upload_path("My Stmt.csv", account={"institution": "Amex", "name": "x", "type": "credit"})
    assert p.endswith(os.path.join("amex", "My_Stmt.csv"))
    assert (tmp_path / "amex").is_dir()


def test_upload_path_uses_explicit_bucket(monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config, "UPLOAD_FOLDER", str(tmp_path))
    h = upload_path("pos.csv", bucket="holdings")
    assert h.endswith(os.path.join("holdings", "pos.csv"))
    assert (tmp_path / "holdings").is_dir()
