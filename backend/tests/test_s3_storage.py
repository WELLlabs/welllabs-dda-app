"""S3 path helpers for diagnose project storage."""

from __future__ import annotations

from app.shared import s3_storage


class TestDiagnoseS3Paths:
    PROJECT_ID = "c5581564-0a41-4140-b46d-501bb73eb96a"
    FILENAME = "abc.jpg"

    def test_project_prefix_under_diagnose(self, monkeypatch):
        monkeypatch.setattr("app.shared.s3_storage.settings.diagnose_s3_prefix", "diagnose")
        assert s3_storage.project_prefix(self.PROJECT_ID) == f"diagnose/{self.PROJECT_ID}/"

    def test_media_key_under_diagnose(self, monkeypatch):
        monkeypatch.setattr("app.shared.s3_storage.settings.diagnose_s3_prefix", "diagnose")
        assert (
            s3_storage.media_key(self.PROJECT_ID, self.FILENAME)
            == f"diagnose/{self.PROJECT_ID}/media/{self.FILENAME}"
        )

    def test_packages_prefix_under_diagnose(self, monkeypatch):
        monkeypatch.setattr("app.shared.s3_storage.settings.diagnose_s3_prefix", "diagnose")
        assert s3_storage.packages_prefix(self.PROJECT_ID) == f"diagnose/{self.PROJECT_ID}/packages/"

    def test_canonicalize_legacy_media_key(self, monkeypatch):
        monkeypatch.setattr("app.shared.s3_storage.settings.diagnose_s3_prefix", "diagnose")
        legacy = f"{self.PROJECT_ID}/media/{self.FILENAME}"
        assert s3_storage.canonicalize_diagnose_key(legacy) == f"diagnose/{legacy}"

    def test_legacy_key_from_canonical(self, monkeypatch):
        monkeypatch.setattr("app.shared.s3_storage.settings.diagnose_s3_prefix", "diagnose")
        canonical = f"diagnose/{self.PROJECT_ID}/media/{self.FILENAME}"
        assert s3_storage.legacy_key_from_canonical(canonical) == f"{self.PROJECT_ID}/media/{self.FILENAME}"

    def test_media_key_pattern_accepts_both_layouts(self, monkeypatch):
        monkeypatch.setattr("app.shared.s3_storage.settings.diagnose_s3_prefix", "diagnose")
        pattern = s3_storage.media_key_pattern()
        assert pattern.match(f"{self.PROJECT_ID}/media/{self.FILENAME}")
        assert pattern.match(f"diagnose/{self.PROJECT_ID}/media/{self.FILENAME}")

    def test_shared_layer_keys_unchanged(self, monkeypatch):
        monkeypatch.setattr("app.shared.s3_storage.settings.diagnose_s3_prefix", "diagnose")
        assert s3_storage.canonicalize_diagnose_key("rasters/dem_india.tif") == "rasters/dem_india.tif"
