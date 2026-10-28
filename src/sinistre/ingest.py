"""Registre des contrats (data/contracts.yaml) et empreinte des fichiers sources.

L'empreinte SHA-256 du PDF est la clé d'idempotence : un contrat déjà ingéré avec la même
empreinte n'est ni re-parsé ni ré-extrait. Une nouvelle édition = nouvelle empreinte = ré-ingestion.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import DATA_DIR


@dataclass
class ContractSource:
    contract_id: str
    insurer: str
    product: str
    edition: str
    source_url: str
    path: Path
    profile: dict

    @property
    def meta(self) -> dict:
        return {"contract_id": self.contract_id, "insurer": self.insurer, "product": self.product,
                "edition": self.edition, "source_url": self.source_url}


def load_registry(path: Path | None = None) -> list[ContractSource]:
    path = path or DATA_DIR / "contracts.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [ContractSource(c["contract_id"], c["insurer"], c.get("product", ""), str(c.get("edition", "")),
                           c.get("source_url", ""), path.parent / c["file"], c.get("profile", {}))
            for c in raw["contracts"]]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
