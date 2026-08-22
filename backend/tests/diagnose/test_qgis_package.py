"""QGIS Docker packaging prerequisites."""

from __future__ import annotations

import shutil
from unittest.mock import patch

import pytest

from app.modules.diagnose.services import qgis_package


def test_require_docker_raises_when_missing():
    with patch.object(shutil, "which", return_value=None):
        with pytest.raises(RuntimeError, match="Docker is not installed"):
            qgis_package._require_docker()


def test_require_docker_ok_when_present():
    with patch.object(shutil, "which", return_value="/usr/bin/docker"):
        qgis_package._require_docker()
