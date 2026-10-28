"""Appels LLM : un seul point d'entrée, sortie JSON validée par Pydantic, cache disque.

- Le cache (clé = modèle + prompts) rend l'extraction idempotente et l'évaluation reproductible.
- En cas de JSON invalide, l'erreur de validation est renvoyée au modèle (2 essais maximum).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from . import config

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


def _cache_path(key: str):
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return config.CACHE_DIR / f"{key}.json"


def _raw_completion(system: str, user: str, max_tokens: int) -> str:
    if not config.LLM_API_KEY:
        raise LLMError("LLM_API_KEY absent : renseignez .env (voir .env.example).")
    if config.LLM_PROVIDER == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=config.LLM_API_KEY, timeout=config.LLM_TIMEOUT)
        msg = client.messages.create(model=config.LLM_MODEL, max_tokens=max_tokens, temperature=0,
                                     system=system, messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in msg.content if b.type == "text")
    from openai import OpenAI
    client = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL, timeout=config.LLM_TIMEOUT)
    resp = client.chat.completions.create(
        model=config.LLM_MODEL, temperature=0, max_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    return resp.choices[0].message.content or ""


def _extract_json(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    end = max(text.rfind("}"), text.rfind("]"))
    if start < 0 or end < start:
        raise LLMError(f"Pas de JSON dans la réponse : {text[:200]!r}")
    return text[start:end + 1]


def complete_json(system: str, user: str, schema: type[T], max_tokens: int = 4000,
                  use_cache: bool = True) -> T:
    key = hashlib.sha256(json.dumps([config.LLM_MODEL, system, user, schema.__name__]).encode()).hexdigest()[:32]
    path = _cache_path(key)
    if use_cache and path.exists():
        return schema.model_validate_json(path.read_text(encoding="utf-8"))

    prompt, last_err = user, None
    for _ in range(2):
        raw = _raw_completion(system, prompt, max_tokens)
        try:
            obj = schema.model_validate_json(_extract_json(raw))
            path.write_text(obj.model_dump_json(indent=1), encoding="utf-8")
            return obj
        except (ValidationError, LLMError, ValueError) as e:
            last_err = e
            prompt = (f"{user}\n\nTa réponse précédente était invalide :\n{str(e)[:1500]}\n"
                      "Réponds uniquement avec un objet JSON valide conforme au schéma.")
    raise LLMError(f"Réponse LLM invalide après 2 essais : {last_err}")
