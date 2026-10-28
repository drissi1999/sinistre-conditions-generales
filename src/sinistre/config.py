"""Configuration par variables d'environnement (voir .env.example)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.getenv("SINISTRE_DATA_DIR", ROOT / "data"))
DB_PATH = Path(os.getenv("SINISTRE_DB", DATA_DIR / "contracts.db"))
CACHE_DIR = Path(os.getenv("SINISTRE_CACHE_DIR", DATA_DIR / "cache"))

# Fournisseur LLM : "openai_compatible" couvre OpenAI, Mistral (api.mistral.ai/v1), les routeurs
# et les modèles auto-hébergés (vLLM, Ollama) ; "anthropic" utilise le SDK natif.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai_compatible")
LLM_BASE_URL = os.getenv("LLM_BASE_URL") or None
LLM_MODEL = os.getenv("LLM_MODEL", "mistral-small-latest")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "300"))  # les modèles gratuits peuvent mettre > 2 min

EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
