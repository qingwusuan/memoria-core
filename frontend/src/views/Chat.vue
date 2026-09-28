<template>
  <div class="chat-root">
    <!-- 移动端顶栏：会话列表开关 + 当前角色 -->
    <div class="chat-mobile-bar">
      <button class="chat-mobile-menu" @click="toggleMobileSidebar" title="会话列表">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
      </button>
      <span class="chat-mobile-title">{{ activePersona || '对话' }}</span>
    </div>

    <!-- 移动端会话列表抽屉遮罩 -->
    <div v-if="mobileSidebar" class="chat-sidebar-mask" @click="mobileSidebar = false"></div>

    <!-- 左侧会话列表 -->
    <aside class="chat-sidebar" :class="{ open: mobileSidebar }">
      <div class="sidebar-header">
        <span>{{ activePersona || '角色' }}</span>
        <button class="sidebar-new-btn" @click="newSession" title="新建对话">+</button>
      </div>
      <div class="sidebar-list">
        <div
          v-for="s in sessions"
          :key="s.id"
          :class="['sidebar-item', { active: s.id === sessionId }]"
          @click="switchSession(s.id)"
        >
          <span class="sidebar-title">{{ s.title }}</span>
          <span class="sidebar-time">{{ fmtTime(s.updated_at || s.created_at) }}</span>
          <button class="sidebar-del" @click.stop="removeSession(s.id)" title="删除">×</button>
        </div>
        <div v-if="!sessions.length" class="sidebar-empty">暂无对话</div>
      </div>
    </aside>

    <!-- 右侧聊天区 -->
    <div class="chat-main">
      <div class="chat-body" ref="bodyRef">
        <div v-if="!messages.length && !loading" class="chat-empty">
          发送第一条消息，或点击 + 上传对话记录文件。
        </div>

        <div v-for="(m, i) in messages" :key="i" :class="['msg', m.role]">
          <!-- 用户消息：可编辑 -->
          <div v-if="m.role === 'user'" class="msg-row">
            <div v-if="editingIdx === i" class="msg-edit-wrap">
              <input
                v-model="editText"
                class="msg-edit-input"
                @keydown.enter="commitEdit(i)"
              />
              <div class="msg-edit-actions">
                <button class="edit-btn" @click="commitEdit(i)">确定</button>
                <button class="edit-btn cancel" @click="cancelEdit">取消</button>
              </div>
            </div>
            <div v-else class="user-bubble-wrap">
              <div class="msg-bubble user-bubble" @dblclick="startEdit(i, m.content)">
                {{ m.content }}
              </div>
            </div>
          </div>

          <!-- 系统消息（导入结果等）：居中灰条 -->
          <div v-else-if="m.role === 'system'" class="msg-row sys-row">
            <div class="msg-bubble sys-bubble">{{ m.content }}</div>
          </div>

          <!-- 动作消息：用户要做的动作/剧情指令（区别于普通消息） -->
          <div v-else-if="m.role === 'action'" class="msg-row action-row">
            <div class="msg-bubble action-bubble">
              <span class="action-tag">动作</span>{{ m.content }}
            </div>
          </div>

          <!-- AI 消息：可刷新 -->
          <div v-else class="msg-row assistant-row">
            <div class="assistant-content">
              <div v-if="parseSuggest(m.content).body" class="msg-bubble assistant-bubble">{{ parseSuggest(m.content).body }}</div>
              <div v-if="parseSuggest(m.content).groups.length" class="suggest-panel">
                <div v-for="(g, gi) in parseSuggest(m.content).groups" :key="gi" class="suggest-group">
                  <div class="suggest-label" :class="g.type">{{ g.label }}</div>
                  <div v-for="(it, ii) in g.items" :key="ii" class="suggest-item">
                    <span class="suggest-num">{{ it.num }}</span>
                    <span class="suggest-text">{{ it.text }}</span>
                  </div>
                </div>
              </div>
            </div>
            <button class="refresh-btn" title="重新生成" @click="regenerate(i)" :disabled="loading">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
              </svg>
            </button>
          </div>
        </div>

        <div v-if="loading" class="msg assistant msg-row assistant-row">
          <div class="msg-bubble assistant-bubble thinking">…</div>
        </div>
      </div>

      <div class="chat-input-area">
        <div class="suggest-toggles">
          <label class="toggle-item" :class="{ on: suggestNormal }">
            <input type="checkbox" v-model="suggestNormal" />
            <span class="toggle-box"></span>
            <span>普通建议</span>
          </label>
          <label class="toggle-item" :class="{ on: suggestNaughty }">
            <input type="checkbox" v-model="suggestNaughty" />
            <span class="toggle-box"></span>
            <span>坏坏建议</span>
          </label>
          <button class="instruct-btn" :class="{ on: showInstruct }" @click="toggleInstruct">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            指令中心
          </button>
          <button class="instruct-btn nick-btn" :class="{ on: showNick }" @click="toggleNick">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
            </svg>
            昵称
          </button>
        </div>

        <!-- 昵称设置：自定义用户昵称（AI 对用户的称呼） -->
        <div v-if="showNick" class="nick-panel">
          <div class="nick-head">
            <span class="nick-title">我的昵称</span>
            <span class="nick-hint">AI 叙事中会以此称呼你（1-10 字）</span>
          </div>
          <div class="nick-body">
            <input
              v-model="nickInput"
              class="nick-input"
              placeholder="输入昵称，如：影幢"
              maxlength="10"
              @keydown.enter="saveNick"
            />
            <button class="nick-save" @click="saveNick">保存</button>
          </div>
          <div v-if="nickMsg" class="nick-msg" :class="{ ok: nickOk }">{{ nickMsg }}</div>
        </div>

        <!-- 指令中心：剧场模式 / 系统调优 / 上帝视角 -->
        <div v-if="showInstruct" class="instruct-panel">
          <div class="instruct-head">
            <span class="instruct-title">指令中心</span>
            <span class="instruct-cur" v-if="instructCat === 'theater'">当前：剧场模式</span>
            <span class="instruct-cur" v-else-if="instructCat === 'sys'">当前：系统调优</span>
            <span class="instruct-cur" v-else>当前：上帝视角</span>
            <button class="instruct-clear" @click="clearCmds">清除</button>
          </div>
          <div class="instruct-tabs">
            <button
              v-for="cat in instructCats"
              :key="cat.key"
              :class="['instruct-tab', { active: instructCat === cat.key }]"
              @click="instructCat = cat.key"
            >{{ cat.label }}<span class="instruct-count">{{ catCount(cat.key) }}</span></button>
          </div>
          <div class="instruct-list">
            <button
              v-for="cmd in filteredInstructs"
              :key="cmd.name"
              :class="['instruct-item', { selected: isSelected(cmd.name) }]"
              @click="toggleCmd(cmd.name)"
            >
              <span class="instruct-name">{{ cmd.name }}</span>
              <span class="instruct-desc">{{ cmd.desc }}</span>
            </button>
          </div>
        </div>

        <!-- 已选指令胶囊 -->
        <div v-if="selectedCmds.length" class="cmd-chips">
          <span v-for="name in selectedCmds" :key="name" class="cmd-chip">
            {{ name }}<button class="chip-x" @click="removeCmd(name)">×</button>
          </span>
          <button class="chip-clear" @click="clearCmds">移除指令</button>
        </div>

        <div class="chat-input-bar">
          <label class="upload-btn" title="上传对话记录 (.txt)">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
            </svg>
            <input type="file" accept=".txt" hidden @change="onFileSelected" />
          </label>
          <textarea
            ref="inputRef"
            v-model="input"
            class="chat-input"
            :placeholder="`给 ${activePersona || '角色'} 发消息`"
            @keydown.enter.exact.prevent="send"
            @input="autoResize"
          ></textarea>
          <button class="send-btn" :class="{ active: input.trim() && !loading }" :disabled="!input.trim() || loading" @click="send">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
              <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
            </svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, watch } from 'vue'
import api from '../api.js'
import { instructCats, instructs } from '../instructs.js'

const messages = ref([])
const input = ref('')
const loading = ref(false)
const activePersona = ref('')
const bodyRef = ref(null)
const inputRef = ref(null)
const fileInputRef = ref(null)

const editingIdx = ref(-1)
const editText = ref('')
const suggestNormal = ref(false)
const suggestNaughty = ref(false)

// 移动端会话列表抽屉开关
const mobileSidebar = ref(false)
function toggleMobileSidebar() {
  mobileSidebar.value = !mobileSidebar.value
}

// ──────────── 指令中心（仿柚姬AI）────────────
const showInstruct = ref(false)
const instructCat = ref('theater')
const filteredInstructs = computed(() =>
  instructs.filter(c => c.cat === instructCat.value)
)
function catCount(key) {
  return instructs.filter(c => c.cat === key).length
}

// 已选指令（可多选，发送时随消息提交）
const selectedCmds = ref([])
function isSelected(name) {
  return selectedCmds.value.includes(name)
}
function toggleCmd(name) {
  const i = selectedCmds.value.indexOf(name)
  if (i >= 0) selectedCmds.value.splice(i, 1)
  else selectedCmds.value.push(name)
}
function removeCmd(name) {
  const i = selectedCmds.value.indexOf(name)
  if (i >= 0) selectedCmds.value.splice(i, 1)
}
function clearCmds() {
  selectedCmds.value = []
}

function toggleInstruct() {
  showInstruct.value = !showInstruct.value
}

// ──────────── 用户昵称设置 ────────────
const showNick = ref(false)
const nickInput = ref('')
const nickMsg = ref('')
const nickOk = ref(false)

async function loadNickname() {
  try {
    const r = await api.getProfile()
    nickInput.value = r.data?.nickname || ''
  } catch {
    nickInput.value = ''
  }
}

function toggleNick() {
  showNick.value = !showNick.value
  if (showNick.value) nickMsg.value = ''
}

async function saveNick() {
  const v = nickInput.value.trim()
  if (!v) {
    nickMsg.value = '昵称不能为空'
    nickOk.value = false
    return
  }
  if (v.length > 10) {
    nickMsg.value = '昵称不能超过 10 个字符'
    nickOk.value = false
    return
  }
  try {
    const r = await api.updateProfile(v)
    nickInput.value = r.data?.nickname || v
    nickMsg.value = '已保存，AI 将以此称呼你'
    nickOk.value = true
    setTimeout(() => { nickMsg.value = '' }, 3000)
  } catch (e) {
    nickMsg.value = '保存失败：' + (e.response?.data?.detail || e.message)
    nickOk.value = false
  }
}

// 会话
const sessionId = ref(null)
const sessions = ref([])

onMounted(async () => {
  try {
    const r = await api.getStats()
    activePersona.value = r.data?.active_persona || ''
  } catch {}
  await loadNickname()
  await loadSessions()
  // 自动打开最近一次会话
  if (sessions.value.length) {
    await switchSession(sessions.value[0].id)
  }
  inputRef.value?.focus()
})

watch(messages, () => {
  nextTick(() => {
    if (bodyRef.value) bodyRef.value.scrollTop = bodyRef.value.scrollHeight
  })
}, { deep: true })

// ──────────── 会话管理 ────────────
async function loadSessions() {
  try {
    const r = await api.listSessions()
    sessions.value = r.data.sessions || []
  } catch { sessions.value = [] }
}

async function newSession() {
  sessionId.value = null
  messages.value = []
  input.value = ''
}

async function switchSession(id) {
  mobileSidebar.value = false
  try {
    const r = await api.getSession(id)
    sessionId.value = id
    messages.value = r.data.session.messages || []
    nextTick(() => { if (bodyRef.value) bodyRef.value.scrollTop = bodyRef.value.scrollHeight })
  } catch {
    // 会话不存在，从列表中移除
    sessions.value = sessions.value.filter(s => s.id !== id)
    if (sessionId.value === id) newSession()
  }
}

async function removeSession(id) {
  try {
    await api.deleteSession(id)
    sessions.value = sessions.value.filter(s => s.id !== id)
    if (sessionId.value === id) newSession()
  } catch {}
}

async function ensureSession() {
  if (sessionId.value) return
  try {
    const r = await api.createSession()
    sessionId.value = r.data.session_id
    // 刷入列表
    sessions.value.unshift({ id: r.data.session_id, title: r.data.title, created_at: new Date().toISOString() })
  } catch {}
}

async function persistSession() {
  if (!sessionId.value || !messages.value.length) return
  try {
    const r = await api.saveSession(sessionId.value, messages.value)
    // 更新列表标题
    const s = sessions.value.find(x => x.id === sessionId.value)
    if (s && r.data.title) s.title = r.data.title
  } catch {}
}

function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  if (d.toDateString() === now.toDateString())
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  return `${d.getMonth() + 1}/${d.getDate()}`
}

// ──────────── 附件上传 ────────────
function onFileSelected(e) {
  const f = e.target.files?.[0]
  if (!f) return
  if (!f.name.endsWith('.txt')) {
    alert('仅支持 .txt 文本文件')
    e.target.value = ''
    return
  }
  const fd = new FormData()
  fd.append('file', f)
  api.uploadDialogue(fd).then(async r => {
    const d = r.data
    await ensureSession()
    messages.value.push({
      role: 'system',
      content: `已导入「${d.filename}」：提取 ${d.events_stored} 个事件。她会记住经历过的事，按她自己的方式去回忆。`
    })
    // 注入对话末尾上下文，让后续消息能从导入内容的末尾自然接续
    if (d.tail_turns && d.tail_turns.length) {
      for (const t of d.tail_turns) {
        messages.value.push({ role: t.role === 'user' ? 'user' : 'assistant', content: t.content })
      }
      messages.value.push({
        role: 'system',
        content: `已载入对话末尾 ${d.tail_turns.length} 条消息，可以直接继续接续。`
      })
    }
    persistSession()
  }).catch(err => {
    messages.value.push({
      role: 'system',
      content: '导入失败：' + (err.response?.data?.detail || err.message)
    })
  }).finally(() => {
    e.target.value = ''
    scrollToBottom()
  })
}

// ──────────── 消息编辑 ────────────
function startEdit(i, text) {
  editingIdx.value = i
  editText.value = text
}
function cancelEdit() {
  editingIdx.value = -1
  editText.value = ''
}
function commitEdit(i) {
  const v = editText.value.trim()
  if (!v) { cancelEdit(); return }
  messages.value[i].content = v
  // 编辑后：截断该条之后的所有旧消息，让 AI 基于新输入重新思考回复
  messages.value.splice(i + 1)
  editingIdx.value = -1
  editText.value = ''
  regenerateAfterEdit(i)
}

// 编辑消息后自动重新生成 AI 回复
async function regenerateAfterEdit(userIdx) {
  if (loading.value) return
  const lastMsg = messages.value[userIdx]
  if (!lastMsg || lastMsg.role !== 'user') return
  loading.value = true
  try {
    const history = []
    for (let j = 0; j < userIdx; j++) {
      const m = messages.value[j]
      if (m.role === 'system') continue
      history.push({ role: m.role, content: m.content })
    }
    const r = await api.chat(lastMsg.content, history, {
      suggest_normal: suggestNormal.value,
      suggest_naughty: suggestNaughty.value,
    })
    messages.value.push({ role: 'assistant', content: r.data.reply })
    persistSession()
  } catch (e) {
    messages.value.push({ role: 'assistant', content: '（请求失败，请检查后端是否运行）' })
  } finally {
    loading.value = false
  }
}

// ──────────── 建议栏解析（统一展示格式）────────────
// 将 AI 回复中的「普通建议/坏坏建议」栏从正文剥离并解析为结构化分组，
// 即使模型输出变体（换行/引号/编号变化），展示层也统一为固定卡片。
function parseSuggest(content) {
  let text = String(content || '').replace(/\r\n?/g, '\n')
  // AI 偶发把建议栏用 markdown 代码块包裹/重复输出，先剥掉围栏防止污染正文与分段
  text = text.replace(/```+/g, '')
  const labelRe = /(普通建议|坏坏建议)[:：]/g
  const labels = []
  let m
  while ((m = labelRe.exec(text))) labels.push({ label: m[1], index: m.index })

  // 同一类标签只渲染第一次出现（AI 曾把建议栏整体重复输出一遍，去重避免重复区块）
  if (!labels.length) return { body: text.trim(), groups: [] }

  // 建议栏块边界：每个标签从「标签起始」到「下一个标签或正文区块标记」为止，
  // 防止 AI 把建议栏写在消息开头/中间（后面还有正文、监控小剧场、堕落小天使等）时，
  // 把建议栏后面的正文吞进最后一条建议，或把标签本身混入正文。
  const BLOCK_MARKS = ['<pre>', '堕落小天使', '堕落点评', '监控小剧场', '隐秘监控', '剧情走向', '截图点评']
  // 先为「所有」标签构建块（含 AI 重复输出的同类建议栏），
  // 渲染时同类只取第一次，但 body 切割必须覆盖全部块，防止重复建议栏原文漏进正文。
  const allBlocks = []
  for (let i = 0; i < labels.length; i++) {
    const lab = labels[i]
    const segStart = lab.index + lab.label.length + 1
    const nextLabel = labels.find(l => l.index > lab.index)
    let blockEnd = nextLabel ? nextLabel.index : text.length
    if (!nextLabel) {
      const rest = text.slice(segStart)
      const re = new RegExp('(' + BLOCK_MARKS.join('|') + ')')
      const idx = rest.search(re)
      if (idx > 0) blockEnd = segStart + idx
    }
    allBlocks.push({ lab, segStart, blockEnd })
  }

  // 渲染去重：同类标签只渲染第一次出现的块
  const seen = new Set()
  const blocks = allBlocks.filter(b => {
    if (seen.has(b.lab.label)) return false
    seen.add(b.lab.label)
    return true
  })

  // body = 所有建议栏块（含重复块）之外的文本（标签本身也不属于正文）
  const bodyParts = []
  let cursor = 0
  for (const b of allBlocks) {
    if (b.lab.index > cursor) bodyParts.push(text.slice(cursor, b.lab.index))
    cursor = Math.max(cursor, b.blockEnd)
  }
  if (cursor < text.length) bodyParts.push(text.slice(cursor))
  const body = bodyParts.join('\n').trim().replace(/<\/?pre>/g, '')

  const groups = blocks.map((b) => {
    const seg = text.slice(b.segStart, b.blockEnd).trim()
    const items = []
    // 编号前不设分隔符白名单：AI 常把多条建议写在同一行，编号前可能是中文句号、引号或空白
    const itemRe = /(?<![\d.])(\d+)[.、．)）]\s*/g
    let im, prevEnd = 0
    while ((im = itemRe.exec(seg))) {
      if (items.length) items[items.length - 1].text = seg.slice(prevEnd, im.index).trim()
      items.push({ num: parseInt(im[1], 10), text: '' })
      prevEnd = im.index + im[0].length
    }
    if (items.length) items[items.length - 1].text = seg.slice(prevEnd).trim()
    else if (seg) items.push({ num: 0, text: seg })
    return {
      label: b.lab.label,
      type: b.lab.label.includes('坏') ? 'naughty' : 'normal',
      items: items.filter(it => it.text)
    }
  })
  return { body, groups: groups.filter(g => g.items.length) }
}

// ──────────── 发送 ────────────
async function send() {
  const raw = input.value.trim()
  if (!raw || loading.value) return

  await ensureSession()

  // 已选指令随消息提交：消息栏只保留用户输入，指令 payload 作为独立字段交给后端注入 prompt
  const cmds = selectedCmds.value.slice()
  const cmdPayloads = cmds
    .map(n => instructs.find(c => c.name === n)?.payload)
    .filter(Boolean)
  // 整段输入直接作为一条普通用户消息发送（与网页版聊天一致，不做动作/台词拆分，
  // 模型天然能理解"动作+台词"混排的自然语言，无需特殊动作通道）。
  selectedCmds.value = []

  messages.value.push({ role: 'user', content: raw })
  input.value = ''
  autoResize()
  loading.value = true

  try {
    const history = []
    for (let i = 0; i < messages.value.length - 1; i++) {
      const m = messages.value[i]
      if (m.role === 'system') continue
      // 兼容旧数据：历史中遗留的 role=action 消息按普通用户消息回灌，避免割裂
      history.push({ role: m.role === 'action' ? 'user' : m.role, content: m.content })
    }
    const r = await api.chat(raw, history, {
      suggest_normal: suggestNormal.value,
      suggest_naughty: suggestNaughty.value,
      instructions: cmdPayloads,
    })
    messages.value.push({ role: 'assistant', content: r.data.reply })
    persistSession()
  } catch (e) {
    messages.value.push({ role: 'assistant', content: '（请求失败，请检查后端是否运行）' })
  } finally {
    loading.value = false
    nextTick(() => { inputRef.value?.focus() })
  }
}

async function regenerate(i) {
  if (loading.value) return
  const cutoff = i
  messages.value.splice(cutoff)
  const lastUserMsg = messages.value.length > 0 ? messages.value[messages.value.length - 1] : null
  if (!lastUserMsg || lastUserMsg.role !== 'user') return
  loading.value = true
  try {
    const history = []
    for (let j = 0; j < messages.value.length - 1; j++) {
      const m = messages.value[j]
      if (m.role === 'system') continue
      history.push({ role: m.role, content: m.content })
    }
    const lastMsg = messages.value[messages.value.length - 1]
    const r = await api.chat(lastMsg.content, history, {
      suggest_normal: suggestNormal.value,
      suggest_naughty: suggestNaughty.value,
    })
    messages.value.push({ role: 'assistant', content: r.data.reply })
    persistSession()
  } catch (e) {
    messages.value.push({ role: 'assistant', content: '（请求失败，请检查后端是否运行）' })
  } finally {
    loading.value = false
  }
}

// ──────────── 输入框自适应 ────────────
function scrollToBottom() {
  nextTick(() => {
    // 聊天滚动容器类名是 .chat-body（见 template ref="bodyRef"），
    // 修复误用 .msg-list 选择器导致的滚动失效
    if (bodyRef.value) bodyRef.value.scrollTop = bodyRef.value.scrollHeight
  })
}

function autoResize() {
  nextTick(() => {
    const el = inputRef.value
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 180) + 'px'
  })
}
</script>

<style scoped>
.chat-root {
  display: flex; height: calc(100vh - 72px); gap: 0;
}

/* ────────── 左侧会话列表 ────────── */
.chat-sidebar {
  width: 220px; flex-shrink: 0; border-right: 1px solid rgba(255,255,255,0.04);
  display: flex; flex-direction: column; overflow: hidden;
}
.sidebar-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 14px 10px; font-size: 13px; color: #AAA;
  border-bottom: 1px solid rgba(255,255,255,0.03);
}
.sidebar-new-btn {
  background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.08);
  color: #999; width: 26px; height: 26px; border-radius: 6px;
  font-size: 16px; cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: background 0.15s;
}
.sidebar-new-btn:hover { background: rgba(255,255,255,0.12); color: #CCC; }
.sidebar-list { flex: 1; overflow-y: auto; padding: 6px 0; }
.sidebar-empty { color: #444; font-size: 12px; text-align: center; padding: 20px 0; }
.sidebar-item {
  display: flex; align-items: center; padding: 8px 14px; cursor: pointer;
  font-size: 12.5px; color: #999; gap: 6px; transition: background 0.12s;
  position: relative;
}
.sidebar-item:hover { background: rgba(255,255,255,0.03); }
.sidebar-item.active { background: rgba(255,255,255,0.06); color: #CCC; }
.sidebar-title {
  flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.sidebar-time { font-size: 11px; color: #555; flex-shrink: 0; }
.sidebar-del {
  display: none; background: none; border: none; color: #666;
  font-size: 15px; cursor: pointer; padding: 0 2px; line-height: 1;
}
.sidebar-item:hover .sidebar-del { display: block; }
.sidebar-del:hover { color: #C44; }

/* ────────── 右侧聊天区 ────────── */
.chat-main {
  flex: 1; display: flex; flex-direction: column; min-width: 0;
}

.chat-body {
  flex: 1; overflow-y: auto; padding: 18px 20px 10px;
  display: flex; flex-direction: column; gap: 12px;
}
.chat-empty { color: #555; font-size: 13px; padding: 40px 0; text-align: center; }

/* 消息行 */
.msg { }
.msg-row { display: flex; gap: 6px; }
.msg.user .msg-row { justify-content: flex-end; }
.msg.assistant .msg-row { justify-content: flex-start; align-items: flex-end; }
.msg.action .msg-row { justify-content: flex-end; }

/* 气泡 */
.user-bubble-wrap {
  display: flex; max-width: 72%; min-width: 0;
}
.user-bubble-wrap .msg-bubble {
  width: auto; max-width: 100%;
}
.msg-bubble {
  width: fit-content; max-width: 72%; padding: 12px 16px; border-radius: 14px;
  font-size: 14px; line-height: 1.6; white-space: pre-wrap; overflow-wrap: break-word;
}
.user-bubble {
  background: #2A2A2A; color: #CCC; cursor: pointer;
}
.assistant-bubble {
  background: rgba(255,255,255,0.05); color: #CCC;
  border-bottom-left-radius: 4px;
}
.msg-bubble.thinking { color: #666; animation: pulse 1.2s infinite; }
.sys-row { justify-content: center; }
.sys-bubble { background: transparent !important; color: #777; font-size: 12px; padding: 6px 12px !important; text-align: center; }

/* 动作气泡：用户要做的动作/剧情指令，区别于普通消息 */
.action-row { align-items: flex-end; }
.action-bubble {
  display: flex; align-items: flex-start; gap: 6px;
  background: rgba(196, 139, 168, 0.10);
  border: 1px dashed rgba(196, 139, 168, 0.45);
  color: #D9B8C8;
}
.action-tag {
  flex-shrink: 0; margin-top: 2px;
  font-size: 11px; font-weight: 600; letter-spacing: 1px;
  color: #C98BA8;
  border: 1px solid rgba(196, 139, 168, 0.5);
  border-radius: 6px; padding: 0 5px; line-height: 16px;
}

/* 建议栏（统一展示格式） */
.assistant-content { max-width: 72%; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
.assistant-content .msg-bubble { max-width: 100%; }
.suggest-panel {
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px;
  padding: 12px 14px;
  display: flex; flex-direction: column; gap: 10px;
}
.suggest-group { display: flex; flex-direction: column; gap: 6px; }
.suggest-label {
  font-size: 12px; font-weight: 600; letter-spacing: 1px;
  color: #8A8A8A;
}
.suggest-label.normal { color: #7FB8A0; }
.suggest-label.naughty { color: #C98BA8; }
.suggest-item {
  display: flex; gap: 8px; align-items: flex-start;
  font-size: 13px; line-height: 1.55; color: #B8B8B8;
}
.suggest-num {
  flex-shrink: 0; width: 20px; height: 20px;
  border-radius: 50%; background: rgba(255,255,255,0.08);
  color: #999; font-size: 11.5px; font-weight: 600;
  font-variant-numeric: tabular-nums; line-height: 20px;
  display: flex; align-items: center; justify-content: center;
  margin-top: 1px;
}
.suggest-text { overflow-wrap: break-word; white-space: pre-wrap; }

/* 编辑 */
.msg-edit-wrap { max-width: 72%; min-width: 160px; }
.msg-edit-input {
  width: 100%; min-width: 120px; background: #1E1E1E; border: 1px solid rgba(255,255,255,0.15);
  border-radius: 10px; padding: 10px 14px; color: #D0D0D0; font-size: 13.5px;
  font-family: inherit; outline: none; line-height: 1.5;
}
.msg-edit-actions { display: flex; gap: 6px; justify-content: flex-end; margin-top: 6px; }
.edit-btn {
  background: rgba(255,255,255,0.08); color: #CCC; border: none;
  border-radius: 6px; padding: 4px 14px; font-size: 12px; cursor: pointer;
}
.edit-btn.cancel { background: transparent; color: #777; }
.edit-btn:hover { background: rgba(255,255,255,0.14); }

/* 刷新按钮 */
.refresh-btn {
  background: none; border: none; color: #555; cursor: pointer;
  padding: 4px; border-radius: 4px; display: flex; align-items: center;
  opacity: 0; transition: opacity 0.15s, color 0.15s; flex-shrink: 0;
}
.assistant-row:hover .refresh-btn { opacity: 1; }
.refresh-btn:hover { color: #999; background: rgba(255,255,255,0.04); }
.refresh-btn:disabled { opacity: 0.15; cursor: default; }

/* ────────── 输入栏 Kimi 风格 ────────── */
.chat-input-area {
  padding: 10px 24px 20px;
  border-top: 1px solid rgba(255,255,255,0.03);
  display: flex; flex-direction: column; align-items: center;
  gap: 8px;
}
.suggest-toggles {
  display: flex; gap: 18px; align-items: center;
  width: 100%; max-width: 720px;
}
.toggle-item {
  display: inline-flex; align-items: center; gap: 6px;
  cursor: pointer; user-select: none;
  font-size: 12px; color: #777;
  transition: color 0.15s;
}
.toggle-item input { display: none; }
.toggle-box {
  width: 14px; height: 14px; border-radius: 4px;
  border: 1px solid rgba(255,255,255,0.18);
  background: rgba(255,255,255,0.03);
  display: inline-flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.toggle-item.on { color: #CCC; }
.toggle-item.on .toggle-box {
  background: rgba(255,255,255,0.9); border-color: rgba(255,255,255,0.9);
}
.toggle-item.on .toggle-box::after {
  content: ''; width: 6px; height: 6px; border-radius: 2px;
  background: #1A1A1A;
}
.instruct-btn {
  margin-left: auto;
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 12.5px; color: oklch(0.95 0.0165 285); cursor: pointer;
  background: oklch(1 0 0 / 0.045);
  border: 0.8px solid oklch(1 0 0 / 0.09);
  border-radius: 15px; padding: 4px 12px;
  transition: all 0.15s;
}
.instruct-btn:hover { background: oklch(0.8 0.144 330 / 0.14); color: oklch(0.8 0.144 330); }
.instruct-btn.on {
  background: oklch(0.8 0.144 330 / 0.14); color: oklch(0.8 0.144 330);
  border-color: oklch(0.8 0.144 330 / 0.36);
}
.nick-btn { margin-left: 6px; }
.nick-panel {
  width: 100%; max-width: 720px;
  background: oklch(0.235 0.0413 285);
  border-radius: 10px; padding: 10px 12px;
  display: flex; flex-direction: column; gap: 8px;
}
.nick-head { display: flex; align-items: baseline; gap: 10px; }
.nick-title { font-size: 14px; color: oklch(0.95 0.0165 285); font-weight: 600; }
.nick-hint { font-size: 12px; color: oklch(0.78 0.022 285); }
.nick-body { display: flex; gap: 8px; align-items: center; }
.nick-input {
  flex: 1; background: oklab(0.27 0.009 -0.034 / 0.5);
  border: 0.8px solid oklch(1 0 0 / 0.12); border-radius: 8px;
  padding: 7px 12px; color: oklch(0.95 0.0165 285);
  font-size: 13.5px; font-family: inherit; outline: none;
}
.nick-input:focus { border-color: oklch(0.8 0.144 330 / 0.5); }
.nick-save {
  flex-shrink: 0; font-size: 12.5px; cursor: pointer;
  color: oklch(0.95 0.0165 285);
  background: oklch(0.8 0.144 330 / 0.22);
  border: 0.8px solid oklch(0.8 0.144 330 / 0.4);
  border-radius: 8px; padding: 7px 16px;
  transition: all 0.15s;
}
.nick-save:hover { background: oklch(0.8 0.144 330 / 0.34); }
.nick-msg { font-size: 12px; color: oklch(0.8 0.144 330); }
.nick-msg.ok { color: oklch(0.8 0.66 150); }
.instruct-panel {
  width: 100%; max-width: 720px;
  background: oklch(0.235 0.0413 285);
  border-radius: 10px; padding: 10px 12px;
  display: flex; flex-direction: column; gap: 8px;
}
.instruct-head {
  display: flex; align-items: center; gap: 10px;
}
.instruct-title { font-size: 14px; color: oklch(0.95 0.0165 285); font-weight: 600; }
.instruct-cur { font-size: 12px; color: oklch(0.78 0.022 285); }
.instruct-clear {
  margin-left: auto; font-size: 12px; cursor: pointer;
  color: oklch(0.8 0.144 330); background: transparent; border: none;
}
.instruct-clear:hover { text-decoration: underline; }
.instruct-tabs {
  display: flex; gap: 6px; flex-wrap: wrap;
}
.instruct-tab {
  font-size: 12.5px; color: oklch(0.78 0.022 285); cursor: pointer;
  background: oklab(0.27 0.009 -0.034 / 0.5);
  border: 0.8px solid oklch(1 0 0 / 0.09);
  border-radius: 10px; padding: 4px 8px;
  display: inline-flex; align-items: center; gap: 4px;
  transition: all 0.15s;
}
.instruct-count { font-size: 10.5px; opacity: 0.7; }
.instruct-tab:hover { color: oklch(0.95 0.0165 285); }
.instruct-tab.active {
  background: oklch(0.8 0.144 330 / 0.14); color: oklch(0.8 0.144 330);
  border-color: oklch(0.8 0.144 330 / 0.36);
}
.instruct-list {
  display: flex; flex-direction: column; gap: 4px;
  max-height: 240px; overflow-y: auto;
}
.instruct-item {
  text-align: left; cursor: pointer;
  background: oklab(0.27 0.009 -0.034 / 0.3);
  border: 0.8px solid oklch(1 0 0 / 0.09);
  border-radius: 8px; padding: 6px 10px;
  display: flex; flex-direction: column; gap: 2px;
  transition: all 0.15s;
}
.instruct-item:hover { background: oklch(0.8 0.144 330 / 0.10); }
.instruct-item.selected {
  background: oklch(0.8 0.144 330 / 0.14);
  border-color: oklch(0.8 0.144 330 / 0.36);
}
.instruct-name { font-size: 13px; color: oklch(0.95 0.0165 285); font-weight: 600; }
.instruct-item.selected .instruct-name { color: oklch(0.8 0.144 330); }
.instruct-desc { font-size: 11px; color: oklch(0.78 0.022 285); line-height: 1.4; }

/* 已选指令胶囊 */
.cmd-chips {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  width: 100%; max-width: 720px;
}
.cmd-chip {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 12px; color: oklch(0.8 0.144 330);
  background: oklch(0.8 0.144 330 / 0.14);
  border: 0.8px solid oklch(0.8 0.144 330 / 0.36);
  border-radius: 9999px; padding: 4px 10px;
}
.chip-x {
  border: none; background: transparent; cursor: pointer;
  color: oklch(0.8 0.144 330); font-size: 13px; line-height: 1; padding: 0 2px;
}
.chip-x:hover { color: #fff; }
.chip-clear {
  font-size: 12px; cursor: pointer;
  color: oklch(0.78 0.022 285); background: transparent;
  border: 0.8px solid oklch(1 0 0 / 0.12); border-radius: 9999px;
  padding: 4px 10px;
}
.chip-clear:hover { color: oklch(0.8 0.144 330); border-color: oklch(0.8 0.144 330 / 0.36); }
.chat-input-bar {
  display: flex; align-items: flex-end; width: 100%; max-width: 720px;
  background: rgba(255,255,255,0.025);
  border: 0.8px solid rgba(255,255,255,0.10);
  border-radius: 24px; padding: 6px 6px 6px 12px;
  transition: border-color 0.2s, background 0.2s;
}
.chat-input-bar:focus-within {
  border-color: rgba(255,255,255,0.20);
  background: rgba(255,255,255,0.035);
}

.upload-btn {
  flex-shrink: 0; width: 36px; height: 36px; display: flex; align-items: center; justify-content: center;
  border-radius: 8px; cursor: pointer; color: #6A6A6A;
  transition: background 0.15s, color 0.15s; margin-bottom: 0;
}
.upload-btn:hover { background: rgba(255,255,255,0.06); color: #999; }

.chat-input {
  flex: 1; resize: none; background: transparent; border: none;
  color: #D0D0D0; font-size: 14px; font-family: inherit; outline: none;
  line-height: 1.55; min-height: 36px; max-height: 180px;
  padding: 6px 4px; overflow-y: auto;
}
.chat-input::placeholder { color: #555; }

.send-btn {
  flex-shrink: 0; width: 36px; height: 36px; border-radius: 22px;
  border: none; cursor: pointer; display: flex;
  align-items: center; justify-content: center;
  transition: all 0.18s; margin-bottom: 0;
  background: rgba(255,255,255,0.10); color: #777;
}
.send-btn:hover:not(:disabled) { background: rgba(255,255,255,0.15); color: #AAA; }
.send-btn.active { background: rgba(255,255,255,0.20); color: #DDD; }
.send-btn.active:hover { background: rgba(255,255,255,0.25); }
.send-btn:disabled { cursor: default; }

@keyframes pulse { 0%,100%{opacity:0.35} 50%{opacity:1} }

/* ────────── 移动端适配（<768px）────────── */
.chat-mobile-bar { display: none; }
.chat-sidebar-mask { display: none; }

@media (max-width: 768px) {
  .chat-root {
    flex-direction: column;
    height: calc(100vh - 76px); /* 底部导航 56px + main 上下 padding 20px */
  }

  /* 移动端顶栏 */
  .chat-mobile-bar {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 14px; flex-shrink: 0;
    border-bottom: 1px solid rgba(255,255,255,0.04);
  }
  .chat-mobile-menu {
    background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.08);
    color: #AAA; width: 34px; height: 34px; border-radius: 8px;
    display: flex; align-items: center; justify-content: center; cursor: pointer;
  }
  .chat-mobile-menu:active { background: rgba(255,255,255,0.12); }
  .chat-mobile-title { font-size: 14px; font-weight: 600; color: #CCC; }

  /* 会话列表 → 左侧抽屉 */
  .chat-sidebar {
    position: fixed; top: 0; left: 0; bottom: 0; z-index: 300;
    width: 78vw; max-width: 300px; background: #0D0D0D;
    border-right: 1px solid rgba(255,255,255,0.06);
    transform: translateX(-100%); transition: transform 0.25s ease;
    box-shadow: 8px 0 32px rgba(0,0,0,0.5);
  }
  .chat-sidebar.open { transform: translateX(0); }
  .chat-sidebar-mask {
    display: block; position: fixed; inset: 0; z-index: 290;
    background: rgba(0,0,0,0.55);
  }
  .sidebar-item { padding: 12px 14px; }
  .sidebar-del { display: block; }

  /* 聊天区 */
  .chat-body { padding: 12px 12px 8px; gap: 10px; }
  .user-bubble-wrap { max-width: 88%; }
  .msg-bubble { max-width: 88%; font-size: 14.5px; }
  .assistant-content { max-width: 92%; }
  .msg-edit-wrap { max-width: 88%; }
  .refresh-btn { opacity: 1; }

  /* 输入栏 */
  .chat-input-area { padding: 8px 10px 12px; }
  .suggest-toggles { gap: 12px; }
  .toggle-item { font-size: 11.5px; }
  .instruct-btn { padding: 4px 10px; font-size: 12px; }
  .nick-panel, .instruct-panel, .cmd-chips, .chat-input-bar { max-width: 100%; }
  .chat-input-bar { border-radius: 20px; }
  .chat-input { font-size: 15px; }
}
</style>
