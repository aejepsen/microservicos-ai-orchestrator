"""GraphRAG: carrega artefato pré-gerado de comunidades (Louvain offline).

O serviço NÃO gera comunidades — serve o artefato. Ausente → GraphRAG off.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class CommunityStore:
    def __init__(self, models_dir: str) -> None:
        self._path = Path(models_dir) / "communities.json"
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    @property
    def available(self) -> bool:
        return bool(self._data)

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            return
        for c in raw.get("communities", []):
            self._data[str(c["id"])] = c

    def get(self, cid: str) -> dict[str, Any] | None:
        return self._data.get(cid)
