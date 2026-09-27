<template>
  <div class="char-page">
    <header class="page-hd">
      <div>
        <h1>角色管理</h1>
        <p class="hd-sub">管理 AI 角色的性格指南与对话人设</p>
      </div>
      <button class="btn btn-primary" @click="showCreate = true">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M12 5v14M5 12h14"/></svg>
        新建角色
      </button>
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
          <textarea v-model="newGuide" rows="11" placeholder="描述性格、背景、说话风格、情感模式与特殊设定…&#10;&#10;例：你是林子欣，一个外冷内热的高中生。说话简短、偶尔毒舌…"></textarea>
        </div>
        <div class="modal-ft">
          <button class="btn" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" @click="create" :disabled="!newName.trim()">创建角色</button>
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

async function load() { const r = await api.listPersonas(); personas.value = r.data }
function select(p) { detail.value = p; editText.value = p.guide; editing.value = false }
function closeDetailIfBg() {
  // 仅当 mousedown 也发生在遮罩背景上才关闭，
  // 防止在 textarea 内拖选文本时鼠标越界触发 click.self 误关弹窗（表现为“返回角色管理页”）
  if (bgPress.value) { detail.value = null; bgPress.value = false }
}
async function activate() {
  await api.activatePersona(detail.value.name); await load()
  detail.value = personas.value.find(x => x.name === detail.value.name)
}
async function toggleEdit() {
  if (editing.value) {
    await api.updatePersona(detail.value.name, editText.value)
    detail.value.guide = editText.value
    editing.value = false
    await load()
  } else {
    editText.value = detail.value.guide
    editing.value = true
  }
}
async function remove() {
  if (!confirm(`确定删除「${detail.value.name}」？`)) return
  await api.deletePersona(detail.value.name); detail.value = null; await load()
}
async function create() {
  await api.createPersona(newName.value.trim(), newGuide.value)
  showCreate.value = false; newName.value = ''; newGuide.value = ''; await load()
}
onMounted(load)
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
  .modal-ft .btn { flex: 1; justify-content: center; }
}
</style>
