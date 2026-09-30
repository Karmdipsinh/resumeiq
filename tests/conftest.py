import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("RESUMEIQ_ENV", "development")

from app import create_app


@pytest.fixture()
def app(tmp_path):
    upload_dir = tmp_path / "uploads"
    application = create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "test.db"),
        "UPLOAD_FOLDER": str(upload_dir),
    })
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()
