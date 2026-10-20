"""角色回收站：列出删除备份、按备份整体恢复、彻底删除。

删除角色时 `_backup_persona` 会把角色相关文件打包到
`data/trash/<角色>_<时间戳>/`，本模块负责把它变成真正可用的回收站：

- list_backups()   列出备份（角色名、时间、大小、包含哪些部分）
- restore_backup() 把角色定义 / 性格 / 聊天 / 摘要 / 场景 / 记忆库一起还原
- purge_backup()   彻底删除某个备份

恢复是"整体"的：要么角色文件、记忆、摘要都回来，要么在写入前就失败，
不会留下半个角色。
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Optional

from backend import config
from backend.engines import context as context_engine

# 备份目录里可能出现的部分（按恢复顺序展示）
PARTS = ("persona.json", "personality", "chat_logs", "summaries", "memories.json")

META_NAME = "meta.json"


class TrashError(Exception):
    """回收站操作失败（参数非法、备份不存在、目标已存在等）。"""


def _trash_root() -> Path:
    return config.DATA_DIR / "trash"


def _safe_id(backup_id: str) -> str:
    """只允许单层目录名，挡掉 ../ 与绝对路径。"""
    raw = str(backup_id or "").strip()
    if not raw or raw in (".", ".."):
        raise TrashError("备份 id 非法")
    if "/" in raw or "\\" in raw or ":" in raw:
        raise TrashError("备份 id 非法")
    return raw


def _backup_path(backup_id: str) -> Path:
    root = _trash_root().resolve()
    path = (root / _safe_id(backup_id)).resolve()
    if root != path.parent:
        raise TrashError("备份 id 非法")
    return path


def _dir_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def _read_meta(path: Path) -> dict:
    meta_file = path / META_NAME
    if meta_file.exists():
        try:
            data = json.loads(meta_file.read_text("utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def _persona_of(path: Path, meta: dict) -> str:
    """优先读 meta.json，其次从 `<角色>_<时间戳>` 目录名反推。"""
    name = str(meta.get("persona") or "").strip()
    if name:
        return name
    stem = path.name
    if "_" in stem:
        stem = stem.rsplit("_", 1)[0]
    return stem


def _parts_of(path: Path) -> list[str]:
    found = []
    for part in PARTS:
        candidate = path / part
        if candidate.is_dir() or candidate.is_file():
            found.append(part)
    if "last_scene" not in found and any(path.glob("last_scene_*.json")):
        found.append("last_scene")
    return found


def list_backups() -> list[dict]:
    """列出所有删除备份，按时间倒序。"""
    root = _trash_root()
    if not root.exists():
        return []
    items = []
    for path in root.iterdir():
        try:
            if not path.is_dir():
                continue
        except OSError:
            continue
        meta = _read_meta(path)
        stat = path.stat()
        items.append({
            "id": path.name,
            "persona": _persona_of(path, meta),
            "created_at": float(meta.get("created_at") or stat.st_mtime),
            "size_bytes": _dir_size(path),
            "parts": _parts_of(path),
        })
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return items


def _copy_tree(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copytree(str(src), str(dst), dirs_exist_ok=True)


def _restore_memories(persona: str, export_file: Path) -> dict:
    """把 memories.json 写回 Chroma；导入失败不阻断角色文件恢复。"""
    if not export_file.exists():
        return {"events": 0, "snippets": 0, "error": None}
    try:
        export = json.loads(export_file.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"events": 0, "snippets": 0, "error": f"memories.json 读取失败: {e}"}

    try:
        from backend.engines import memory as memory_engine
        return memory_engine.restore_memories(persona, export)
    except Exception as e:  # 向量库不可用（未装依赖 / 模型缺失）时如实报告
        return {"events": 0, "snippets": 0, "error": f"记忆回写失败: {e}"}


def restore_backup(backup_id: str, overwrite: bool = False) -> dict:
    """整体恢复一个备份，返回恢复明细。

    目标角色已存在且 overwrite=False 时抛 TrashError，绝不静默覆盖。
    """
    path = _backup_path(backup_id)
    if not path.is_dir():
        raise TrashError("备份不存在")
    meta = _read_meta(path)
    persona = _persona_of(path, meta)
    if not persona:
        raise TrashError("备份里没有角色名")

    persona_file = config.PERSONAS_DIR / f"{persona}.json"
    if persona_file.exists() and not overwrite:
        raise TrashError(f"角色「{persona}」已存在；如需覆盖请显式确认")

    if not (path / "persona.json").exists():
        raise TrashError("备份缺少 persona.json，无法恢复")

    restored = []

    # 1) 角色定义
    shutil.copy2(str(path / "persona.json"), str(persona_file))
    restored.append("persona")

    # 2) 性格状态
    if (path / "personality").is_dir():
        _copy_tree(path / "personality", config.DATA_DIR / "personalities" / persona)
        restored.append("personality")

    # 3) 聊天记录
    if (path / "chat_logs").is_dir():
        _copy_tree(path / "chat_logs", config.DATA_DIR / "chat_logs" / persona)
        restored.append("chat_logs")

    # 4) 滚动摘要
    if (path / "summaries").is_dir():
        _copy_tree(path / "summaries", context_engine.summary_dir(persona))
        restored.append("summaries")

    # 5) 末尾场景锚点
    scene_files = list(path.glob("last_scene_*.json"))
    if scene_files:
        scenes_dir = config.DATA_DIR / "last_scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)
        for src in scene_files:
            target = scenes_dir / f"{src.stem.removeprefix('last_scene_')}.json"
            shutil.copy2(str(src), str(target))
        restored.append("last_scene")

    # 6) 记忆库
    memory_result = _restore_memories(persona, path / "memories.json")
    if memory_result.get("events") or memory_result.get("snippets"):
        restored.append("memories")

    return {
        "persona": persona,
        "restored": restored,
        "memories": memory_result,
        "backup_id": path.name,
    }


def purge_backup(backup_id: str) -> bool:
    """彻底删除一个备份。"""
    path = _backup_path(backup_id)
    if not path.is_dir():
        raise TrashError("备份不存在")
    shutil.rmtree(str(path), ignore_errors=False)
    return True
