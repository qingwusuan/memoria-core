"""
持久记忆存储（事件提取 + 向量化存储 + 语义检索 + 对话片段索引）
使用 bge-small-zh-v1.5 做中文语义向量化。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import uuid
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer

from backend import config
from backend.llm.deepseek import chat as llm_chat

# ── 全局单例 ──
_chroma_client: Optional[chromadb.PersistentClient] = None
_events_coll: Optional[object] = None
_snippets_coll: Optional[object] = None
_embedding_model: Optional[SentenceTransformer] = None

# 配置常量
SNIPPETS_COLLECTION = "memoria_snippets"
SNIPPET_CHUNK_SIZE = 400       # 每个片段的字符数上限
SNIPPET_OVERLAP = 0            # 按对话轮次切分，不再使用字符重叠
MAX_SCENE_LENGTH = 6000        # 单个场景超过此字符数时自动拆片子场景
RECENT_WINDOW_N = 8            # prompt 拼接时保留的近轮数（可在 config 覆盖）
DEDUP_OVERLAP_MIN = 0.35       # 去重文本重叠校验阈值：候选与 top1 摘要 3-gram Jaccard >= 此值才算实质重复


def _text_overlap_ratio(a: str, b: str, n: int = 3) -> float:
    """计算两段中文文本的字符 n-gram 集合 Jaccard 重叠度（0.0~1.0）。

    用于去重二次校验：仅凭向量距离判重复会误杀语义相近但实为不同
    记忆点的事件（如亲密互动类），此处用字符级重叠度确认内容实质一致。
    """
    def _grams(s: str) -> set:
        s = "".join(s.split())  # 去空白
        if len(s) < n:
            return {s} if s else set()
        return {s[i:i + n] for i in range(len(s) - n + 1)}
    ga, gb = _grams(a), _grams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


class _BgeEmbeddingFn:
    """ChromaDB embedding function backed by bge-small-zh-v1.5."""

    def __init__(self, model: SentenceTransformer):
        self._model = model

    def name(self) -> str:
        return "bge-small-zh-v1.5"

    def embed_query(self, input) -> list[list[float]]:
        if isinstance(input, str):
            input = [input]
        return self._model.encode(input, normalize_embeddings=True).tolist()

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return self._model.encode(input, normalize_embeddings=True).tolist()

    def __call__(self, input: list[str]) -> list[list[float]]:
        return self.embed_documents(input)


def _safe_coll_suffix(persona: str) -> str:
    """ChromaDB 集合名仅允许 [a-zA-Z0-9._-]；中文等非 ASCII 角色名做确定性哈希映射。"""
    import re as _re
    if _re.fullmatch(r"[a-zA-Z0-9._-]+", persona):
        return persona
    h = hashlib.md5(persona.encode("utf-8")).hexdigest()[:10]
    return f"p_{h}"


def _get_chroma(persona: str = "default"):
    """按角色隔离 ChromaDB collection。每个角色拥有独立的事件和片段集合。"""
    global _chroma_client, _embedding_model
    if _chroma_client is None:
        os.makedirs(str(config.CHROMA_DIR), exist_ok=True)
        _chroma_client = chromadb.PersistentClient(
            path=str(config.CHROMA_DIR),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        print(f"[memory] 加载 embedding 模型: {config.EMBEDDING_MODEL} ...", file=sys.stderr)
        _embedding_model = SentenceTransformer(config.EMBEDDING_MODEL)

    _ef = _BgeEmbeddingFn(_embedding_model)

    def _get_or_create_coll(name):
        try:
            return _chroma_client.get_collection(name=name, embedding_function=_ef)
        except Exception:
            return _chroma_client.create_collection(
                name=name,
                embedding_function=_ef,
                metadata={"hnsw:space": "cosine"},
            )

    events_coll = _get_or_create_coll(f"{config.CHROMA_COLLECTION}_{_safe_coll_suffix(persona)}")
    snippets_coll = _get_or_create_coll(f"{SNIPPETS_COLLECTION}_{_safe_coll_suffix(persona)}")
    return _chroma_client, events_coll, snippets_coll, _embedding_model


# ═══════════════════════════════════════════════════════════════
# 事件提取（含关键引用 + 场景自动拆片）
# ═══════════════════════════════════════════════════════════════

EXTRACTION_PROMPT = """从以下对话中提取值得长期记忆的事件。

每条事件包含：
- summary: 一句话事件描述（中文）
- importance: 0.0~1.0 重要性评分（关系里程碑、角色设定、未来计划等高分）
- quotes: 1~3 句对话原文引用（必须是原文原句，不要改写），没有重要原文则给空数组 []

提取标准：
1. 用户偏好、习惯、身份信息
2. 角色设定或人设约定
3. 关系里程碑（表白、承诺、争吵、确认关系等）
4. 提及的未来计划、承诺事项
5. 有亮点的隐喻或梗（可作为日后 call-back 素材的句子）
6. 重要身体动作/亲密互动（拥抱、牵手、搂抱、依偎、亲吻、靠肩、挽手、触碰等具体亲密或关键肢体动作，并写明情境），这类事件对关系记忆有实质价值，必须提取
7. 有实质内容的情绪表态（喜欢、想念、吃醋、心动、占有欲等明确情感表达）

重要：
- 对话以"用户：..."和"角色名：..."交替出现。**必须优先提取"用户："消息中出现的关键事实**（身份、计划、偏好、承诺、经历），这是最高优先级。
- 避免提取过于泛化的互动行为（如"某人调侃回应"、"某人等待回复时的分心行为"、"某人微笑着回应"等无具体信息量的日常反应），除非其中包含新的具体事实或关系进展。
- 上述"避免泛化"仅针对无信息量的日常寒暄/神态反应，**不适用于身体接触类动作**：任何具体的亲密互动（拥抱、牵手、搂抱、依偎等）都属于第 6 条标准，必须单独成事件，不要合并进表白/暧昧大事件里。
- 每条事件必须有实质信息增量；纯情绪/神态描写不算事件（但明确的情感表态按第 7 条保留）。

注意：summary 是角色记忆的唯一载体，必须保留信息量——对话中任何有实质内容的发言（表白、约定、偏好、观点、承诺、情绪表态）都要把大意转述进 summary。例如不能只写"两人看了电影"，应写成"他说改天陪她去看电影，她嘴硬说谁要你陪"。
注意：quotes 必须严格来自原文，不要改写或缩写（不进对话上下文，仅留档供图谱展示）。

对话：
{dialogue}

以 JSON 数组输出：
[{{"summary": "...", "importance": 0.9, "quotes": ["原文1", "原文2"]}}]"""


def _repair_json_quotes(body: str) -> str:
    """修复 LLM 输出 JSON 中字符串内部多余的 ASCII 引号。

    实测 LLM 在 quotes 字段常输出 `"“原文”"` 这种把中文引号包裹的内容
    又用 ASCII 引号包一层的形式，导致 JSON 非法、json.loads 失败。
    用状态机扫描：字符串内容中的裸引号（下一个非空白字符不是 , ] }）
    视为内容引号，替换为中文左引号，从而修复 JSON。
    """
    out = []
    in_str = False
    i, n = 0, len(body)
    while i < n:
        ch = body[i]
        if in_str:
            if ch == "\\":
                out.append(ch)
                if i + 1 < n:
                    out.append(body[i + 1])
                i += 2
                continue
            if ch == '"':
                j = i + 1
                while j < n and body[j] in " \t\r\n":
                    j += 1
                if j < n and body[j] in ",]}:":
                    in_str = False
                    out.append(ch)
                else:
                    out.append("\u201c")  # 内容引号 → 中文左引号
                i += 1
                continue
            out.append(ch)
            i += 1
        else:
            if ch == '"':
                in_str = True
            out.append(ch)
            i += 1
    return "".join(out)


def _convert_cjk_quotes_as_delimiters(body: str) -> str:
    """把全角引号（U+201C/U+201D）转换为 JSON 字符串定界符。

    实测 LLM 在 quotes 数组元素中直接输出 `"原文"`（中文引号包裹）而非
    JSON 字符串，导致 json.loads 失败。本函数用状态机扫描：结构位置的
    全角引号视为字符串定界符，字符串内容中的中文引号原样保留。
    """
    out = []
    in_str = False
    delim: str | None = None  # "a"=ASCII 定界, "c"=全角定界
    i, n = 0, len(body)
    while i < n:
        ch = body[i]
        if in_str:
            if ch == "\\":
                out.append(ch)
                if i + 1 < n:
                    out.append(body[i + 1])
                i += 2
                continue
            if delim == "a":
                if ch == '"':
                    j = i + 1
                    while j < n and body[j] in " \t\r\n":
                        j += 1
                    if j < n and body[j] in ",]}:":
                        in_str = False
                    out.append(ch)
                else:
                    out.append(ch)
                i += 1
                continue
            # 全角定界字符串内
            if ch == "\u201d":
                in_str = False
                out.append('"')
            else:
                out.append(ch)
            i += 1
        else:
            if ch == '"':
                in_str = True
                delim = "a"
                out.append(ch)
            elif ch == "\u201c":
                in_str = True
                delim = "c"
                out.append('"')
            elif ch == "\u201d":
                out.append('"')  # 孤立右引号按定界符闭合
            else:
                out.append(ch)
            i += 1
    return "".join(out)


def extract_events(dialogue: str) -> list[dict]:
    prompt = EXTRACTION_PROMPT.format(dialogue=dialogue)
    # 事件提取对 JSON 结构输出，低温度在 deepseek-flash 路由下极易返回空内容，
    # 提高到温 + 加大 token 额度以降低空返回率（提取结果经多重 JSON 解析容错）。
    response = llm_chat(prompt, temperature=0.9, max_tokens=2000, background=True)
    try:
        # 剥离 markdown 代码块 ```json ... ```
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # 去掉首行 ```json 和末行 ```
            body = "\n".join(lines[1:-1]) if len(lines) > 2 else cleaned
            cleaned = body.strip()
        start = cleaned.find("[")
        end = cleaned.rfind("]") + 1
        if start >= 0 and end > start:
            json_body = cleaned[start:end]
            try:
                return json.loads(json_body)
            except json.JSONDecodeError:
                # 容错1：全角引号当定界符
                try:
                    return json.loads(_convert_cjk_quotes_as_delimiters(json_body))
                except json.JSONDecodeError:
                    # 容错2：字符串内裸 ASCII 引号 → 中文引号
                    repaired = _repair_json_quotes(json_body)
                    return json.loads(repaired)
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def _split_dialogue_by_scenes(dialogue: str, max_len: int = MAX_SCENE_LENGTH) -> list[str]:
    """
    按场景标记切分对话。场景标记格式：> **场景名** 或 **场景名** 开头行。
    若单个场景超过 max_len，按换行切为子块（保证以换行为边界）。
    若无场景标记，直接按 max_len 切分。
    """
    scene_pattern = re.compile(r"(?:^|\n)(>?\s*\*\*[^*]+\*\*)", re.MULTILINE)
    matches = list(scene_pattern.finditer(dialogue))

    if not matches:
        # 无场景标记 → 按 max_len 切
        if len(dialogue) <= max_len:
            return [dialogue]
        chunks = []
        for i in range(0, len(dialogue), max_len):
            chunk = dialogue[i:i + max_len]
            if chunk.strip():
                chunks.append(chunk)
        return chunks

    # 有场景标记 → 按标记切
    scenes = []
    for idx, m in enumerate(matches):
        start = m.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(dialogue)
        scene_text = dialogue[start:end].strip()
        if scene_text:
            # 超长场景再切子块
            if len(scene_text) > max_len:
                sub_chunks = _split_dialogue_by_scenes(scene_text, max_len)
                scenes.extend(sub_chunks)
            else:
                scenes.append(scene_text)

    # 处理场景标记之前的文本（如果有）
    if matches and matches[0].start() > 0:
        prefix = dialogue[:matches[0].start()].strip()
        if prefix:
            if len(prefix) > max_len:
                scenes = _split_dialogue_by_scenes(prefix, max_len) + scenes
            else:
                scenes.insert(0, prefix)

    return scenes


def store_events_from_dialogue(dialogue: str, persona: str = "default") -> list[str]:
    """从对话中提取事件并存储。超长对话自动按场景拆片后逐片提取。"""
    _, ev_coll, _, _ = _get_chroma(persona)

    scenes = _split_dialogue_by_scenes(dialogue)
    ids = []
    ts = time.time()

    for scene in scenes:
        try:
            events = extract_events(scene)
        except Exception as e:
            # 单个场景提取失败不中断整批导入，保留已提取内容
            print(f"[memory] 场景事件提取失败，跳过该场景: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            events = []
        time.sleep(1.0)  # 场景间限速，避免瞬时打爆 LLM RPM 限流
        for ev in events:
            mid = f"mem_{uuid.uuid4().hex[:12]}"
            quotes = ev.get("quotes", [])
            if isinstance(quotes, list) and quotes:
                quotes_str = json.dumps(quotes, ensure_ascii=False)
            else:
                quotes_str = "[]"

            ev_coll.add(
                ids=[mid],
                documents=[ev["summary"]],
                metadatas=[{
                    "importance": ev.get("importance", 0.5),
                    "ts": ts,
                    "quotes": quotes_str,
                }],
            )
            ids.append(mid)

    return ids


def _extract_events_with_retry(
    scene: str,
    max_attempts: int = 3,
    wait_seconds: float = 20.0,
) -> list[dict]:
    """带长退避重试的事件提取。

    组织级 LLM RPM 限制很紧（实测 org max RPM=3），每轮聊天的主回复与
    性格分析已消耗配额，紧跟其后的提取调用常撞 429。deepseek.chat 内置
    重试总退避仅 15s，不足以跨过 20s 限流窗口，这里按 20s 间隔再补 2 次
    重试，后台任务中运行，不阻塞用户回复。
    """
    import traceback
    for attempt in range(max_attempts):
        try:
            return extract_events(scene)
        except Exception as e:
            print(f"[memory] extract_events attempt={attempt} FAILED: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            if attempt == max_attempts - 1:
                return []
            time.sleep(wait_seconds)
    return []


def store_chat_events_from_dialogue(
    dialogue: str,
    persona: str = "default",
    dedup_threshold: float = 0.30,
) -> list[str]:
    """单轮聊天事件提取入库（带语义去重）。

    与 store_events_from_dialogue 的区别：
    - 面向每轮聊天的小段文本，限速更轻（0.5s）；
    - 入库前先用向量检索已有事件，summary 与最近事件距离 < dedup_threshold
      且文本重叠度 >= DEDUP_OVERLAP_MIN 时视为重复事件，跳过不写，避免图谱
      随聊天无限膨胀出同义节点，也避免误杀语义相近的新记忆点；
    - 提取带长退避重试，抗 LLM 429 限流。
    """
    _, ev_coll, _, _ = _get_chroma(persona)
    print(f"[memory] store_chat_events start persona={persona} len={len(dialogue)}", flush=True)

    scenes = _split_dialogue_by_scenes(dialogue)
    ids = []
    ts = time.time()

    for scene in scenes:
        if not scene or not scene.strip():
            continue
        events = _extract_events_with_retry(scene)
        print(f"[memory] scene events={len(events)}", flush=True)
        time.sleep(0.5)  # 限速，避免打爆 LLM RPM

        for ev in events:
            summary = str(ev.get("summary", "")).strip()
            if not summary:
                print(f"[memory]   skip empty summary: {ev}", file=sys.stderr, flush=True)
                continue
            try:
                imp = float(ev.get("importance", 0.5))
            except (TypeError, ValueError):
                imp = 0.5
            imp = max(0.0, min(1.0, imp))

            # 语义去重（双重判定，两层都过才算重复）：
            # 1) 距离硬门槛：与已有事件 top1 向量距离 < dedup_threshold 才进入候选；
            # 2) 文本重叠校验：候选事件的摘要须与 top1 实质内容重叠（3-gram Jaccard >= 阈值）。
            # 仅凭向量距离判重复会误杀语义相近但实为不同记忆点的事件（如亲密互动类），故加内容比对。
            if ev_coll.count() > 0:
                try:
                    q = ev_coll.query(query_texts=[summary], n_results=1)
                    if q["ids"] and q["ids"][0] and q.get("distances") and q.get("documents"):
                        d = q["distances"][0][0]
                        top_doc = q["documents"][0][0] if q["documents"][0] else ""
                        overlap = _text_overlap_ratio(summary, top_doc)
                        is_dup = (d < dedup_threshold and overlap >= DEDUP_OVERLAP_MIN)
                        print(f"[memory]   dedup check: {summary[:40]}... top={q['ids'][0][0]} dist={d:.4f} overlap={overlap:.2f} {'SKIP' if is_dup else 'INSERT'}", file=sys.stderr, flush=True)
                        if is_dup:
                            continue
                except Exception as e:
                    print(f"[memory]   dedup query error: {e}", file=sys.stderr, flush=True)

            mid = f"mem_{uuid.uuid4().hex[:12]}"
            quotes = ev.get("quotes", [])
            if isinstance(quotes, list) and quotes:
                quotes_str = json.dumps(quotes, ensure_ascii=False)
            else:
                quotes_str = "[]"

            ev_coll.add(
                ids=[mid],
                documents=[summary],
                metadatas=[{
                    "importance": imp,
                    "ts": ts,
                    "quotes": quotes_str,
                }],
            )
            ids.append(mid)

    if ids:
        print(f"[memory] 聊天事件入库 {len(ids)} 条（已去重）", file=sys.stderr)
    return ids


def search_memories(query: str, top_k: int = 5, persona: str = "default") -> list[dict]:
    """语义检索事件记忆，返回摘要 + 重要度 + 原文引用。"""
    _, ev_coll, _, _ = _get_chroma(persona)
    results = ev_coll.query(query_texts=[query], n_results=top_k)
    items = []
    if results["ids"] and results["ids"][0]:
        for i, mid in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i]
            quotes_raw = meta.get("quotes", "[]")
            try:
                quotes = json.loads(quotes_raw) if isinstance(quotes_raw, str) else quotes_raw
            except json.JSONDecodeError:
                quotes = []

            items.append({
                "id": mid,
                "summary": results["documents"][0][i],
                "importance": meta.get("importance", 0.5),
                "distance": results["distances"][0][i] if results.get("distances") else 0.0,
                "quotes": quotes,
            })
    return items


# ═══════════════════════════════════════════════════════════════
# 对话片段索引（全量 RAG）
# ═══════════════════════════════════════════════════════════════

# 元评论模式：用户指责 AI / 自我纠正类无意义行
_META_JUNK_PATTERNS = [
    re.compile(r"你这ai[是不是能]*"),
    re.compile(r"抱歉.*(?:之前|写得)"),
    re.compile(r"重写$"),
]


def _clean_dialogue(text: str) -> str:
    """移除独立的场景标记行和元评论垃圾段落。"""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # 跳过纯场景标记行：*主席台告白后牵手阶段* 等
        if re.match(r"^\*[^*]+\*$", stripped):
            continue
        # 跳过元评论垃圾行（对 AI 的指责或自纠）
        if any(p.search(stripped) for p in _META_JUNK_PATTERNS):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def _similarity(a: str, b: str) -> float:
    """5-gram Jaccard 相似度，用于判断相邻片段是否高度重复。"""
    n = 5
    if len(a) < n or len(b) < n:
        # 短文本直接用最长公共子串比例
        shorter = min(len(a), len(b))
        if shorter == 0:
            return 0.0
        s = set(a) & set(b)
        return len(s) / shorter
    a_ngrams = set(a[i : i + n] for i in range(len(a) - n + 1))
    b_ngrams = set(b[i : i + n] for i in range(len(b) - n + 1))
    if not a_ngrams or not b_ngrams:
        return 0.0
    return len(a_ngrams & b_ngrams) / len(a_ngrams | b_ngrams)


def _chunk_dialogue(
    text: str,
    chunk_size: int = SNIPPET_CHUNK_SIZE,
    overlap: int = SNIPPET_OVERLAP,
) -> list[str]:
    """按对话自然段落切分文本，每个对话轮次只归属一个片段，杜绝重复和截断。"""
    text = _clean_dialogue(text)

    # 按双换行为段落边界切分
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

    chunks = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= chunk_size:
            current = (current + "\n\n" + para) if current else para
        else:
            if current:
                chunks.append(current)
            # 如果单个段落本身超过 chunk_size，按 chunk_size 硬切但保留换行完整性
            if len(para) > chunk_size:
                sub = para
                while len(sub) > chunk_size:
                    cut = sub.rfind("\n", 0, chunk_size)
                    if cut == -1 or cut < chunk_size // 2:
                        cut = chunk_size
                    chunks.append(sub[:cut].strip())
                    sub = sub[cut:].strip()
                current = sub if sub else ""
            else:
                current = para

    if current.strip():
        chunks.append(current.strip())

    # 去重：相邻片段高度相似（>85%）时只保留较长者
    unique_chunks = []
    for ch in chunks:
        if unique_chunks and _similarity(ch, unique_chunks[-1]) > 0.85:
            if len(ch) > len(unique_chunks[-1]):
                unique_chunks[-1] = ch
            continue
        unique_chunks.append(ch)

    return unique_chunks


def store_dialogue_snippets(dialogue: str, persona: str = "default") -> int:
    """将对话原文切块存入 snippets collection。返回入库片段数。"""
    _, _, sn_coll, _ = _get_chroma(persona=persona)
    chunks = _chunk_dialogue(dialogue)

    if not chunks:
        return 0

    ids = []
    ts = time.time()
    for chunk in chunks:
        sid = f"sn_{uuid.uuid4().hex[:12]}"
        sn_coll.add(
            ids=[sid],
            documents=[chunk],
            metadatas=[{"ts": ts, "char_count": len(chunk)}],
        )
        ids.append(sid)

    print(f"[memory] 入库 {len(ids)} 个对话片段", file=sys.stderr)
    return len(ids)


def search_snippets(query: str, top_k: int = 3, distance_threshold: float = 0.65, persona: str = "default") -> list[dict]:
    """
    语义检索对话原文片段。
    只返回 distance < threshold 的结果（阈值越小越精准，0.65 为推荐值）。
    """
    _, _, sn_coll, _ = _get_chroma(persona=persona)
    if sn_coll.count() == 0:
        return []

    results = sn_coll.query(query_texts=[query], n_results=top_k)
    items = []
    if results["ids"] and results["ids"][0]:
        for i, sid in enumerate(results["ids"][0]):
            distance = results["distances"][0][i] if results.get("distances") else 0.0
            if distance > distance_threshold:
                continue
            items.append({
                "id": sid,
                "text": results["documents"][0][i],
                "distance": distance,
            })
    return items


def get_collection_stats(persona: str = "default") -> dict:
    _, ev_coll, sn_coll, model = _get_chroma(persona)
    return {
        "total_memories": ev_coll.count(),
        "total_snippets": sn_coll.count(),
        "embedding_model": config.EMBEDDING_MODEL,
        "dim": model.get_embedding_dimension() if model else config.EMBEDDING_DIM,
    }


def wipe_memories(persona: str = "default"):
    """清空当前角色的所有记忆（事件 + 片段）。"""
    global _chroma_client
    client, _, _, _ = _get_chroma(persona)
    try:
        client.delete_collection(f"{config.CHROMA_COLLECTION}_{_safe_coll_suffix(persona)}")
    except Exception as e:
        print(f"[memory] 删除事件 collection 失败: {e}", file=sys.stderr, flush=True)
    try:
        client.delete_collection(f"{SNIPPETS_COLLECTION}_{_safe_coll_suffix(persona)}")
    except Exception as e:
        print(f"[memory] 删除片段 collection 失败: {e}", file=sys.stderr, flush=True)


# ═══════════════════════════════════════════════════════════════
# 导入记录末尾场景（接续对话的场景锚点）
# ═══════════════════════════════════════════════════════════════

_SCENE_MARKER_RE = re.compile(r"(?:^|\n)\s*>?\s*\*+([^*]+)\*+\s*")


def extract_last_scene(text: str) -> str:
    """提取对话文本中最后一个场景标记（如 `> **电影院外我爱你告白**` → 电影院外我爱你告白）。"""
    matches = list(_SCENE_MARKER_RE.finditer(text))
    if not matches:
        return ""
    return matches[-1].group(1).strip()


def save_last_scene(persona: str, text_or_scene: str):
    """保存当前角色的导入记录末尾场景，供接续对话时锚定场景。"""
    scene = text_or_scene.strip()
    if not scene:
        return
    # 若传入的是完整对话文本，自动提取最后一个场景标记
    if "\n" in scene or len(scene) > 80:
        scene = extract_last_scene(scene)
        if not scene:
            return
    d = config.DATA_DIR / "last_scenes"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{_safe_coll_suffix(persona)}.json").write_text(
        json.dumps({"persona": persona, "scene": scene, "updated_at": time.time()}, ensure_ascii=False),
        "utf-8",
    )


def load_last_scene(persona: str = "default") -> str:
    """读取当前角色的末尾场景；未记录则返回空字符串。"""
    try:
        f = config.DATA_DIR / "last_scenes" / f"{_safe_coll_suffix(persona)}.json"
        if not f.exists():
            return ""
        return json.loads(f.read_text("utf-8")).get("scene", "")
    except Exception as e:
        print(f"[memory] 读取末尾场景失败: {e}", file=sys.stderr, flush=True)
        return ""
