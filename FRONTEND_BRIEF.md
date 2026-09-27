# Memoria Core 前端交接文档

## 技术栈
- Vue 3 (Composition API + `<script setup>`)
- Vue Router 4 (hash 模式)
- Pinia (状态管理，已挂载，按需使用)
- D3.js v7
- Axios
- Vite 5

## 项目结构
```
frontend/
├── package.json
├── vite.config.js          # 已配 proxy: /api → localhost:8000
├── index.html
└── src/
    ├── main.js             # 路由 + Pinia 挂载
    ├── App.vue             # 顶栏导航 + <router-view>
    ├── api.js              # Axios 封装，所有后端接口
    └── views/
        ├── CharacterManager.vue   # 角色管理
        ├── MemoryGraph.vue        # D3 力导向图
        └── PersonalityPanel.vue   # Canvas 雷达图
```

CSS 变量（定义在 App.vue `:root`）：
```css
--bg-root: #0a0a0f;       /* 页面底色 */
--bg-surface: #111118;    /* 次级背景 */
--bg-card: #16161f;       /* 卡片背景 */
--bg-hover: #1e1e2c;      /* hover 态 */
--border: #252536;        /* 边框 */
--text-primary: #e8e8f0;  /* 主文字 */
--text-secondary: #9898b0;
--text-muted: #606078;
--accent: #7289ff;        /* 主题色（蓝紫） */
--warn: #f0a060;
--danger: #e06060;
--radius: 12px;
--transition: 0.2s cubic-bezier(0.4, 0, 0.2, 1);
```

---

## 三个页面功能需求

### 1. 角色管理 `/character`
- **左侧面板 (260px)**：角色列表，点击选中，当前活跃角色带蓝色标记
- **右侧面板**：选中角色的详情展示（角色指南纯文本），可编辑、启用、删除
- **新建弹窗**：输入名称 + 角色指南文本
- **角色指南**本质是一段 system prompt 文本，描述角色性格/背景/说话方式

### 2. 记忆图谱 `/memory`
- D3 力导向图（force simulation）
- 节点分两类：**事件**（蓝色）和**对话片段**（橙色），半径按重要性缩放
- 顶部 chip 按钮过滤显示/隐藏两类节点
- 点击节点弹出详情面板（右下角浮层，含节点内容 + 重要性）
- 支持拖拽、缩放（d3.zoom）
- 空状态：无数据时显示占位提示

### 3. 性格面板 `/personality`
- 从 `/api/personality` 获取数据
- **雷达图**：Canvas 绘制，11 维（表层蓝色 + 深层橙色双多边形叠加）
- **维度表格**：11 维按 gap 绝对值降序排列，gap > 0.3 红底高亮
- **敏感点列表**：触发器关键词 → 目标维度 → delta，底部卡片
- 空状态同上

---

## 后端 API 全部端点

Base: `http://localhost:8000`（Vite dev 自动 proxy `/api`）

### 统计
```
GET /api/stats
→ { event_count, snippet_count, personality: { round_count, intimacy }, active_persona, total_personas }
```

### 对话
```
POST /api/chat
← { message: string, history: [{role,content}] }
→ { reply: string, personality_snapshot: { round_count, intimacy, top_gaps: [{dimension, surface, deep, gap}] } }

POST /api/dialogue/ingest
← { dialogue: string, run_personality: bool }
→ { events_stored: int, snippets_stored: int }
```

### 记忆检索
```
GET /api/memories/search?q=xxx&top_k=10
→ { results: [{id, summary, importance, distance, quotes, ...}] }

GET /api/snippets/search?q=xxx&top_k=5
→ { results: [{id, text, distance, ...}] }
```

### 记忆图谱
```
GET /api/memories/graph
→ { nodes: [{id, type:"event"|"snippet", label, importance?, ts}], total_events, total_snippets }
```

### 性格
```
GET /api/personality
→ {
    round_count, intimacy,
    dimensions: [{index, name, surface, deep, gap}],
    categories: { "亲近-疏离": [0,1,2], ... },
    sensitive_points: [{keywords, dimension, delta, description}]
  }

POST /api/personality/reset
→ { status: "ok" }
```

### 角色 CRUD
```
GET    /api/personas              → [{ name, guide, is_active }]
GET    /api/personas/{name}       → { name, guide, is_active }
POST   /api/personas              ← { name, guide }  → { name, guide, is_active }
PUT    /api/personas/{name}       ← { name, guide }  → { name, guide, is_active }
DELETE /api/personas/{name}       → { status: "ok" }
POST   /api/personas/{name}/activate  → { status: "ok", active_persona }
```

---

## 文件操作注意事项
- `write_file` 遇到已存在文件会**自动重命名**（加时间戳后缀），覆盖需用 `Move-Item -Force`
- `edit_file` 用 `old_str`/`new_str` 做精确替换
- 构建命令：`npm install && npm run build`（产物在 `frontend/dist/`）
- 开发命令：`npm run dev`（端口 5173，代理到 8000）

## 后端启动
```bash
cd output/memoria-core
uvicorn backend.main:app --port 8000 --host 127.0.0.1
```
后端已自动挂载 `frontend/dist/` 为静态文件，访问 `http://localhost:8000` 即可看到构建后的前端。
