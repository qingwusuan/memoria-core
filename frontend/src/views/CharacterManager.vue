<template>
  <div class="char-page">
    <header class="page-hd">
      <div>
        <h1>角色管理</h1>
        <p class="hd-sub">管理 AI 角色的性格指南与对话人设</p>
      </div>
      <div class="hd-actions">
        <button class="btn" @click="openTrash">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v5M14 11v5"/></svg>
          回收站<span class="trash-count" v-if="trash.length">{{ trash.length }}</span>
        </button>
        <button class="btn btn-primary" @click="showCreate = true">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M12 5v14M5 12h14"/></svg>
          新建角色
        </button>
      </div>
    </header>

    <div class="persona-grid" v-if="personas.length">
      <div
        v-for="p in personas" :key="p.name"
        :class="['persona-card', { active: p.is_active }]"
        @click="select(p)"
      >
        <div class="pc-avatar" :class="{ active: p.is_active }">{{ p.name[0] }}</div>
        <div class="pc-body">
          <div class="pc-name">
            {{ p.name }}
            <span class="pc-badge" v-if="p.is_active">当前</span>
          </div>
          <div class="pc-preview">{{ p.guide.slice(0, 90) }}{{ p.guide.length > 90 ? '…' : '' }}</div>
        </div>
        <div class="pc-arrow">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m9 18 6-6-6-6"/></svg>
        </div>
      </div>
    </div>

    <div class="empty-state" v-else>
      <div class="es-icon">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
          <circle cx="12" cy="8" r="4.5"/><path d="M5.5 21v-2a4.5 4.5 0 0 1 4.5-4.5h4a4.5 4.5 0 0 1 4.5 4.5v2"/>
        </svg>
      </div>
      <p class="es-title">尚未创建角色</p>
      <p class="es-desc">角色指南定义了 AI 的性格基调、说话方式与行为边界，是 Memoria 的灵魂。</p>
      <button class="btn btn-primary es-btn" @click="showCreate = true">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M12 5v14M5 12h14"/></svg>
        创建第一个角色
      </button>
    </div>

    <div class="detail-overlay" v-if="detail" @mousedown.self="bgPress = true" @click.self="closeDetailIfBg()">
      <div class="detail-sheet">
        <div class="ds-hd">
          <div class="ds-avatar">{{ detail.name[0] }}</div>
          <div>
            <h2>{{ detail.name }}</h2>
            <span class="ds-status" v-if="detail.is_active">当前活跃角色</span>
          </div>
          <button class="btn-close" @click="detail = null">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
          </button>
        </div>
        <div class="ds-guide" v-if="!editing">
          <pre>{{ detail.guide }}</pre>
        </div>
        <div class="ds-edit" v-else>
          <textarea v-model="editText" rows="14"></textarea>
        </div>
        <div class="ds-view">
          <label>叙事视角</label>
          <select :value="detail.narrative_person || ''" @change="setPersonaView($event.target.value)">
            <option value="">跟随默认</option>
            <option value="third">第三人称</option>
            <option value="first">第一人称</option>
          </select>
          <span class="ds-view-hint">只影响这个角色，保存后立即生效。</span>
        </div>
        <div class="ds-actions">
          <button class="btn" v-if="!detail.isActive && !detail.is_active" @click="activate">启用此角色</button>
          <button class="btn" @click="toggleEdit">{{ editing ? '保存' : '编辑' }}</button>
          <button class="btn btn-danger" @click="remove">删除</button>
        </div>
      </div>
    </div>

    <div class="modal-overlay" v-if="showCreate" @mousedown.self="bgPress = true" @click.self="bgPress && (showCreate = false, bgPress = false)">
      <div class="modal">
        <h3>新建角色</h3>
        <div class="field">
          <label>角色名称</label>
          <input v-model="newName" placeholder="给角色起个名字" />
        </div>
        <div class="field">
          <label>角色指南</label>
          <textarea v-model="newGuide" rows="11" placeholder="描述性格、背景、说话风格、情感模式与特殊设定…&#10;&#10;例：你是小夏，一个外冷内热的高中生。说话简短、偶尔毒舌…"></textarea>
        </div>
        <div class="modal-ft">
          <button class="btn" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" @click="create" :disabled="!newName.trim()">创建角色</button>
        </div>
      </div>
    </div>

    <div class="modal-overlay" v-if="showTrash" @mousedown.self="bgPress = true" @click.self="bgPress && (showTrash = false, bgPress = false)">
      <div class="modal trash-modal">
        <div class="tm-hd">
          <h3>回收站</h3>
          <button class="btn-close" @click="showTrash = false">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
          </button>
        </div>
        <p class="tm-hint">删除角色时的完整备份，保留 7 天。恢复会一起还原角色定义、性格状态、聊天记录、滚动摘要、场景锚点与记忆库。</p>

        <div class="tm-empty" v-if="!trash.length">回收站是空的。</div>

        <div class="tm-list" v-else>
          <div class="tm-item" v-for="t in trash" :key="t.id">
            <div class="tm-avatar">{{ t.persona[0] || '?' }}</div>
            <div class="tm-body">
              <div class="tm-name">{{ t.persona }}</div>
              <div class="tm-meta">{{ formatTime(t.created_at) }} · {{ formatSize(t.size_bytes) }}</div>
              <div class="tm-parts">
                <span class="tm-chip" v-for="part in t.parts" :key="part">{{ partLabel(part) }}</span>
              </div>
            </div>
            <div class="tm-actions">
              <button class="btn" :disabled="trashBusy === t.id" @click="restore(t)">
                {{ trashBusy === t.id ? '恢复中…' : '恢复' }}
              </button>
              <button class="btn btn-danger" :disabled="trashBusy === t.id" @click="purge(t)">彻底删除</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api.js'

const personas = ref([])
const detail = ref(null)
const editing = ref(false)
const editText = ref('')
const showCreate = ref(false)
const newName = ref('')
const newGuide = ref('')
const bgPress = ref(false)
const showTrash = ref(false)
const trash = ref([])
const trashBusy = ref('')

const PART_LABELS = {
  'persona.json': '角色定义',
  personality: '性格',
  chat_logs: '聊天',
  summaries: '摘要',
  memories: '记忆',
  last_scene: '场景',
}

async function load() {
  try {
    const r = await api.listPersonas()
    personas.value = r.data
  } catch (e) {
    personas.value = []
    alert('加载角色列表失败：' + (e.response?.data?.detail || e.message))
  }
}
function select(p) { detail.value = p; editText.value = p.guide; editing.value = false }
function closeDetailIfBg() {
  // 仅当 mousedown 也发生在遮罩背景上才关闭，
  // 防止在 textarea 内拖选文本时鼠标越界触发 click.self 误关弹窗（表现为“返回角色管理页”）
  if (bgPress.value) { detail.value = null; bgPress.value = false }
}
async function activate() {
  try {
    await api.activatePersona(detail.value.name)
    await load()
    detail.value = personas.value.find(x => x.name === detail.value.name)
  } catch (e) {
    alert('启用角色失败：' + (e.response?.data?.detail || e.message))
  }
}
async function toggleEdit() {
  if (editing.value) {
    try {
      await api.updatePersona(detail.value.name, editText.value)
      detail.value.guide = editText.value
      editing.value = false
      await load()
    } catch (e) {
      alert('保存角色失败：' + (e.response?.data?.detail || e.message))
    }
  } else {
    editText.value = detail.value.guide
    editing.value = true
  }
}
async function setPersonaView(value) {
  const name = detail.value.name
  try {
    await api.updatePersona(name, detail.value.guide, value)
    await load()
    detail.value = personas.value.find(p => p.name === name) || null
  } catch (e) {
    alert('保存叙事视角失败：' + (e.response?.data?.detail || e.message))
  }
}
async function remove() {
  if (!confirm(`确定删除「${detail.value.name}」？`)) return
  try {
    await api.deletePersona(detail.value.name)
    detail.value = null
    await load()
    await loadTrash(true)
  } catch (e) {
    alert('删除角色失败：' + (e.response?.data?.detail || e.message))
  }
}

/* ──────────── 回收站 ──────────── */
function partLabel(part) { return PART_LABELS[part] || part }
function formatTime(ts) {
  if (!ts) return '时间未知'
  const d = new Date(ts * 1000)
  const p = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
function formatSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}
async function loadTrash(silent = false) {
  try {
    const r = await api.listTrash()
    trash.value = r.data.items || []
  } catch (e) {
    trash.value = []
    if (!silent) alert('加载回收站失败：' + (e.response?.data?.detail || e.message))
  }
}
function openTrash() {
  showTrash.value = true
  loadTrash()
}
async function restore(t) {
  if (!confirm(`恢复「${t.persona}」？将还原角色定义、性格、聊天、摘要、场景与记忆。`)) return
  trashBusy.value = t.id
  try {
    await api.restoreTrash(t.id)
    await load()
    await loadTrash(true)
    alert(`已恢复「${t.persona}」`)
  } catch (e) {
    const status = e.response?.status
    const detail = e.response?.data?.detail || e.message
    if (status === 409 && confirm(`${detail}\n\n要用这份备份覆盖现有角色吗？`)) {
      try {
        await api.restoreTrash(t.id, true)
        await load()
        await loadTrash(true)
        alert(`已覆盖恢复「${t.persona}」`)
      } catch (e2) {
        alert('恢复失败：' + (e2.response?.data?.detail || e2.message))
      }
    } else if (status !== 409) {
      alert('恢复失败：' + detail)
    }
  } finally {
    trashBusy.value = ''
  }
}
async function purge(t) {
  if (!confirm(`彻底删除「${t.persona}」的备份？此操作不可恢复。`)) return
  if (!confirm(`再次确认：备份删除后，角色、聊天与摘要在磁盘上不再保留任何副本。`)) return
  trashBusy.value = t.id
  try {
    await api.purgeTrash(t.id)
    await loadTrash(true)
  } catch (e) {
    alert('删除备份失败：' + (e.response?.data?.detail || e.message))
  } finally {
    trashBusy.value = ''
  }
}
async function create() {
  try {
    await api.createPersona(newName.value.trim(), newGuide.value)
    showCreate.value = false
    newName.value = ''
    newGuide.value = ''
    await load()
  } catch (e) {
    alert('创建角色失败：' + (e.response?.data?.detail || e.message))
  }
}
onMounted(() => { load(); loadTrash(true) })
</script>

<style scoped>
.char-page { max-width: 960px; margin: 0 auto; }
.page-hd { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 32px; }
.page-hd h1 { font-size: 22px; font-weight: 600; color: #E0E0E0; letter-spacing: -0.02em; }
.hd-sub { font-size: 12.5px; color: #666; margin-top: 4px; }

/* grid */
.persona-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(288px, 1fr)); gap: 12px; }
.persona-card {
  display: flex; align-items: center; gap: 13px; padding: 16px 18px;
  background: #111; border: 1px solid rgba(255,255,255,0.04);
  border-radius: 10px; cursor: pointer; transition: all 0.2s ease;
  box-shadow: 0 1px 2px rgba(0,0,0,0.3);
}
.persona-card:hover {
  background: #151515; border-color: rgba(255,255,255,0.07);
  box-shadow: 0 4px 16px rgba(0,0,0,0.4);
  transform: translateY(-1px);
}
.persona-card.active {
  border-color: rgba(91,141,239,0.35);
  background: rgba(91,141,239,0.04);
}
.pc-avatar {
  width: 42px; height: 42px; border-radius: 10px; flex-shrink: 0;
  background: linear-gradient(135deg, #3A3A3A, #2A2A2A);
  display: flex; align-items: center; justify-content: center;
  font-size: 17px; font-weight: 700; color: #888;
}
.pc-avatar.active {
  background: linear-gradient(135deg, #5B8DEF, #8B6FE8);
  color: #fff; box-shadow: 0 2px 10px rgba(91,141,239,0.3);
}
.pc-body { flex: 1; min-width: 0; }
.pc-name { font-size: 14.5px; font-weight: 600; margin-bottom: 3px; display: flex; align-items: center; gap: 8px; color: #D0D0D0; }
.pc-badge {
  font-size: 10px; padding: 1.5px 7px; border-radius: 9px;
  background: rgba(91,141,239,0.15); color: #5B8DEF; font-weight: 550;
}
.pc-preview { font-size: 12px; color: #686868; line-height: 1.45; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pc-arrow { color: #3A3A3A; transition: color 0.2s, transform 0.2s; }
.persona-card:hover .pc-arrow { color: #666; transform: translateX(2px); }

/* empty */
.empty-state {
  text-align: center; padding: 80px 20px 60px;
  max-width: 420px; margin: 0 auto;
}
.es-icon {
  width: 64px; height: 64px; border-radius: 16px;
  background: linear-gradient(135deg, rgba(91,141,239,0.08), rgba(139,111,232,0.08));
  display: inline-flex; align-items: center; justify-content: center;
  color: #5B8DEF; margin-bottom: 24px;
  box-shadow: 0 4px 20px rgba(91,141,239,0.06);
}
.es-title { font-size: 17px; font-weight: 600; color: #B0B0B0; margin-bottom: 8px; }
.es-desc { font-size: 13.5px; color: #555; line-height: 1.7; margin-bottom: 28px; }
.es-btn { font-size: 13.5px; padding: 10px 24px; }

/* detail */
.detail-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); backdrop-filter: blur(4px); z-index: 100; display: flex; align-items: center; justify-content: center; }
.detail-sheet {
  background: #111; border: 1px solid rgba(255,255,255,0.06); border-radius: 14px;
  width: 580px; max-height: 80vh; display: flex; flex-direction: column; overflow: hidden;
  box-shadow: 0 16px 48px rgba(0,0,0,0.5);
}
.ds-hd { display: flex; align-items: center; gap: 14px; padding: 22px 24px; border-bottom: 1px solid rgba(255,255,255,0.04); }
.ds-avatar {
  width: 44px; height: 44px; border-radius: 11px; flex-shrink: 0;
  background: linear-gradient(135deg, #5B8DEF, #8B6FE8);
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; font-weight: 700; color: #fff;
}
.ds-hd h2 { font-size: 16px; font-weight: 600; color: #E0E0E0; }
.ds-status { font-size: 12px; color: #5B8DEF; }
.btn-close {
  margin-left: auto; background: none; border: none; color: #555; cursor: pointer;
  padding: 6px; border-radius: 8px; transition: all 0.15s;
}
.btn-close:hover { color: #CCC; background: rgba(255,255,255,0.04); }
.ds-guide { padding: 22px 24px; overflow-y: auto; flex: 1; }
.ds-guide pre { white-space: pre-wrap; font-family: inherit; font-size: 13.5px; line-height: 1.85; color: #999; }
.ds-edit { padding: 22px 24px; flex: 1; }
.ds-edit textarea {
  width: 100%; height: 100%; min-height: 220px; background: #0B0B0B;
  border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; color: #CCC;
  padding: 14px; font-family: inherit; font-size: 13.5px; line-height: 1.85;
  resize: none; outline: none;
}
.ds-edit textarea:focus { border-color: rgba(91,141,239,0.4); }
.ds-actions { display: flex; gap: 8px; padding: 14px 24px; border-top: 1px solid rgba(255,255,255,0.04); }

/* modal */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.65); backdrop-filter: blur(4px); z-index: 200; display: flex; align-items: center; justify-content: center; }
.modal {
  background: #111; border: 1px solid rgba(255,255,255,0.06); border-radius: 14px;
  padding: 26px; width: 500px; display: flex; flex-direction: column; gap: 18px;
  box-shadow: 0 20px 56px rgba(0,0,0,0.5);
}
.modal h3 { font-size: 17px; font-weight: 600; color: #E0E0E0; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field label { font-size: 12px; color: #757575; font-weight: 500; }
.modal input, .modal textarea {
  background: #0B0B0B; border: 1px solid rgba(255,255,255,0.06); border-radius: 8px;
  color: #CCC; padding: 11px 13px; font-family: inherit; font-size: 13.5px;
  outline: none; resize: none; line-height: 1.6;
}
.modal input:focus, .modal textarea:focus { border-color: rgba(91,141,239,0.4); }
.modal-ft { display: flex; gap: 8px; justify-content: flex-end; padding-top: 4px; }

/* buttons */
.btn {
  display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px;
  border: 1px solid rgba(255,255,255,0.06); background: #181818; color: #999;
  border-radius: 7px; cursor: pointer; font-size: 13px; font-weight: 500;
  transition: all 0.18s ease;
}
.btn:hover { background: #222; border-color: rgba(255,255,255,0.1); color: #CCC; }
.btn-primary {
  background: linear-gradient(135deg, #5B8DEF, #6B7FEF);
  border: none; color: #fff; font-weight: 550;
  box-shadow: 0 2px 8px rgba(91,141,239,0.2);
}
.btn-primary:hover { background: linear-gradient(135deg, #6B9DF8, #7B8FF8); box-shadow: 0 4px 14px rgba(91,141,239,0.3); }
.btn-primary:active { transform: scale(0.98); }
.btn-danger:hover { background: rgba(224,80,80,0.12); border-color: rgba(224,80,80,0.3); color: #D06060; }
.btn:disabled { opacity: 0.3; cursor: not-allowed; }

/* 角色级叙事视角 */
.ds-view {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 12px 24px; border-top: 1px solid rgba(255,255,255,0.04);
  font-size: 12.5px; color: #757575;
}
.ds-view select {
  background: #0B0B0B; color: #BBB; border: 1px solid rgba(255,255,255,0.08);
  border-radius: 6px; padding: 4px 8px; font-size: 12.5px; font-family: inherit;
  outline: none;
}
.ds-view-hint { color: #4E4E4E; font-size: 11.5px; }

/* ────────── 回收站 ────────── */.hd-actions { display: flex; align-items: center; gap: 8px; }
.trash-count {
  min-width: 17px; height: 17px; padding: 0 5px; margin-left: 2px;
  border-radius: 9px; background: rgba(91,141,239,0.18); color: #7FA6F5;
  font-size: 10.5px; font-weight: 600; display: inline-flex;
  align-items: center; justify-content: center;
}
.trash-modal { width: 640px; max-height: 78vh; overflow: hidden; }
.tm-hd { display: flex; align-items: center; justify-content: space-between; }
.tm-hd h3 { font-size: 17px; font-weight: 600; color: #E0E0E0; }
.tm-hd .btn-close { margin-left: 0; }
.tm-hint { font-size: 12px; color: #666; line-height: 1.65; margin-top: -6px; }
.tm-empty { padding: 26px 0; text-align: center; font-size: 13px; color: #555; }
.tm-list { overflow-y: auto; max-height: 52vh; display: flex; flex-direction: column; gap: 8px; }
.tm-item {
  display: flex; align-items: center; gap: 12px; padding: 12px 14px;
  background: #0D0D0D; border: 1px solid rgba(255,255,255,0.05); border-radius: 9px;
}
.tm-avatar {
  width: 36px; height: 36px; border-radius: 9px; flex-shrink: 0;
  background: linear-gradient(135deg, #3A3A3A, #2A2A2A);
  display: flex; align-items: center; justify-content: center;
  font-size: 15px; font-weight: 700; color: #888;
}
.tm-body { flex: 1; min-width: 0; }
.tm-name { font-size: 13.5px; font-weight: 600; color: #D0D0D0; }
.tm-meta { font-size: 11.5px; color: #666; margin-top: 2px; }
.tm-parts { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.tm-chip {
  font-size: 10.5px; padding: 1px 6px; border-radius: 5px;
  background: rgba(255,255,255,0.05); color: #777;
}
.tm-actions { display: flex; gap: 6px; flex-shrink: 0; }
.tm-actions .btn { padding: 6px 12px; font-size: 12.5px; }

/* ────────── 移动端适配（<768px）────────── */
@media (max-width: 768px) {
  .page-hd { flex-direction: column; gap: 12px; margin-bottom: 20px; }
  .page-hd .btn { align-self: flex-start; }
  .persona-grid { grid-template-columns: 1fr; }
  .persona-card { padding: 14px 16px; }

  /* 详情弹窗 → 底部全屏抽屉 */
  .detail-overlay { align-items: flex-end; }
  .detail-sheet {
    width: 100%; max-height: 92vh; border-radius: 16px 16px 0 0;
  }
  .ds-hd { padding: 18px 18px; }
  .ds-guide, .ds-edit { padding: 18px; }
  .ds-actions { padding: 12px 18px; }
  .ds-actions .btn { flex: 1; justify-content: center; }

  /* 新建角色弹窗 → 全屏 */
  .modal-overlay { align-items: flex-end; }
  .modal {
    width: 100%; max-height: 92vh; border-radius: 16px 16px 0 0;
    padding: 20px 18px; overflow-y: auto;
  }
  .trash-modal { width: 100%; max-height: 92vh; border-radius: 16px 16px 0 0; }
  .tm-list { max-height: 58vh; }
  .tm-item { align-items: flex-start; flex-wrap: wrap; }
  .tm-actions { width: 100%; justify-content: flex-end; }
  .modal-ft .btn { flex: 1; justify-content: center; }
}
</style>
