"""One independent runtime and data directory per television."""

import asyncio
import re
import uuid
from dataclasses import dataclass

from app.db import Persistence
from app.samsung.client import SamsungClient
from app.samsung.mock import MockFrameClient
from app.services.watcher import AutomationWatcher


@dataclass
class Television:
    db: Persistence
    watcher: AutomationWatcher


class TelevisionManager:
    def __init__(self, directory, mock):
        self.directory, self.mock = directory, mock
        self.registry = Persistence(directory)
        self.runtimes = {}
        self.lock = asyncio.Lock()

    async def start(self):
        if not self.registry.get("televisions", "primary"):
            self.registry.put("televisions", "primary", {"name": "My Frame"})
        for identifier in self.registry.all("televisions"):
            if identifier != "primary" and not re.fullmatch(r"[a-f0-9]{32}", identifier):
                raise ValueError("Invalid stored television identifier")
            await self.open(identifier)

    async def open(self, identifier):
        db = (
            self.registry
            if identifier == "primary"
            else Persistence(self.directory / "tvs" / identifier)
        )
        ip = db.get("config", "tv_ip")
        client = (
            MockFrameClient()
            if self.mock
            else (SamsungClient(ip, db.directory / "tokens") if ip else None)
        )
        watcher = AutomationWatcher(db, client)
        runtime = Television(db, watcher)
        self.runtimes[identifier] = runtime
        if self.mock:
            await watcher.refresh_capabilities()
        watcher.task = asyncio.create_task(watcher.run())
        return runtime

    async def add(self, name):
        async with self.lock:
            if len(self.runtimes) >= 16:
                raise ValueError("This installation supports up to 16 televisions")
            identifier = uuid.uuid4().hex
            self.registry.put("televisions", identifier, {"name": self.name(name)})
            await self.open(identifier)
            return identifier

    @staticmethod
    def name(value):
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 80:
            raise ValueError("Give the TV a name between 1 and 80 characters")
        return value.strip()

    def list(self):
        names = self.registry.all("televisions")
        return [
            {
                "id": identifier,
                "name": names[identifier]["name"],
                "connected": runtime.watcher.state.get("connected", False),
                "model": runtime.db.get("config", "device", {}).get("model", ""),
                "automation": runtime.watcher.settings["automation"],
            }
            for identifier, runtime in self.runtimes.items()
        ]

    async def close(self):
        for runtime in self.runtimes.values():
            await runtime.watcher.stop()
            if runtime.db is not self.registry:
                runtime.db.close()
        self.registry.close()
