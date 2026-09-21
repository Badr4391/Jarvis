import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jarvis.config import Config  # noqa: E402
from jarvis.core.context import JarvisContext  # noqa: E402
from jarvis.storage.db import Database  # noqa: E402


@pytest.fixture()
def db(tmp_path) -> Database:
    return Database(tmp_path / "test.db")


@pytest.fixture()
def ctx(tmp_path, db) -> JarvisContext:
    config = Config()
    config.data_dir = tmp_path
    context = JarvisContext(config=config, _db=db)
    return context
