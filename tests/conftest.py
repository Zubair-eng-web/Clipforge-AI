import os
import tempfile

# Must be set BEFORE importing the app so tests use throwaway DB + storage
_tmp = tempfile.mkdtemp()
os.environ["CLIPFORGE_DB_PATH"] = os.path.join(_tmp, "test.db")
os.environ["CLIPFORGE_STORAGE_DIR"] = os.path.join(_tmp, "storage")

import pytest
from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c