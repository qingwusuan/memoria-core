"""运行时设置：模型供应商与叙事视角。

这些是"用户随时会改"的选项，不该只存在于 .env 里。设置落在
`data/settings.json`（原子写），环境变量只作为默认值与兜底：

- provider：用哪家的 key 与模型。只允许 key 已配置的供应商，切换立即生效。
- narrative_person：`third`（小说体）或 `first`（角色以"我"说话）。
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Optional

from backend import config

ALLOWED_PROVIDERS = ("deepseek", "kimi")
ALLOWED_PERSONS = ("first", "third")

_PROVIDER_LABELS = {"deepseek": "DeepSeek", "kimi": "Kimi（Moonshot）"}
_lock = threading.Lock()


def _path() -> Path:
    return config.DATA_DIR / "settings.json"


def _defaults() -> dict:
    return {
        "provider": None,  # None = 跟随 .env
        "narrative_person": "third",
    }


def load() -> dict:
    data = _defaults()
    try:
        with _path().open("r", encoding="utf-8") as f:
            stored = json.load(f)
        if isinstance(stored, dict):
            data.update({k: stored[k] for k in data if k in stored})
    except (OSError, json.JSONDecodeError):
        pass
    if data["narrative_person"] not in ALLOWED_PERSONS:
        data["narrative_person"] = "third"
    if data["provider"] not in ALLOWED_PROVIDERS:
        data["provider"] = None
    return data


def save(patch: dict) -> dict:
    """合并并持久化设置；非法值直接拒绝（抛 ValueError）。"""
    with _lock:
        data = load()
        if "provider" in patch:
            provider = patch["provider"]
            if provider in ("", None):
                data["provider"] = None
            elif provider not in ALLOWED_PROVIDERS:
                raise ValueError(f"不支持的供应商：{provider}")
            elif not has_key(provider):
                raise ValueError(f"{_PROVIDER_LABELS.get(provider, provider)} 未配置 API Key")
            else:
                data["provider"] = provider

        if "narrative_person" in patch:
            person = patch["narrative_person"]
            if person not in ALLOWED_PERSONS:
                raise ValueError("叙事视角只能是 first 或 third")
            data["narrative_person"] = person

        tmp = _path().with_suffix(".json.tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _path())
        return data


def get(key: str):
    return load().get(key)


def has_key(provider: str) -> bool:
    if provider == "kimi":
        return bool(config.KIMI_API_KEY)
    if provider == "deepseek":
        return bool(config.LLM_API_KEY)
    return False


def effective_provider() -> str:
    """当前实际使用的供应商：设置优先，其次 .env，最后回退 deepseek。"""
    chosen: Optional[str] = get("provider")
    if chosen and has_key(chosen):
        return chosen
    configured = config.LLM_PROVIDER if config.LLM_PROVIDER in ALLOWED_PROVIDERS else "deepseek"
    if has_key(configured):
        return configured
    for provider in ALLOWED_PROVIDERS:
        if has_key(provider):
            return provider
    return configured


def model_of(provider: str) -> str:
    return config.KIMI_MODEL if provider == "kimi" else config.LLM_MODEL


def available_providers() -> list[dict]:
    return [
        {
            "id": provider,
            "label": _PROVIDER_LABELS[provider],
            "model": model_of(provider),
            "has_key": has_key(provider),
        }
        for provider in ALLOWED_PROVIDERS
    ]


def public_view() -> dict:
    """给前端的完整状态。"""
    data = load()
    provider = effective_provider()
    return {
        "provider": provider,
        "provider_from_env": data["provider"] is None,
        "model": model_of(provider),
        "narrative_person": data["narrative_person"],
        "providers": available_providers(),
    }
