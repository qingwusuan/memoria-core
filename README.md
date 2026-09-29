# Memoria Core

Memoria Core 是一个本地部署的 **AI 陪伴 / 角色扮演聊天应用**：由 FastAPI 提供后端服务，Vue 3 提供前端界面，ChromaDB + 中文向量模型（bge-small-zh-v1.5）为角色提供**长期记忆**。角色会记住你们之间发生过的事（关系里程碑、偏好、约定、亲密互动等），并通过一套 11 维双层性格引擎持续演化自己的"人格"。

项目代码全部位于本仓库，运行时数据（对话记录、记忆库、性格状态）保存在本地 `data/` 目录，默认不提交到版本库。

---

## 功能特性

- **多角色人格（Persona）管理**
  - 创建 / 编辑 / 删除 / 激活多个角色，每个角色拥有独立的角色指南（system prompt 文本）、独立的记忆库与性格状态；
  - 删除角色前自动备份到 `data/trash/`。
- **长期记忆事件库（ChromaDB 向量检索）**
  - 每轮对话由 LLM 异步提取"值得长期记忆的事件"（摘要 + 重要性 + 原文引用），向量化存入 ChromaDB；
  - 检索时按语义召回最近相关记忆并注入对话 prompt（默认 top-k=6）；
  - 入库前做**语义去重**（向量距离 + 3-gram 文本重叠双重判定），避免记忆图谱无限膨胀；
  - 对话原文同时切块索引（`memoria_snippets`），支持"对话片段"级语义检索与图谱展示。
- **11 维双层性格引擎**
  - 亲和度 / 依赖度 / 攻击性 / 主动性 / 亲密意愿 / 自我认同 / 被抛弃恐惧 / 自我暴露 / 情绪表达 / 嫉妒倾向 / 愤怒方式，每个维度区分**表层表现**与**深层感受**（各在 [-1,1]）；
  - LLM 每 5 轮对话降频分析一次性格漂移，带惯性约束；表里不一（gap>0.6）持续 3 轮会触发"说漏嘴"破裂事件；
  - **了解度（intimacy）**随对话增长，超过 0.4 后性格注入从表层描述切换为深层描述。
- **敏感点管理**
  - 配置"触发关键词 → 目标维度瞬时拉升"，本地匹配即时生效（无 LLM 调用），带冷却轮数防止刷屏。
- **人格图谱可视化**
  - D3 力导向图：事件节点（蓝）+ 对话片段节点（橙），半径按重要性缩放，支持拖拽 / 缩放 / 点击查看详情 / 分类过滤。
- **性格面板**
  - Canvas 雷达图叠加 11 维表层（蓝）与深层（橙）双多边形，维度表格按表里差值降序排列（gap>0.3 红底高亮）。
- **建议栏**
  - 可选开启"普通建议 / 坏坏建议"，以严格格式附在回复末尾，指导用户下一步行动。
- **指令中心**
  - 剧场模式（剧情走向、堕落点评、角色独白、弹幕剧场、显示好感度等 17 项）、系统调优（字数加强、对话加强、时间概念、虚构时间线等 9 项）、上帝视角（全篇总结、电影视角画面等 3 项），指令 payload 随消息提交并强制注入 prompt。
- **对话会话管理**
  - 会话按角色持久化（`data/chat_logs/{角色}/`），支持列表 / 详情 / 改名 / 删除。
- **历史对话导入与场景锚定**
  - 支持粘贴文本或上传文件批量导入历史对话，自动按场景标记拆片、提取事件与片段；记录导入末尾场景，接续对话时自动锚定场景。
- **用户昵称**
  - 自定义被称呼的昵称（默认"影幢"），叙事正文中严格使用该昵称指代用户。

---

## 技术栈

| 层次 | 组件 | 版本要求（以仓库依赖文件为准） |
|---|---|---|
| 后端框架 | FastAPI / Uvicorn / Pydantic | fastapi>=0.110.0 / uvicorn>=0.29.0 / pydantic>=2.0.0 |
| 向量存储 | ChromaDB（PersistentClient，cosine 距离） | chromadb>=0.4.0 |
| 向量模型 | SentenceTransformer + bge-small-zh-v1.5（dim=512） | sentence-transformers>=2.2.0 |
| LLM 客户端 | OpenAI SDK（兼容 DeepSeek / Kimi） | openai>=1.0.0 |
| 环境配置 | python-dotenv | python-dotenv>=1.0.0 |
| 前端框架 | Vue 3（Composition API + `<script setup>`）/ Vue Router 4（hash）/ Pinia | vue ^3.4 / vue-router ^4.3 / pinia ^2.1 |
| 前端构建 | Vite | vite ^6.4.3（dev 端口 5173，`/api` 代理到 8000） |
| 可视化 | D3.js | d3 ^7.9 |
| 网络请求 | Axios | axios ^1.7 |

后端为 Python 3.10+（开发环境为 3.11）；前端为 Node.js + npm。

---

## 目录结构

```
memoria-core/
├── backend/
│   ├── main.py                    # FastAPI 应用：全部 API 路由、CORS、静态托管、会话管理
│   ├── config.py                  # 配置：路径、LLM / Embedding / Chroma 参数（从 .env 读取）
│   ├── agents/
│   │   ├── orchestrator.py        # 对话编排器：性格分析→主回复→异步事件入库
│   │   ├── personality.py         # 性格分析 Agent（状态读写 / 降频分析 / 敏感点）
│   │   ├── responder.py           # 主回复 Agent（空回复重试 / 字数加强续写）
│   │   ├── memory_extractor.py    # 事件提取入库 Agent
│   │   ├── base.py                # Agent 基类
│   │   └── util.py                # 建议栏拆分、汉字计数等工具
│   ├── engines/
│   │   ├── memory.py              # 记忆引擎：事件提取/向量化/去重/检索/片段索引/图谱
│   │   ├── personality.py         # 性格引擎：11 维双层状态/漂移/破裂/敏感点/注入（纯计算）
│   │   └── prompt_builder.py      # Prompt 拼接器：角色指南+性格注入+时间感知+记忆检索
│   ├── llm/
│   │   └── deepseek.py            # LLM 客户端封装（DeepSeek/Kimi 路由、双锁串行、429 退避）
│   └── models/
│       └── schemas.py             # Pydantic 数据模型
├── frontend/
│   ├── package.json               # 前端依赖与脚本（dev / build / preview）
│   ├── vite.config.js             # Vite 配置：/api 代理（可用 MEMORIA_API_TARGET 覆盖）
│   ├── index.html
│   └── src/
│       ├── main.js                # 路由 + Pinia 挂载
│       ├── App.vue                # 顶栏导航 + 全局 CSS 变量
│       ├── api.js                 # Axios 封装（所有后端接口，角色名编码）
│       ├── instructs.js           # 指令中心数据（剧场模式/系统调优/上帝视角）
│       └── views/
│           ├── CharacterManager.vue   # 角色管理页
│           ├── Chat.vue               # 聊天页（建议栏 / 指令 / 动作输入）
│           ├── MemoryGraph.vue        # 记忆图谱页（D3 力导向图）
│           └── PersonalityPanel.vue   # 性格面板页（Canvas 雷达图）
├── prompts/
│   └── event_extraction.txt       # 事件提取提示词
├── data/                          # 运行时数据（被 .gitignore 排除，不入库）
├── requirements.txt               # 后端依赖
├── .env.example                   # 环境变量模板
├── .gitignore
└── FRONTEND_BRIEF.md              # 前端交接文档（页面与 API 说明）
```

---

## 快速开始（Windows）

前置要求：Python 3.10+、Node.js（含 npm）。

### 1. 安装后端依赖

```powershell
# 进入项目根目录
cd C:\path\to\memoria-core

# （可选）创建并激活虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

```powershell
copy .env.example .env
```

编辑 `.env`（至少必填两项，详见下方配置说明）：

```dotenv
# 必填：LLM 供应商（deepseek 或 kimi）
LLM_PROVIDER=deepseek
# 必填：对应供应商的 API Key
DEEPSEEK_API_KEY=sk-xxxxxxxx
# 必填：Embedding 模型路径（本地目录）或 HuggingFace 模型名
EMBEDDING_MODEL=C:/path/to/bge-small-zh-v1.5
```

> `EMBEDDING_MODEL` 为**必填项**：缺失时后端启动会直接报错。可填写本地已下载的模型目录（如 `C:\Users\...\models\bge-small-zh-v1.5`，需与 `EMBEDDING_DIM=512` 匹配），也可填写 HuggingFace 模型名（如 `BAAI/bge-small-zh-v1.5`，首次运行自动下载）。

### 3. 启动后端

```powershell
uvicorn backend.main:app --port 8000 --host 127.0.0.1
```

后端启动后：
- API 服务地址：`http://127.0.0.1:8000`
- 若已执行过前端构建（`frontend/dist/` 存在），访问 `http://127.0.0.1:8000` 可直接看到构建后的前端页面。

### 4. 启动前端（开发模式）

新开一个终端：

```powershell
cd frontend
npm install
npm run dev
```

浏览器访问 `http://localhost:5173`。Vite 已配置将 `/api` 请求代理到 `http://localhost:8000`（默认值；可通过环境变量 `MEMORIA_API_TARGET` 覆盖代理目标）。

### 5. 前端生产构建

```powershell
cd frontend
npm run build
```

产物输出到 `frontend/dist/`，由后端自动静态托管。

---

## 配置说明（.env）

| 变量 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `LLM_PROVIDER` | 否 | `deepseek` | LLM 供应商：`deepseek` 或 `kimi` |
| `DEEPSEEK_API_KEY` | 视供应商 | 空 | DeepSeek API Key |
| `DEEPSEEK_BASE_URL` | 否 | `https://api.deepseek.com/v1` | DeepSeek API 地址 |
| `DEEPSEEK_MODEL` | 否 | `deepseek-chat` | DeepSeek 模型名 |
| `KIMI_API_KEY` | 视供应商 | 空 | Kimi（Moonshot）API Key |
| `KIMI_BASE_URL` | 否 | `https://api.moonshot.cn/v1` | Kimi API 地址 |
| `KIMI_MODEL` | 否 | `moonshot-v1-32k` | Kimi 模型名 |
| `EMBEDDING_MODEL` | **是** | 无（缺失报错） | Embedding 模型本地路径或 HF 模型名（bge-small-zh-v1.5，dim=512） |
| `EMBEDDING_DIM` | 否 | `512` | Embedding 输出维度 |
| `CHROMA_COLLECTION` | 否 | `memoria_events` | ChromaDB 事件集合名前缀 |
| `CHROMA_SIMILARITY_TOP_K` | 否 | `10` | 记忆检索召回数上限 |
| `DEFAULT_DECAY_PER_DAY` | 否 | `0.02` | 记忆每日衰减系数 |
| `MIN_IMPORTANCE_TO_KEEP` | 否 | `0.0` | 记忆保留最低重要性 |
| `MEMORIA_API_TARGET` | 否 | `http://localhost:8000` | 前端 Vite 代理目标（`vite.config.js` 读取） |
| `MEMORIA_SERVE_STATIC` | 否 | — | 生产同源伺服开关（后端直接托管前端构建产物，无需跨域） |

---

## API 概览

基础地址：`http://127.0.0.1:8000`。当前版本**无内置用户鉴权**（未配置登录 / Token），CORS 白名单仅允许本机前端来源，详见"安全说明"。

### 统计

```
GET /api/stats
→ { event_count, snippet_count, personality: { round_count, intimacy }, active_persona, total_personas }
```

### 对话

```
POST /api/chat
请求体：{ message: string, history: [{role, content}], suggest_normal?: bool, suggest_naughty?: bool, instructions?: string[], action?: string }
→ { reply: string, personality_snapshot: { round_count, intimacy, top_gaps: [{dimension, surface, deep, gap}] } | null }
```

- `history` 中 role 可取 `user` / `assistant` / `action`；
- `suggest_normal` / `suggest_naughty` 控制回复末尾是否附带建议栏；
- `instructions` 为指令中心选中的指令 payload，强制注入 prompt 执行；
- `action` 表示用户要执行的"动作"（不当作说的话）。

### 记忆检索

```
GET /api/memories/search?q=<关键词>&top_k=<数量>
→ { results: [{ id, summary, importance, distance, quotes }] }

GET /api/snippets/search?q=<关键词>&top_k=<数量>
→ { results: [{ id, text, distance }] }
```

### 记忆图谱

```
GET /api/memories/graph
→ { nodes: [{ id, type: "event"|"snippet", label, importance?, ts }], total_events, total_snippets }
```

### 性格

```
GET /api/personality
→ { round_count, intimacy, dimensions: [{index, name, surface, deep, gap}], categories, sensitive_points: [...] }

POST /api/personality/reset
→ { status: "ok" }

GET /api/personality/sensitive_points
POST /api/personality/sensitive_points   # 新增敏感点
PUT /api/personality/sensitive_points    # 整体替换敏感点表
```

### 会话管理

```
POST   /api/chat/sessions                 # 新建会话
GET    /api/chat/sessions                 # 会话列表
GET    /api/chat/sessions/{session_id}    # 会话详情（含消息）
PUT    /api/chat/sessions/{session_id}    # 更新会话（改名等）
DELETE /api/chat/sessions/{session_id}    # 删除会话
```

### 对话导入

```
POST /api/dialogue/ingest
请求体：{ dialogue: string, run_personality?: bool }
→ { events_stored: int, snippets_stored: int }

POST /api/dialogue/upload                 # 上传对话文件批量导入
```

### 角色管理（Persona CRUD）

```
GET    /api/personas                      → [{ name, guide, is_active }]
GET    /api/personas/{name}               → { name, guide, is_active }
POST   /api/personas                      # 新建角色 { name, guide }
PUT    /api/personas/{name}               # 更新角色指南
DELETE /api/personas/{name}               # 删除角色（先备份到 data/trash）
POST   /api/personas/{name}/activate      # 切换当前活跃角色
```

### 用户资料

```
GET /api/user/profile                     # 获取昵称
PUT /api/user/profile                     # 更新昵称 { nickname }
```

---

## 数据存储说明

所有运行时数据保存在项目根目录 `data/` 下，已被 `.gitignore` 排除（含隐私对话与人格状态，不进入版本库）：

| 路径 | 内容 |
|---|---|
| `data/chroma/` | ChromaDB 持久化目录。每个角色独立两个集合：事件集合 `memoria_events_<suffix>`、对话片段集合 `memoria_snippets_<suffix>`（角色名为非 ASCII 时用哈希后缀隔离） |
| `data/personas/` | 角色定义（角色指南） |
| `data/personalities/{角色}/state.json` | 每个角色的 11 维双层性格状态、了解度、敏感点表 |
| `data/chat_logs/{角色}/` | 每个角色的对话会话记录（JSON） |
| `data/last_scenes/` | 导入记录末尾场景锚点（供接续对话定位场景） |
| `data/user_nickname.json` | 用户昵称（默认"影幢"） |
| `data/active_persona.json` | 当前活跃角色 |
| `data/trash/` | 删除角色前的备份 |

其他目录：
- `prompts/event_extraction.txt`：事件提取提示词模板；
- `logs/`、`backend/uvicorn_*.log`：运行日志（`.gitignore` 已排除）。

---

## 安全说明

- **角色名路径校验**：所有按角色名访问磁盘 / 集合的路径均经过安全校验（`_safe_persona_name`），拒绝 `..` 等路径穿越字符；ChromaDB 集合名对非 ASCII 角色名做确定性哈希映射，避免非法集合名。
- **会话原子写与写锁**：会话文件采用原子写入 + 全局写锁（`_atomic_write_text` + `_session_write_lock`），避免并发覆盖与串档；事件入库闭包固定 persona，防止角色切换期间串档。
- **LLM 并发控制**：Kimi 账号组织级并发为 1，客户端按"主对话锁 + 后台任务锁"双锁串行（各自等待超时 300s），429 限流自动指数退避重试，后台任务不阻塞主对话。
- **CORS 白名单**：仅允许 `http://localhost:5173` 与 `http://127.0.0.1:5173`（开发前端来源），未开放 `*`；生产建议通过 `MEMORIA_SERVE_STATIC` 同源伺服，无跨域需求。
- **隐私与数据边界**：对话记录、记忆、人格状态均存储在本地 `data/`，仓库 `.gitignore` 明确排除，避免隐私泄漏到公开仓库。
- **删除保护**：删除角色前先备份至 `data/trash/`；记忆清空仅作用于当前角色的 Chroma 集合。
- **提示词注入约束**：指令中心 payload 与消息中的 `【指令名】` 前缀按固定优先级执行，Prompt 拼接器对检索记忆只注入语义摘要、不带原文引用，防止旧文风回流。

> 注意：本项目目前**没有内置用户鉴权**，仅适合本机 / 局域网信任环境使用；请勿将服务直接暴露到公网。如确需公网访问，请自行在反向代理层增加认证。

---

## 常见问题（FAQ）

**Q1：启动后端报错 `EMBEDDING_MODEL 未配置`？**
A：`EMBEDDING_MODEL` 是必填项。复制 `.env.example` 为 `.env`，填写本地模型目录（如 `C:/Users/.../models/bge-small-zh-v1.5`）或 HF 模型名（如 `BAAI/bge-small-zh-v1.5`）后重启。

**Q2：前端页面能打开但接口 404 / 跨域报错？**
A：确认后端已启动（`uvicorn backend.main:app --port 8000`）；确认访问的是 `http://localhost:5173`（Vite 代理 `/api` → 8000），CORS 白名单只放行 `localhost` 与 `127.0.0.1` 的 5173 来源。

**Q3：为什么有些轮次对话没有被记入记忆 / 图谱节点很少？**
A：事件提取是**异步后台任务**且是条件触发的：寒暄轮（用户无实质内容、回复正文过短）会跳过入库；提取受 LLM 限流影响会重试。可查看后端日志（`backend/uvicorn_out*.log`）中的 `[memory]` 输出确认入库情况。

**Q4：用 Kimi 时频繁报 429 / 请求排队？**
A：客户端已内置主/后台双锁串行与退避重试；若仍频繁 429，通常是账号组织级并发配额（org max concurrency=1）被其他请求占用，请检查该账号是否有并发调用，或切换 `LLM_PROVIDER=deepseek`。

**Q5：导入的长对话被截断 / 提取不全？**
A：导入会自动按场景标记（如 `> **场景名**`）拆片，单场景超过 6000 字符再自动切子块，逐片提取；单场景提取失败不会中断整批导入。若希望精确分段，可在文本中多用场景标记。

**Q6：接续对话时角色场景跳变？**
A：导入文本末尾的场景会被记录（`data/last_scenes/`），接续消息带"（接续对话）"前缀时会自动锚定该场景与上一段叙事末尾进行检索与续写。

**Q7：想彻底清空某个角色的记忆？**
A：调用 `POST /api/personality/reset` 重置性格状态；记忆清空当前无独立前端入口，可停止服务后删除 `data/chroma/` 中对应角色的集合目录（注意该操作不可恢复，请先备份）。

**Q8：后端端口被占用？**
A：换端口启动即可，如 `uvicorn backend.main:app --port 8001`；若同时使用前端开发模式，请同步调整 `MEMORIA_API_TARGET` 或 `vite.config.js` 中的代理目标。

---

## 说明

本项目为个人 / 学习用途的本地应用，运行所需的 LLM API Key 与 Embedding 模型均需自行准备。文档中的功能与接口均以仓库代码实际实现为准。
