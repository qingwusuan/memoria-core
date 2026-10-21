<template>
  <div class="settings-overlay" v-if="modelValue" @click.self="close">
    <div class="settings-modal">
      <header class="st-hd">
        <h3>设置</h3>
        <button class="st-close" @click="close">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
        </button>
      </header>

      <p class="st-desc">
        API Key 只保存在本机 <code>data/credentials.json</code>，不会写进 <code>.env</code>，
        也不会回传给前端。除内置两家外，也可以登记任意 OpenAI 兼容接口。
      </p>

      <section class="st-sec" v-for="p in providers" :key="p.id">
        <div class="key-row">
          <div class="key-info">
            <b>{{ p.label }}</b>
            <span class="key-badge" v-if="!p.builtin">自定义</span>
            <span class="key-status" :class="{ ok: p.has_key }">
              {{ p.has_key ? '已配置 ' + p.masked : '未配置' }}
            </span>
          </div>
          <div class="key-actions">
            <input
              v-model="drafts[p.id]"
              type="password"
              :placeholder="p.has_key ? '替换为新 Key' : '粘贴 API Key'"
              autocomplete="off"
              spellcheck="false"
            />
            <button class="st-btn primary" :disabled="saving[p.id] || !(drafts[p.id] || '').trim()" @click="saveKey(p)">
              {{ saving[p.id] ? '保存中…' : '保存' }}
            </button>
            <button class="st-btn" :disabled="saving[p.id] || !p.has_key" @click="clearKey(p)">清除</button>
            <button class="st-btn danger" v-if="!p.builtin" :disabled="saving[p.id]" @click="removeProvider(p)">删除</button>
          </div>
        </div>
        <span class="key-model">{{ p.model }}</span>
      </section>

      <section class="st-sec">
        <div class="add-hd">
          <h4>添加供应商</h4>
          <button class="st-btn" @click="showAdd = !showAdd">{{ showAdd ? '收起' : '展开' }}</button>
        </div>
        <div v-if="showAdd" class="add-form">
          <label>名称<input v-model="form.label" placeholder="例如：我的中转站" /></label>
          <label>接口地址<input v-model="form.base_url" placeholder="https://api.example.com/v1" /></label>
          <label>模型名<input v-model="form.model" placeholder="例如：gpt-4o-mini / qwen-plus" /></label>
          <label>API Key<input v-model="form.key" type="password" placeholder="粘贴该接口的 Key" autocomplete="off" /></label>
          <div class="add-actions">
            <button class="st-btn primary" :disabled="adding" @click="addProvider">
              {{ adding ? '添加中…' : '添加并保存 Key' }}
            </button>
          </div>
          <p class="add-hint">接口需兼容 OpenAI 的 <code>/chat/completions</code>（大多数中转与本地推理都支持）。</p>
        </div>
      </section>

      <p class="st-status" v-if="status">{{ status }}</p>

      <footer class="st-ft">
        <button class="st-btn" @click="close">关闭</button>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch, onMounted } from 'vue'
import api from '../api.js'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'saved'])

const providers = ref([])
const drafts = reactive({})
const saving = reactive({})
const status = ref('')
const showAdd = ref(false)
const adding = ref(false)
const form = reactive({ label: '', base_url: '', model: '', key: '' })

async function load() {
  try {
    const r = await api.getSettings()
    apply(r.data.providers || [])
  } catch {
    providers.value = []
    status.value = '读取设置失败'
  }
}

function apply(list) {
  providers.value = list
  for (const p of list) {
    if (!(p.id in drafts)) drafts[p.id] = ''
    if (!(p.id in saving)) saving[p.id] = false
  }
}

function close() {
  status.value = ''
  emit('update:modelValue', false)
}

async function saveKey(p) {
  saving[p.id] = true
  status.value = ''
  try {
    const r = await api.setApiKey(p.id, drafts[p.id].trim())
    drafts[p.id] = ''
    apply(r.data.settings.providers || providers.value)
    status.value = `${p.label} 已保存`
    emit('saved')
  } catch (e) {
    status.value = '保存失败：' + (e.response?.data?.detail || e.message)
  } finally {
    saving[p.id] = false
  }
}

async function clearKey(p) {
  if (!confirm(`清除 ${p.label} 的 API Key？`)) return
  saving[p.id] = true
  status.value = ''
  try {
    const r = await api.setApiKey(p.id, '')
    apply(r.data.settings.providers || providers.value)
    status.value = `${p.label} 的 Key 已清除`
    emit('saved')
  } catch (e) {
    status.value = '清除失败：' + (e.response?.data?.detail || e.message)
  } finally {
    saving[p.id] = false
  }
}

async function addProvider() {
  adding.value = true
  status.value = ''
  try {
    const r = await api.addProvider(form.label.trim(), form.base_url.trim(), form.model.trim())
    const created = r.data.provider
    apply(r.data.providers || providers.value)
    if (form.key.trim()) {
      const k = await api.setApiKey(created.id, form.key.trim())
      apply(k.data.settings.providers || providers.value)
    }
    status.value = `${created.label} 已添加`
    form.label = ''
    form.base_url = ''
    form.model = ''
    form.key = ''
    showAdd.value = false
    emit('saved')
  } catch (e) {
    status.value = '添加失败：' + (e.response?.data?.detail || e.message)
  } finally {
    adding.value = false
  }
}

async function removeProvider(p) {
  if (!confirm(`删除供应商「${p.label}」？它的 Key 也会一并清除。`)) return
  saving[p.id] = true
  status.value = ''
  try {
    const r = await api.deleteProvider(p.id)
    apply(r.data.providers || providers.value)
    status.value = `${p.label} 已删除`
    emit('saved')
  } catch (e) {
    status.value = '删除失败：' + (e.response?.data?.detail || e.message)
  } finally {
    saving[p.id] = false
  }
}

watch(() => props.modelValue, v => { if (v) load() })
onMounted(() => { if (props.modelValue) load() })
</script>

<style scoped>
.settings-overlay {
  position: fixed; inset: 0; z-index: 300; display: flex;
  align-items: center; justify-content: center;
  background: rgba(0,0,0,0.6); backdrop-filter: blur(3px); padding: 16px;
}
.settings-modal {
  width: min(600px, 100%); max-height: 86vh; overflow-y: auto;
  background: #101010; border: 1px solid rgba(255,255,255,0.07);
  border-radius: 14px; padding: 20px 22px 16px;
  box-shadow: 0 24px 64px rgba(0,0,0,0.55);
}
.st-hd { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.st-hd h3 { font-size: 16px; font-weight: 600; color: #E0E0E0; }
.st-close { background: none; border: none; color: #555; cursor: pointer; padding: 4px; border-radius: 6px; }
.st-close:hover { color: #CCC; background: rgba(255,255,255,0.05); }
.st-desc { font-size: 12px; color: #5E5E5E; line-height: 1.65; margin-bottom: 14px; }
.st-desc code, .add-hint code { background: rgba(255,255,255,0.05); padding: 1px 4px; border-radius: 3px; }
.st-sec { margin-top: 14px; padding-top: 14px; border-top: 1px solid rgba(255,255,255,0.05); }
.key-row { display: flex; flex-direction: column; gap: 8px; }
.key-info { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.key-info b { font-size: 13px; color: #C8C8C8; font-weight: 600; }
.key-badge {
  font-size: 10px; padding: 1px 6px; border-radius: 5px;
  background: rgba(91,141,239,0.14); color: #7FA6F5;
}
.key-status { font-size: 11.5px; color: #666; }
.key-status.ok { color: #6FA36F; }
.key-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.key-actions input {
  flex: 1; min-width: 160px;
  background: #0B0B0B; border: 1px solid rgba(255,255,255,0.08);
  border-radius: 7px; color: #CCC; padding: 7px 10px; font-size: 12.5px;
  font-family: inherit; outline: none;
}
.key-actions input:focus { border-color: rgba(91,141,239,0.4); }
.key-model { display: block; margin-top: 6px; font-size: 11px; color: #4A4A4A; }
.add-hd { display: flex; align-items: center; justify-content: space-between; }
.add-hd h4 { font-size: 13px; font-weight: 600; color: #BBB; }
.add-form { display: grid; gap: 10px; margin-top: 12px; }
.add-form label { display: grid; gap: 4px; font-size: 11.5px; color: #6E6E6E; }
.add-form input {
  background: #0B0B0B; border: 1px solid rgba(255,255,255,0.08);
  border-radius: 7px; color: #CCC; padding: 8px 10px; font-size: 12.5px;
  font-family: inherit; outline: none;
}
.add-form input:focus { border-color: rgba(91,141,239,0.4); }
.add-actions { display: flex; justify-content: flex-end; }
.add-hint { font-size: 11px; color: #4E4E4E; line-height: 1.6; }
.st-status { margin-top: 14px; font-size: 12px; color: #C07070; }
.st-ft { display: flex; justify-content: flex-end; margin-top: 18px; }
.st-btn {
  padding: 7px 14px; border-radius: 7px; border: 1px solid rgba(255,255,255,0.08);
  background: #181818; color: #999; font-size: 12.5px; cursor: pointer; font-family: inherit;
  transition: all 0.15s;
}
.st-btn:hover:not(:disabled) { background: #222; color: #CCC; }
.st-btn.primary {
  background: linear-gradient(135deg, #5B8DEF, #6B7FEF); border: none;
  color: #fff; font-weight: 550;
}
.st-btn.danger:hover:not(:disabled) { background: rgba(224,80,80,0.12); color: #D06060; border-color: rgba(224,80,80,0.3); }
.st-btn:disabled { opacity: 0.45; cursor: not-allowed; }
</style>
