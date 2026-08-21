"""S3 cleanup helpers."""

from __future__ import annotations

from app.modules.diagnose.services.s3_cleanup import _UUID_PREFIX_RE


class TestUuidPrefixPattern:
    def test_matches_project_uuid(self):
        assert _UUID_PREFIX_RE.match("c5581564-0a41-4140-b46d-501bb73eb96a")

    def test_rejects_cog_filename(self):
        assert not _UUID_PREFIX_RE.match("IndiaSat_LULC_24_25.cog.tif")

    def test_rejects_watersheds_key(self):
        assert not _UUID_PREFIX_RE.match("watersheds.fbg")
