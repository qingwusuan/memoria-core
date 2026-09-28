"""
Memoria Core — FastAPI 后端
整合记忆引擎、性格引擎、Prompt 拼接器，提供 REST API。
"""
from __future__ import annotations

import asyncio
import datetime
import json
import os
import re
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend import config
from backend.engines import memory, personality, prompt_builder
from backend.engines.personality import PersonalityState, SensitivePoint
from backend.agents.personality import PersonalityAnalyzerAgent
from backend.agents.responder import ResponderAgent
from backend.agents.memory_extractor import MemoryExtractorAgent
from backend.agents.orchestrator import Orchestrator

# ── 持久化路径 ──
PERSONAS_DIR = config.PERSONAS_DIR
PERSONALITIES_DIR = config.DATA_DIR / "personalities"  # 按角色存储性格状态
PERSONALITIES_DIR.mkdir(parents=True, exist_ok=True)

# ── 用户昵称 ──
USER_NICKNAME_FILE = config.USER_NICKNAME_FILE


def load_user_nickname() -> str:
    """读取用户自定义昵称；文件不存在或内容非法时返回默认昵称「影幢」。"""
    try:
        if USER_NICKNAME_FILE.exists():
            data = json.loads(USER_NICKNAME_FILE.read_text("utf-8"))
            nickname = str(data.get("nickname", "")).strip()
            if nickname:
                return nickname
    except Exception as e:
        print(f"[main] 读取用户昵称失败，使用默认昵称: {e}", flush=True)
    return config.DEFAULT_USER_NICKNAME


def save_user_nickname(nickname: str) -> str:
    """校验并持久化用户昵称，返回规范化后的昵称。昵称要求 1-10 个字符。"""
    nickname = (nickname or "").strip()
    if not nickname:
        raise HTTPException(400, "昵称不能为空")
    if len(nickname) > 10:
        raise HTTPException(400, "昵称长度不能超过 10 个字符")
    USER_NICKNAME_FILE.parent.mkdir(parents=True, exist_ok=True)
    USER_NICKNAME_FILE.write_text(
        json.dumps(
            {"nickname": nickname, "updated_at": datetime.datetime.now().isoformat()},
            ensure_ascii=False,
            indent=2,
        ),
        "utf-8",
    )
    return nickname

# ── 全局性格状态 ──
_current_personality: Optional[PersonalityState] = None
_current_persona_name: str = "default"
_sensitive_points: list[SensitivePoint] = []
# 多元性格 Agent 管理：当前激活 persona 的 Agent 实例与 Orchestrator。
# 性格状态的所有权在 PersonalityAnalyzerAgent，此处仅为兼容旧 API 保留镜像引用。
_personality_agent: Optional[PersonalityAnalyzerAgent] = None
_orchestrator: Optional[Orchestrator] = None


def _personality_file(persona: str) -> Path:
    """返回指定角色的性格状态文件路径"""
    return PERSONALITIES_DIR / persona / "state.json"


def _rebuild_agents(persona: str):
    """构建/重建当前 persona 的 Agent 集合并挂到全局（含 Orchestrator）。"""
    global _personality_agent, _orchestrator, _current_personality, _sensitive_points
    personality_agent = PersonalityAnalyzerAgent(persona, llm_impl=chat_llm)
    personality_agent.load()
    _personality_agent = personality_agent
    _current_personality = personality_agent.state
    _sensitive_points = personality_agent.sensitive_points
    _orchestrator = Orchestrator(
        persona=persona,
        personality_agent=personality_agent,
        responder_agent=ResponderAgent(persona, llm_impl=chat_llm),
        memory_agent=MemoryExtractorAgent(persona),
    )
    return personality_agent


def _sync_personality_mirror():
    """将 Agent 内部状态同步回兼容镜像（analyze 替换对象后调用）。"""
    global _current_personality, _sensitive_points
    if _personality_agent is not None:
        _current_personality = _personality_agent.state
        _sensitive_points = _personality_agent.sensitive_points


def _load_personality(persona: str | None = None) -> PersonalityState:
    """构建并加载指定角色的性格 Agent；返回其状态对象。"""
    pname = persona or _current_persona_name
    agent = _rebuild_agents(pname)
    return agent.state


def _save_personality(state: PersonalityState):
    """持久化当前角色的性格状态（委托给 PersonalityAnalyzerAgent）。"""
    if _personality_agent is not None:
        _personality_agent.save()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _current_persona_name
    _migrate_legacy_collections()
    # 恢复上次激活的角色（避免重启后掉回 default 导致记忆检索空库）
    _current_persona_name = _load_active_persona()
    _load_personality()
    yield


def _migrate_legacy_collections():
    """将旧的无角色后缀 collection 迁移到 default 角色名下。一次性。"""
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    try:
        client = chromadb.PersistentClient(
            path=str(config.CHROMA_DIR),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        new_events = f"{config.CHROMA_COLLECTION}_default"
        new_snippets = f"memoria_snippets_default"

        # 检查是否需要迁移
        old_collections = [c.name for c in client.list_collections()]
        has_old_events = config.CHROMA_COLLECTION in old_collections
        has_old_snippets = "memoria_snippets" in old_collections
        has_new_events = new_events in old_collections
        has_new_snippets = new_snippets in old_collections

        if not has_old_events and not has_old_snippets:
            return
        if has_new_events and has_new_snippets:
            return  # 已经迁移过

        # 迁移 events
        if has_old_events and not has_new_events:
            old_coll = client.get_collection(config.CHROMA_COLLECTION)
            new_coll = client.get_or_create_collection(new_events)
            _copy_collection_data(old_coll, new_coll)
            client.delete_collection(config.CHROMA_COLLECTION)
            print(f"[migrate] 已迁移 {config.CHROMA_COLLECTION} → {new_events}", flush=True)

        # 迁移 snippets
        if has_old_snippets and not has_new_snippets:
            old_coll = client.get_collection("memoria_snippets")
            new_coll = client.get_or_create_collection(new_snippets)
            _copy_collection_data(old_coll, new_coll)
            client.delete_collection("memoria_snippets")
            print(f"[migrate] 已迁移 memoria_snippets → {new_snippets}", flush=True)
    except Exception as e:
        print(f"[migrate] 迁移失败（可忽略）: {e}", flush=True)


def _copy_collection_data(src, dst, batch_size: int = 500):
    """将 ChromaDB collection 数据批量复制到目标 collection。"""
    total = src.count()
    if total == 0:
        return
    offset = 0
    while offset < total:
        chunk = src.get(offset=offset, limit=batch_size, include=["documents", "metadatas", "embeddings"])
        if not chunk["ids"]:
            break
        dst.add(
            ids=chunk["ids"],
            documents=chunk["documents"],
            metadatas=chunk["metadatas"],
            embeddings=chunk.get("embeddings"),
        )
        offset += len(chunk["ids"])


app = FastAPI(title="Memoria Core", version="0.1.0", lifespan=lifespan)
# 本地单机部署：显式允许前端开发服务器来源（vite 默认端口 5173）。
# 注意 allow_origins=["*"] 与 allow_credentials=True 是无效组合（浏览器会拒绝携带凭据），
# 故必须显式列出来源；生产走 MEMORIA_SERVE_STATIC 同源伺服，无跨域需求。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════
# 请求/响应模型
# ═══════════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []  # [{"role": "user"/"assistant"/"action", "content": "..."}]
    suggest_normal: bool = False   # 是否在回复末尾附「普通建议」
    suggest_naughty: bool = False  # 是否在回复末尾附「坏坏建议」
    instructions: list[str] = []   # 指令中心选中的指令 payload，注入给模型执行
    action: str = ""               # 用户要执行的「动作」（独立于消息，不当作说的话/发的消息）


class ChatResponse(BaseModel):
    reply: str
    personality_snapshot: dict | None = None


class IngestRequest(BaseModel):
    dialogue: str
    run_personality: bool = False


class PersonaRequest(BaseModel):
    name: str
    guide: str  # 角色指南全文


class SensitivePointRequest(BaseModel):
    trigger_keywords: list[str]
    target_dimension: int
    delta: float
    cooldown_rounds: int = 50
    description: str = ""


class PersonaResponse(BaseModel):
    name: str
    guide: str
    is_active: bool


class ProfileRequest(BaseModel):
    nickname: str


# ═══════════════════════════════════════════════════════════════
# 统计
# ═══════════════════════════════════════════════════════════════

@app.get("/api/stats")
async def get_stats():
    stats = await asyncio.to_thread(memory.get_collection_stats, persona=_current_persona_name)
    p = _current_personality
    return {
        **stats,
        "personality": {
            "round_count": p.round_count if p else 0,
            "intimacy": p.intimacy if p else 0.0,
        },
        "active_persona": _current_persona_name,
        "total_personas": len(list_persona_files()),
    }


# ═══════════════════════════════════════════════════════════════
# 用户资料（自定义昵称）
# ═══════════════════════════════════════════════════════════════

@app.get("/api/user/profile")
def get_user_profile():
    """查询用户资料：返回当前自定义昵称（默认「影幢」）。"""
    return {"nickname": load_user_nickname()}


@app.put("/api/user/profile")
def update_user_profile(req: ProfileRequest):
    """修改用户昵称并持久化到 data/user_nickname.json。"""
    nickname = save_user_nickname(req.nickname)
    return {"nickname": nickname, "status": "ok"}


# ═══════════════════════════════════════════════════════════════
# 对话
# ═══════════════════════════════════════════════════════════════

@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, background_tasks: BackgroundTasks):
    global _current_personality

    # 加载当前角色
    persona = load_persona(_current_persona_name)
    guide = persona.get("guide", "") if persona else ""
    char_name = persona.get("name", "角色") if persona else "角色"

    # 用户昵称：读取自定义昵称（默认「影幢」），注入 prompt 让模型在叙事中用昵称称呼用户
    user_nickname = load_user_nickname()
    # 接续对话（带"(接续对话)"前缀 或 全新会话无 history）时，加载导入记录末尾场景作为检索锚点，
    # 避免短句检索把记忆拉向泛化场景导致回复场景偏离。
    scene_hint = ""
    if prompt_builder._is_continuation_message(req.message) or not req.history:
        scene_hint = memory.load_last_scene(_current_persona_name)

    # Orchestrator 同步编排：性格分析 → 敏感点 → 主回复 → 事件入库判定。
    # 内部含多次 LLM 调用（性格分析 + 主回复），放线程池执行不阻塞事件循环。
    if _orchestrator is not None:
        reply, snapshot, store_task = await asyncio.to_thread(
            _orchestrator.chat_sync,
            history=req.history,
            message=req.message,
            action=req.action,
            character_name=char_name,
            character_guide=guide,
            scene_hint=scene_hint,
            user_nickname=user_nickname,
            suggest_normal=req.suggest_normal,
            suggest_naughty=req.suggest_naughty,
            instructions=req.instructions,
        )
    else:
        # 兜底：Agent 未初始化时不回复（正常流程 lifespan 已初始化）
        reply, snapshot = "", None
        store_task = None

    # 结束一轮后同步性格状态镜像（analyze/apply 可能替换对象）
    _sync_personality_mirror()

    # 聊天事件异步入库：把本轮「用户消息 + AI 正文」交给后台任务提取事件，
    # 不阻塞回复返回；入库带语义去重，避免重复事件撑爆图谱。
    # 条件化触发已在 Orchestrator 内判定，寒暄轮 store_task 为 None 直接跳过。
    if store_task is not None:
        background_tasks.add_task(store_task)

    return ChatResponse(reply=reply, personality_snapshot=snapshot)


# ═══════════════════════════════════════════════════════════════
# 记忆检索
# ═══════════════════════════════════════════════════════════════

@app.get("/api/memories/search")
def search_memories_api(q: str = Query(..., description="搜索关键词"), top_k: int = 10):
    return {"results": memory.search_memories(q, top_k=top_k, persona=_current_persona_name)}


@app.get("/api/snippets/search")
def search_snippets_api(q: str = Query(...), top_k: int = 5):
    return {"results": memory.search_snippets(q, top_k=top_k, persona=_current_persona_name)}


# ═══════════════════════════════════════════════════════════════
# 聊天会话持久化
# ═══════════════════════════════════════════════════════════════

# 会话写文件线程锁：并发/中断时防止 JSON 写坏（配合临时文件 + os.replace 原子替换）
_session_write_lock = threading.Lock()


def _atomic_write_text(file: Path, text: str):
    """线程安全 + 原子写入：先写同目录 .tmp 临时文件，再 os.replace 原子替换。

    即使进程在写入中途崩溃，目标文件也只会是旧版本或新版本，不会是半截 JSON。
    """
    tmp = file.with_name(file.name + ".tmp")
    with _session_write_lock:
        tmp.write_text(text, encoding="utf-8")
        os.replace(str(tmp), str(file))


def _safe_session_id(session_id: str) -> str:
    """会话 ID 只允许 [A-Za-z0-9_-]，防御路径穿越（session_id 直接拼文件名）。"""
    if not session_id or not re.fullmatch(r"[A-Za-z0-9_-]+", session_id):
        raise HTTPException(400, "非法的会话 ID")
    return session_id


def _chat_logs_dir(persona: str | None = None):
    """返回指定角色的会话目录；persona 缺省时取当前激活角色。

    注意：路由入口必须在请求开始时锁定 persona 快照并显式传入，
    避免请求中途切换角色导致在途请求写错目录（串档）。
    """
    pname = persona or _current_persona_name or "default"
    d = Path(config.DATA_DIR) / "chat_logs" / pname
    d.mkdir(parents=True, exist_ok=True)
    return d

class SessionCreate(BaseModel):
    title: Optional[str] = None

class SessionMessages(BaseModel):
    messages: list  # [{role, content}]

@app.post("/api/chat/sessions")
def create_session(req: SessionCreate):
    # 请求开始时锁定角色快照，避免中途切换角色导致串档
    persona = _current_persona_name or "default"
    # 会话 ID 独立生成：时间戳 + 足够长的随机段，与角色无关但几乎不可能碰撞
    # （历史曾出现跨角色同名会话文件，见第 5 项评估报告）
    sid = datetime.datetime.now().strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:12]
    title = req.title or "新对话"
    file = _chat_logs_dir(persona) / f"{sid}.json"
    _atomic_write_text(file, json.dumps({"id": sid, "title": title, "messages": [], "created_at": datetime.datetime.now().isoformat()}, ensure_ascii=False))
    return {"session_id": sid, "title": title}

@app.get("/api/chat/sessions")
def list_sessions():
    persona = _current_persona_name or "default"
    d = _chat_logs_dir(persona)
    if not d.exists():
        return {"sessions": []}
    sessions = []
    for f in sorted(d.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data.pop("messages", None)  # 列表时不带消息体
            sessions.append(data)
        except Exception as e:
            print(f"[main] 跳过损坏的会话记录 {f}: {e}", flush=True)
    return {"sessions": sessions}

@app.get("/api/chat/sessions/{session_id}")
def get_session(session_id: str):
    persona = _current_persona_name or "default"
    _safe_session_id(session_id)
    file = _chat_logs_dir(persona) / f"{session_id}.json"
    if not file.exists():
        raise HTTPException(404, "会话不存在")
    data = json.loads(file.read_text(encoding="utf-8"))
    return {"session": data}

@app.put("/api/chat/sessions/{session_id}")
def save_session(session_id: str, req: SessionMessages):
    persona = _current_persona_name or "default"
    _safe_session_id(session_id)
    file = _chat_logs_dir(persona) / f"{session_id}.json"
    data = {}
    if file.exists():
        data = json.loads(file.read_text(encoding="utf-8"))
    data["messages"] = req.messages
    data["updated_at"] = datetime.datetime.now().isoformat()
    first_msg = req.messages[0]["content"][:24] if req.messages else "空对话"
    if not data.get("title") or data["title"] == "新对话":
        data["title"] = first_msg
    _atomic_write_text(file, json.dumps(data, ensure_ascii=False))
    return {"ok": True, "title": data.get("title")}

@app.delete("/api/chat/sessions/{session_id}")
def delete_session(session_id: str):
    persona = _current_persona_name or "default"
    _safe_session_id(session_id)
    file = _chat_logs_dir(persona) / f"{session_id}.json"
    if not file.exists():
        raise HTTPException(404, "会话不存在")
    file.unlink()
    return {"ok": True}

# ═══════════════════════════════════════════════════════════════
# 对话摄入（事件提取）
# ═══════════════════════════════════════════════════════════════

@app.post("/api/dialogue/ingest")
async def ingest_dialogue(req: IngestRequest):
    event_ids = memory.store_chat_events_from_dialogue(req.dialogue, persona=_current_persona_name)
    # 记录导入记录末尾场景，供后续接续对话锚定场景
    memory.save_last_scene(_current_persona_name, req.dialogue)

    if req.run_personality and _current_personality is not None:
        events = memory.extract_events(req.dialogue)
        summary = "; ".join(e.get("summary", "") for e in events[:5])
        if summary:
            # 阻塞 LLM 调用放到独立线程，避免卡死 uvicorn 线程池
            def _run_personality():
                global _current_personality
                if _personality_agent is not None:
                    _personality_agent.analyze(summary, llm_chat=chat_llm_background)
                    _personality_agent.save()
                    _sync_personality_mirror()
                else:
                    _current_personality = personality.analyze_delta(
                        _current_personality, summary, llm_chat=chat_llm_background
                    )
                    _save_personality(_current_personality)

            await asyncio.to_thread(_run_personality)

    return {
        "events_stored": len(event_ids),
    }


# ═══════════════════════════════════════════════════════════════
# 对话文件上传（附件导入）
# ═══════════════════════════════════════════════════════════════

@app.post("/api/dialogue/upload")
async def upload_dialogue(file: UploadFile = File(...)):
    if not file.filename.endswith(".txt"):
        raise HTTPException(400, "仅支持 .txt 文本文件")
    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("gbk")
        except Exception as e:
            print(f"[main] 对话文件 UTF-8/GBK 解码均失败: {e}", flush=True)
            raise HTTPException(400, "无法识别文件编码，请使用 UTF-8 或 GBK 编码的 .txt 文件")
    if not text.strip():
        raise HTTPException(400, "文件内容为空")
    # 事件抽取/切片入库含逐场景 LLM 调用与限速 sleep，属重 IO；
    # 必须在线程池执行，否则会阻塞事件循环，导致其它请求全部超时。
    event_ids = await asyncio.to_thread(
        memory.store_chat_events_from_dialogue, text, persona=_current_persona_name
    )
    # 记录导入记录末尾场景，供后续接续对话锚定场景
    memory.save_last_scene(_current_persona_name, text)

    # 解析对话末尾轮次，供前端注入聊天上下文（让 AI 能从末尾自然接续）
    tail_turns = _parse_tail_turns(text, max_turns=6)
    return {
        "events_stored": len(event_ids),
        "filename": file.filename,
        "tail_turns": tail_turns,
    }


def _parse_tail_turns(text: str, max_turns: int = 6) -> list[dict]:
    """解析文本末尾的对话轮次，返回 [{role, content}]，仅取最后 max_turns 条。

    兼容格式：
      - 用户：xxx / AI：xxx
      - **用户**: xxx / **AI**: xxx
      - 场景块格式：`> **场景名**` 标记之后，第一段为用户输入（归 user），
        其后正文为 AI 叙事（归 assistant）；「普通建议/坏坏建议」等建议栏
        不属于对话轮次，解析到即跳过并结束当前轮次。
    无角色标记的正文行按 AI 回复处理；识别到 '---' 分节符时停止（只保留最后一个分节）。
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    turns: list[dict] = []

    user_pat = re.compile(r"^(?:\*\*)?(?:用户|我)(?:\*\*)?[:：]\s*(.*)$")
    ai_pat = re.compile(r"^(?:\*\*)?(?:AI|助手|林子欣)(?:\*\*)?[:：]\s*(.*)$")
    scene_pat = re.compile(r"^>?\s*\*+[^*]+\*+$")
    suggestion_pat = re.compile(r"^(?:普通建议|坏坏建议)[:：]")

    # 场景标记后的第一个内容段视为用户输入；遇到建议栏则关闭当前轮
    pending_user = False
    in_suggestion = False

    def _append(role: str, content: str):
        nonlocal pending_user, in_suggestion
        if not content.strip():
            return
        if in_suggestion:
            return
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"] += "\n" + content
        else:
            turns.append({"role": role, "content": content})
        pending_user = False

    for ln in lines:
        if ln == "---":
            turns = []  # 遇到分节符：重新开始计数（只保留最后一段）
            pending_user = False
            in_suggestion = False
            continue
        if suggestion_pat.match(ln):
            in_suggestion = True
            pending_user = False
            continue
        if scene_pat.match(ln):
            # 新的场景标记：其后的第一个内容段是用户输入
            pending_user = True
            in_suggestion = False
            continue
        m = user_pat.match(ln)
        if m:
            _append("user", m.group(1))
            continue
        m = ai_pat.match(ln)
        if m:
            _append("assistant", m.group(1))
            continue
        # 场景标记后第一段正文 → 用户输入
        if pending_user:
            _append("user", ln)
            continue
        # 普通正文行 → 归为 assistant 继续
        _append("assistant", ln)

    return turns[-max_turns:]

# ═══════════════════════════════════════════════════════════════
# 性格
# ═══════════════════════════════════════════════════════════════

@app.get("/api/personality")
def get_personality():
    if _current_personality is None:
        raise HTTPException(404, "性格状态未初始化")
    p = _current_personality
    dimensions = []
    for i, name in enumerate(personality.DIMENSION_NAMES):
        dimensions.append({
            "index": i,
            "name": name,
            "surface": p.surface(i),
            "deep": p.deep(i),
            "gap": p.gap(i),
        })
    return {
        "round_count": p.round_count,
        "intimacy": p.intimacy,
        "dimensions": dimensions,
        "categories": personality.DIMENSION_CATEGORIES,
        "sensitive_points": [
            {
                "keywords": sp.trigger_keywords,
                "dimension": sp.target_dimension,
                "delta": sp.delta,
                "description": sp.description,
            }
            for sp in _sensitive_points
        ],
    }


@app.post("/api/personality/reset")
def reset_personality():
    global _current_personality, _sensitive_points
    if _personality_agent is not None:
        _personality_agent.reset()
        _current_personality = _personality_agent.state
        _sensitive_points = _personality_agent.sensitive_points
    else:
        _current_personality = PersonalityState()
        _sensitive_points = []
        _save_personality(_current_personality)
    return {"status": "ok", "message": "性格状态已重置"}


# ── 敏感点读写（kimi 审查补口：复用现有 personality 存储，不引入新存储）──

@app.get("/api/personality/sensitive_points")
def get_sensitive_points():
    if _personality_agent is None:
        raise HTTPException(404, "性格状态未初始化")
    return {
        "status": "ok",
        "sensitive_points": [
            {
                "trigger_keywords": sp.trigger_keywords,
                "target_dimension": sp.target_dimension,
                "delta": sp.delta,
                "cooldown_rounds": sp.cooldown_rounds,
                "description": sp.description,
            }
            for sp in _personality_agent.sensitive_points
        ],
    }


def _validate_sensitive_point(req: SensitivePointRequest):
    dim_count = len(personality.DIMENSION_NAMES)
    if not 0 <= req.target_dimension < dim_count:
        raise HTTPException(400, f"target_dimension 超出范围 [0, {dim_count - 1}]")
    if not req.trigger_keywords or not all(
        isinstance(k, str) and k.strip() for k in req.trigger_keywords
    ):
        raise HTTPException(400, "trigger_keywords 不能为空且每项必须为非空字符串")


@app.post("/api/personality/sensitive_points")
def add_sensitive_point(req: SensitivePointRequest):
    global _sensitive_points
    if _personality_agent is None:
        raise HTTPException(404, "性格状态未初始化")
    _validate_sensitive_point(req)
    _personality_agent.add_sensitive_point(SensitivePoint(
        trigger_keywords=[k.strip() for k in req.trigger_keywords],
        target_dimension=req.target_dimension,
        delta=req.delta,
        cooldown_rounds=req.cooldown_rounds,
        description=req.description,
    ))
    _sync_personality_mirror()
    return {
        "status": "ok",
        "message": "敏感点已添加",
        "count": len(_personality_agent.sensitive_points),
    }


@app.put("/api/personality/sensitive_points")
def replace_sensitive_points(req: list[SensitivePointRequest]):
    global _sensitive_points
    if _personality_agent is None:
        raise HTTPException(404, "性格状态未初始化")
    for item in req:
        _validate_sensitive_point(item)
    _personality_agent.set_sensitive_points([
        SensitivePoint(
            trigger_keywords=[k.strip() for k in item.trigger_keywords],
            target_dimension=item.target_dimension,
            delta=item.delta,
            cooldown_rounds=item.cooldown_rounds,
            description=item.description,
        )
        for item in req
    ])
    _sync_personality_mirror()
    return {
        "status": "ok",
        "message": f"敏感点已保存（共 {len(req)} 条）",
        "count": len(_personality_agent.sensitive_points),
    }


# ═══════════════════════════════════════════════════════════════
# 角色管理
# ═══════════════════════════════════════════════════════════════

# ── 角色名校验（路径穿越防御）──
_PERSONA_NAME_RE = re.compile(r"^[\u4e00-\u9fffA-Za-z0-9_-]+$")


def _safe_persona_name(name: str) -> str:
    """统一校验角色名，拒绝路径穿越与非法字符。

    只允许中文/英文/数字/下划线/连字符；拒绝空串、首尾空白、
    控制字符以及任何路径分隔符（..、/、\\）。非法时抛 HTTPException(400)。
    所有把 {name} 拼进文件路径的路由/函数必须在文件系统操作前调用本函数。
    """
    if not name or not isinstance(name, str):
        raise HTTPException(400, "角色名不能为空")
    if name.strip() != name or "\x00" in name:
        raise HTTPException(400, "角色名不能包含首尾空白或控制字符")
    if not _PERSONA_NAME_RE.match(name):
        raise HTTPException(400, "角色名只能包含中文、英文、数字、下划线与连字符")
    return name


def list_persona_files() -> list[str]:
    """列出所有 persona JSON 文件名（不含扩展名）"""
    if not PERSONAS_DIR.exists():
        return []
    return sorted([
        f.stem for f in PERSONAS_DIR.glob("*.json")
    ])


def load_persona(name: str) -> dict | None:
    """加载指定角色；name 非法时抛 400，防止路径穿越读写目录外文件。"""
    _safe_persona_name(name)
    file = PERSONAS_DIR / f"{name}.json"
    if not file.exists():
        return None
    return json.loads(file.read_text("utf-8"))


def save_persona(name: str, guide: str):
    """保存角色到磁盘；name 非法时抛 400，防止路径穿越写入目录外。"""
    _safe_persona_name(name)
    PERSONAS_DIR.mkdir(parents=True, exist_ok=True)
    file = PERSONAS_DIR / f"{name}.json"
    data = {"name": name, "guide": guide, "updated_at": time.time()}
    file.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


@app.get("/api/personas", response_model=list[PersonaResponse])
def list_personas():
    names = list_persona_files()
    result = []
    for name in names:
        try:
            p = load_persona(name)
        except HTTPException:
            # 历史遗留非法文件名（如含路径分隔符）不再可读，跳过而非让整个列表 500
            print(f"[main] 跳过非法角色文件名: {name!r}", flush=True)
            continue
        if p:
            result.append(PersonaResponse(
                name=p.get("name", name),
                guide=p.get("guide", ""),
                is_active=(name == _current_persona_name),
            ))
    return result


@app.get("/api/personas/{name}", response_model=PersonaResponse)
def get_persona(name: str):
    p = load_persona(name)
    if not p:
        raise HTTPException(404, f"角色 '{name}' 不存在")
    return PersonaResponse(
        name=p.get("name", name),
        guide=p.get("guide", ""),
        is_active=(name == _current_persona_name),
    )


@app.post("/api/personas", response_model=PersonaResponse)
def create_persona(req: PersonaRequest):
    _safe_persona_name(req.name)
    if load_persona(req.name):
        raise HTTPException(409, f"角色 '{req.name}' 已存在")
    save_persona(req.name, req.guide)
    return PersonaResponse(name=req.name, guide=req.guide, is_active=False)


@app.put("/api/personas/{name}", response_model=PersonaResponse)
def update_persona(name: str, req: PersonaRequest):
    _safe_persona_name(name)  # URL 参数（旧名）
    _safe_persona_name(req.name)  # 请求体（新名，改名场景）
    if not load_persona(name):
        raise HTTPException(404, f"角色 '{name}' 不存在")
    save_persona(req.name, req.guide)
    # 如果改名，清理旧文件
    if req.name != name:
        old_file = PERSONAS_DIR / f"{name}.json"
        if old_file.exists():
            old_file.unlink()
    return PersonaResponse(
        name=req.name, guide=req.guide,
        is_active=(req.name == _current_persona_name),
    )


def _active_persona_file() -> Path:
    return config.DATA_DIR / "active_persona.json"


def _load_active_persona() -> str:
    """启动时恢复上次激活的角色，避免重启后掉回 default 导致记忆检索空库。"""
    try:
        f = _active_persona_file()
        if f.exists():
            name = json.loads(f.read_text("utf-8")).get("name", "")
            if load_persona(name):
                return name
    except Exception as e:
        print(f"[main] 恢复上次激活角色失败，回退 default: {e}", flush=True)
    return "default"


def _save_active_persona(name: str):
    try:
        _active_persona_file().write_text(
            json.dumps({"name": name, "updated_at": time.time()}, ensure_ascii=False), "utf-8"
        )
    except Exception as e:
        print(f"[main] 保存激活角色记录失败: {e}", flush=True)


@app.post("/api/personas/{name}/activate")
def activate_persona(name: str):
    global _current_persona_name
    _safe_persona_name(name)
    if not load_persona(name):
        raise HTTPException(404, f"角色 '{name}' 不存在")
    _current_persona_name = name
    _load_personality(name)  # 切换到该角色的性格状态
    _save_active_persona(name)
    return {"status": "ok", "active_persona": name}


def _backup_persona(name: str, backup_root: Path) -> Path:
    """删除角色前，将角色全部相关数据备份到 data/trash/<name>_<时间戳>/。

    覆盖：角色定义 JSON、性格状态目录、会话记录目录、末尾场景记录、记忆库
    （事件 + 片段导出为 memories.json）。备份完成后调用方才执行删除。
    """
    import shutil
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backup_root / f"{name}_{ts}"
    dest.mkdir(parents=True, exist_ok=True)
    # 1) 角色定义
    src = PERSONAS_DIR / f"{name}.json"
    if src.exists():
        shutil.copy2(str(src), str(dest / "persona.json"))
    # 2) 性格状态目录
    pdir = PERSONALITIES_DIR / name
    if pdir.exists():
        shutil.copytree(str(pdir), str(dest / "personality"), dirs_exist_ok=True)
    # 3) 会话记录目录
    cdir = config.DATA_DIR / "chat_logs" / name
    if cdir.exists():
        shutil.copytree(str(cdir), str(dest / "chat_logs"), dirs_exist_ok=True)
    # 4) 末尾场景记录
    d = config.DATA_DIR / "last_scenes"
    if d.exists():
        for f in d.glob("*.json"):
            try:
                if json.loads(f.read_text("utf-8")).get("persona") == name:
                    shutil.copy2(str(f), str(dest / f"last_scene_{f.stem}.json"))
            except Exception as e:
                print(f"[main] 备份末尾场景 {f} 失败: {e}", flush=True)
    # 5) 记忆库（chroma collection 导出为 JSON，删除前先落盘）
    try:
        _, ev_coll, sn_coll, _ = memory._get_chroma(persona=name)
        export = {}
        if ev_coll.count() > 0:
            g = ev_coll.get(include=["documents", "metadatas"])
            export["events"] = [
                {"id": i, "document": doc, "metadata": meta}
                for i, doc, meta in zip(g["ids"], g["documents"], g["metadatas"])
            ]
        if sn_coll.count() > 0:
            g = sn_coll.get(include=["documents", "metadatas"])
            export["snippets"] = [
                {"id": i, "document": doc, "metadata": meta}
                for i, doc, meta in zip(g["ids"], g["documents"], g["metadatas"])
            ]
        if export:
            (dest / "memories.json").write_text(
                json.dumps(export, ensure_ascii=False, indent=2), "utf-8"
            )
    except Exception as e:
        print(f"[main] 备份角色 {name} 记忆库失败: {e}", flush=True)
    return dest


def _cleanup_old_trash(backup_root: Path, days: int = 7):
    """清理 data/trash 下超过 days 天的旧备份目录。"""
    import shutil
    cutoff = time.time() - days * 86400
    if not backup_root.exists():
        return
    for d in backup_root.iterdir():
        try:
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(str(d))
        except Exception as e:
            print(f"[main] 清理旧备份 {d} 失败: {e}", flush=True)


@app.delete("/api/personas/{name}")
def delete_persona(name: str):
    _safe_persona_name(name)
    file = PERSONAS_DIR / f"{name}.json"
    if not file.exists():
        raise HTTPException(404, f"角色 '{name}' 不存在")
    global _current_persona_name
    # P0-4：删除前先完整备份到 data/trash/<name>_<时间戳>/，并清理 7 天前的旧备份
    backup_root = config.DATA_DIR / "trash"
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_dir = _backup_persona(name, backup_root)
    _cleanup_old_trash(backup_root, days=7)
    file.unlink()
    # 清理该角色的性格状态目录
    import shutil
    pdir = PERSONALITIES_DIR / name
    if pdir.exists():
        shutil.rmtree(str(pdir))
    # 清理该角色的会话记录目录（对话 JSON）
    cdir = config.DATA_DIR / "chat_logs" / name
    if cdir.exists():
        shutil.rmtree(str(cdir))
    # 清理该角色的记忆库
    memory.wipe_memories(persona=name)
    # 清理该角色的末尾场景记录
    try:
        d = config.DATA_DIR / "last_scenes"
        if d.exists():
            for f in d.glob("*.json"):
                try:
                    if json.loads(f.read_text("utf-8")).get("persona") == name:
                        f.unlink()
                except Exception as e:
                    print(f"[main] 清理末尾场景 {f} 失败: {e}", flush=True)
    except Exception as e:
        print(f"[main] 清理角色 {name} 末尾场景目录失败: {e}", flush=True)
    if _current_persona_name == name:
        _current_persona_name = "default"
        _load_personality("default")
        try:
            f = _active_persona_file()
            if f.exists():
                f.unlink()
        except Exception as e:
            print(f"[main] 删除激活角色记录失败: {e}", flush=True)
    return {"status": "ok", "backup": str(backup_dir)}


# ═══════════════════════════════════════════════════════════════
# 数据导出（记忆图谱用）
# ═══════════════════════════════════════════════════════════════

# 边权重：时间相邻弱关联 / 内容相似强关联（权重=文本重叠度）
_EDGE_WEIGHT_TEMPORAL = 0.4
_SIMILAR_EDGE_MIN_OVERLAP = 0.3  # 复用 memory 去重判据相近的 n-gram 重叠阈值


def _build_graph_edges(nodes: list[dict]) -> list[dict]:
    """基于已有字段构建节点关联边（不引入新依赖）。

    建边依据（与现有存储/逻辑一致）：
    1) 时间相邻：按 ts 升序排列后，相邻节点建 temporal 边，把孤立事件串成时间链；
    2) 内容相似：复用 memory._text_overlap_ratio（项目已有去重判据），
       events 之间 / event-snippet 之间文本重叠度 >= 阈值时建 similar 边。
    每对节点最多一条边；similar 优先于 temporal（后者仅为兜底链）。
    """
    from backend.engines.memory import _text_overlap_ratio

    edges: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def _add(a: dict, b: dict, etype: str, weight: float):
        key = tuple(sorted((a["id"], b["id"])))
        if key in seen:
            return
        seen.add(key)
        edges.append({
            "source": a["id"],
            "target": b["id"],
            "type": etype,
            "weight": weight,
        })

    if len(nodes) >= 2:
        ordered = sorted(nodes, key=lambda n: n.get("ts") or 0)
        for i in range(len(ordered) - 1):
            _add(ordered[i], ordered[i + 1], "temporal", _EDGE_WEIGHT_TEMPORAL)

    events = [n for n in nodes if n["type"] == "event"]
    snippets = [n for n in nodes if n["type"] == "snippet"]
    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            ov = _text_overlap_ratio(events[i]["label"], events[j]["label"])
            if ov >= _SIMILAR_EDGE_MIN_OVERLAP:
                _add(events[i], events[j], "similar", round(ov, 3))
    for ev in events:
        for sn in snippets:
            ov = _text_overlap_ratio(ev["label"], sn["full_text"])
            if ov >= _SIMILAR_EDGE_MIN_OVERLAP:
                _add(ev, sn, "similar", round(ov, 3))

    return edges


@app.get("/api/memories/graph")
def memory_graph(min_importance: float = Query(0.0, ge=0.0, le=1.0)):
    """返回记忆节点和关联，供 D3.js 力导向图使用。min_importance 过滤低重要度事件。"""
    _, ev_coll, sn_coll, _ = memory._get_chroma(persona=_current_persona_name)
    events = []
    if ev_coll.count() > 0:
        all_events = ev_coll.get(include=["documents", "metadatas"])
        for i, mid in enumerate(all_events["ids"]):
            meta = all_events["metadatas"][i]
            imp = meta.get("importance", 0.5)
            if imp < min_importance:
                continue
            events.append({
                "id": mid,
                "type": "event",
                "label": all_events["documents"][i],
                "importance": imp,
                "ts": meta.get("ts", 0),
            })

    snippets = []
    if sn_coll.count() > 0 and sn_coll.count() <= 200:
        all_sn = sn_coll.get(include=["documents", "metadatas"])
        for i, sid in enumerate(all_sn["ids"]):
            meta = all_sn["metadatas"][i]
            doc = all_sn["documents"][i]
            snippets.append({
                "id": sid,
                "type": "snippet",
                "label": doc[:80] + ("..." if len(doc) > 80 else ""),
                "full_text": doc,
                "ts": meta.get("ts", 0),
            })

    return {
        "nodes": events + snippets,
        "edges": _build_graph_edges(events + snippets),
        "total_events": len(events),
        "total_snippets": len(snippets),
    }


# ═══════════════════════════════════════════════════════════════
# LLM 调用适配
# ═══════════════════════════════════════════════════════════════

def chat_llm(prompt: str, system: str = "", temperature: float = 0.3, max_tokens: int = 2000) -> str:
    """性格分析专用的 LLM 调用，从 backend.llm.deepseek 导入。
    默认 max_tokens 抬至 2000：kimi-k2.6 推理型下 1000 额度被 reasoning 占满
    会导致正文为空（"LLM 返回空内容"→ 500 丢消息）。
    走主对话锁（与主回复串行，保持对话链路顺序语义）。"""
    from backend.llm.deepseek import chat
    return chat(prompt, system=system, temperature=temperature, max_tokens=max_tokens)


def chat_llm_background(prompt: str, system: str = "", temperature: float = 0.3, max_tokens: int = 2000) -> str:
    """后台任务专用 LLM 调用（事件提取/对话导入分析），走后台锁，
    与主对话锁互不阻塞，避免后台重试 sleep 拖慢聊天回复。"""
    from backend.llm.deepseek import chat
    return chat(prompt, system=system, temperature=temperature, max_tokens=max_tokens, background=True)


def _split_suggest(reply: str) -> tuple[str, str]:
    """拆分叙事正文与建议栏。返回 (body, suggest)。"""
    lines = reply.split("\n")
    idx = None
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("普通建议") or s.startswith("坏坏建议"):
            idx = i
            break
    if idx is None:
        return reply, ""
    body = "\n".join(lines[:idx]).rstrip()
    suggest = "\n".join(lines[idx:]).strip()
    return body, suggest


def _hanzi_count(text: str) -> int:
    import re as _re
    return len(_re.findall(r'[\u4e00-\u9fff]', text))


# ── 静态文件（前端 build 产物）──
# 放在所有 API 路由之后注册，确保 API 优先匹配
if os.environ.get("MEMORIA_SERVE_STATIC"):
    static_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
