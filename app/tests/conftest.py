import pytest

from app.db import Persistence
from app.samsung.mock import MockFrameClient
from app.services.watcher import AutomationWatcher


@pytest.fixture
async def system(tmp_path):
    db = Persistence(tmp_path)
    c = MockFrameClient()
    w = AutomationWatcher(db, c)
    await w.refresh_capabilities()
    yield db, c, w
    await w.stop()
    db.close()
