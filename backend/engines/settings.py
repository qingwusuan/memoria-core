"""运行时设置与 API Key 存储。

- 偏好（当前供应商、默认叙事视角）落在 `data/settings.json`；
- API Key 落在 `data/credentials.json`，**不改 `.env`**；环境变量仍作为兜底；
- 两者都是原子写，不需要重启即可生效。

设置页只负责导入 Key；「用哪家」属于对话时的运行时选择，不放设置里。
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


def _cred_path() -> Path:
    return config.DATA_DIR / "credentials.json"


def _defaults() -> dict:
    return {
        "provider": None,  # None = 跟随 .env
        "narrative_person": "third",
    }


def _read_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load() -> dict:
    data = _defaults()
    stored = _read_json(_path())
    data.update({k: stored[k] for k in data if k in stored})
    if data["narrative_person"] not in ALLOWED_PERSONS:
        data["narrative_person"] = "third"
    if data["provider"] not in ALLOWED_PROVIDERS:
        data["provider"] = None
    return data


def save(patch: dict) -> dict:
    """合并并持久化偏好；非法值直接拒绝（抛 ValueError）。"""
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

        _write_json(_path(), data)
        return data


def get(key: str):
    return load().get(key)


# ---------- API Key ----------

def _load_credentials() -> dict:
    raw = _read_json(_cred_path())
    return {
        k: v for k, v in raw.items()
        if k in ALLOWED_PROVIDERS and isinstance(v, str) and v.strip()
    }


def get_key(provider: str) -> str:
    """优先用设置页导入的 Key，其次回落到环境变量。"""
    stored = _load_credentials().get(provider)
    if stored:
        return stored
    if provider == "kimi":
        return config.KIMI_API_KEY or ""
    return config.LLM_API_KEY or ""


def set_key(provider: str, key: str) -> bool:
    """导入 / 更新 Key；传空字符串表示清除。返回是否已配置。"""
    if provider not in ALLOWED_PROVIDERS:
        raise ValueError(f"不支持的供应商：{provider}")
    with _lock:
        creds = _load_credentials()
        cleaned = (key or "").strip()
        if cleaned:
            creds[provider] = cleaned
        else:
            creds.pop(provider, None)
        _write_json(_cred_path(), creds)
    return bool(get_key(provider))


def mask_key(key: str) -> str:
    """只回显首尾，避免把完整 Key 传给前端。"""
    key = (key or "").strip()
    if not key:
        return ""
    if len(key) <= 8:
        return "…"
    return f"{key[:3]}…{key[-4:]}"


def has_key(provider: str) -> bool:
    return bool(get_key(provider))


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
            "masked": mask_key(get_key(provider)),
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
