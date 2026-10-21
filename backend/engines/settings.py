"""运行时设置、供应商注册表与 API Key 存储。

- 内置供应商：deepseek / kimi（地址与模型来自 .env，可被自定义项覆盖）；
- 自定义供应商：任意 OpenAI 兼容接口，存在 `data/providers.json`；
- 偏好（当前用哪家、默认叙事视角）：`data/settings.json`；
- API Key：`data/credentials.json`，按供应商 id 存放，**不写 `.env`**。

设置页只负责导入 Key 与登记供应商；「用哪家」属于对话时的运行时选择。
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Optional

from backend import config

ALLOWED_PERSONS = ("first", "third")

_BUILTIN = {
    "deepseek": {"label": "DeepSeek", "key_env": "DEEPSEEK_API_KEY"},
    "kimi": {"label": "Kimi（Moonshot）", "key_env": "KIMI_API_KEY"},
}
_lock = threading.Lock()


def _path() -> Path:
    return config.DATA_DIR / "settings.json"


def _cred_path() -> Path:
    return config.DATA_DIR / "credentials.json"


def _providers_path() -> Path:
    return config.DATA_DIR / "providers.json"


def _defaults() -> dict:
    return {"provider": None, "narrative_person": "third"}


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


# ---------- 偏好 ----------

def load() -> dict:
    data = _defaults()
    stored = _read_json(_path())
    data.update({k: stored[k] for k in data if k in stored})
    if data["narrative_person"] not in ALLOWED_PERSONS:
        data["narrative_person"] = "third"
    if data["provider"] and not provider_config(data["provider"]):
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
            elif not provider_config(provider):
                raise ValueError(f"未登记的供应商：{provider}")
            elif not has_key(provider):
                raise ValueError(f"{provider_config(provider)['label']} 未配置 API Key")
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


# ---------- 供应商注册表 ----------

def _custom_providers() -> list[dict]:
    raw = _read_json(_providers_path()).get("providers")
    items = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id") or "").strip()
        base_url = str(item.get("base_url") or "").strip()
        model = str(item.get("model") or "").strip()
        if not (pid and base_url and model):
            continue
        items.append({
            "id": pid,
            "label": str(item.get("label") or pid),
            "base_url": base_url,
            "model": model,
            "builtin": False,
        })
    return items


def _builtin_config(pid: str) -> Optional[dict]:
    if pid == "deepseek":
        return {
            "id": pid,
            "label": _BUILTIN[pid]["label"],
            "base_url": config.LLM_BASE_URL,
            "model": config.LLM_MODEL,
            "builtin": True,
        }
    if pid == "kimi":
        return {
            "id": pid,
            "label": _BUILTIN[pid]["label"],
            "base_url": config.KIMI_BASE_URL,
            "model": config.KIMI_MODEL,
            "builtin": True,
        }
    return None


def provider_config(pid: str) -> Optional[dict]:
    builtin = _builtin_config(pid)
    if builtin:
        return builtin
    for item in _custom_providers():
        if item["id"] == pid:
            return item
    return None


def list_providers() -> list[dict]:
    """内置在前，自定义按名称排序。"""
    return [_builtin_config("deepseek"), _builtin_config("kimi")] + sorted(
        _custom_providers(), key=lambda item: item["label"].lower()
    )


def _slug(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return slug or "custom"


def add_provider(label: str, base_url: str, model: str) -> dict:
    """登记一个 OpenAI 兼容供应商；id 由名称生成并去重。"""
    label = (label or "").strip()
    base_url = (base_url or "").strip().rstrip("/")
    model = (model or "").strip()
    if not label:
        raise ValueError("供应商名称不能为空")
    if not re.match(r"^https?://", base_url):
        raise ValueError("接口地址必须以 http:// 或 https:// 开头")
    if not model:
        raise ValueError("模型名不能为空")

    with _lock:
        existing = {item["id"] for item in list_providers()}
        base = _slug(label)
        pid = base
        index = 2
        while pid in existing:
            pid = f"{base}-{index}"
            index += 1
        custom = _custom_providers()
        custom.append({"id": pid, "label": label, "base_url": base_url, "model": model})
        _write_json(_providers_path(), {"providers": [
            {k: item[k] for k in ("id", "label", "base_url", "model")} for item in custom
        ]})
    return provider_config(pid)


def remove_provider(pid: str) -> None:
    """删除自定义供应商（内置的不能删），同时清掉它的 Key。"""
    if _builtin_config(pid):
        raise ValueError("内置供应商不能删除")
    with _lock:
        creds = _load_credentials()
        creds.pop(pid, None)
        _write_json(_cred_path(), creds)
        custom = [item for item in _custom_providers() if item["id"] != pid]
        _write_json(_providers_path(), {"providers": [
            {k: item[k] for k in ("id", "label", "base_url", "model")} for item in custom
        ]})


# ---------- API Key ----------

def _load_credentials() -> dict:
    raw = _read_json(_cred_path())
    return {
        k: v for k, v in raw.items()
        if isinstance(v, str) and v.strip()
    }


def get_key(pid: str) -> str:
    """优先用设置页导入的 Key，其次回落到环境变量（仅内置供应商）。"""
    stored = _load_credentials().get(pid)
    if stored:
        return stored
    if pid == "kimi":
        return config.KIMI_API_KEY or ""
    if pid == "deepseek":
        return config.LLM_API_KEY or ""
    return ""


def set_key(pid: str, key: str) -> bool:
    if not provider_config(pid):
        raise ValueError(f"未登记的供应商：{pid}")
    with _lock:
        creds = _load_credentials()
        cleaned = (key or "").strip()
        if cleaned:
            creds[pid] = cleaned
        else:
            creds.pop(pid, None)
        _write_json(_cred_path(), creds)
    return bool(get_key(pid))


def mask_key(key: str) -> str:
    key = (key or "").strip()
    if not key:
        return ""
    if len(key) <= 8:
        return "…"
    return f"{key[:3]}…{key[-4:]}"


def has_key(pid: str) -> bool:
    return bool(get_key(pid))


# ---------- 运行时选择 ----------

def effective_provider() -> str:
    """当前实际使用的供应商：设置优先，其次 .env，最后第一个配了 Key 的。"""
    chosen: Optional[str] = get("provider")
    if chosen and has_key(chosen):
        return chosen

    env_provider = config.LLM_PROVIDER
    if env_provider in _BUILTIN and has_key(env_provider):
        return env_provider

    for item in list_providers():
        if has_key(item["id"]):
            return item["id"]
    return env_provider if env_provider in _BUILTIN else "deepseek"


def model_of(pid: str) -> str:
    cfg = provider_config(pid)
    return cfg["model"] if cfg else ""


def available_providers() -> list[dict]:
    return [
        {
            "id": item["id"],
            "label": item["label"],
            "model": item["model"],
            "builtin": item["builtin"],
            "has_key": has_key(item["id"]),
            "masked": mask_key(get_key(item["id"])),
        }
        for item in list_providers()
    ]


def public_view() -> dict:
    data = load()
    pid = effective_provider()
    return {
        "provider": pid,
        "provider_from_env": data["provider"] is None,
        "model": model_of(pid),
        "narrative_person": data["narrative_person"],
        "providers": available_providers(),
    }
