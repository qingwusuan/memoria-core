<template>
  <div class="settings-overlay" v-if="modelValue" @click.self="close">
    <div class="settings-modal">
      <header class="st-hd">
        <h3>设置</h3>
        <button class="st-close" @click="close">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
        </button>
      </header>

      <section class="st-sec">
        <h4>模型供应商</h4>
        <p class="st-desc">切换后下一次回复就用新模型；只显示已配置 Key 的供应商。</p>
        <div class="st-options">
          <button
            v-for="p in providers" :key="p.id"
            class="st-opt" :class="{ active: draftProvider === p.id }"
            :disabled="!p.has_key"
            @click="draftProvider = p.id"
          >
            <b>{{ p.label }}</b>
            <span>{{ p.model }}{{ p.has_key ? '' : ' · 未配置 Key' }}</span>
          </button>
        </div>
      </section>

      <section class="st-sec">
        <h4>默认叙事视角</h4>
        <p class="st-desc">
          没有单独设置视角的角色会跟随这里。单个角色可以在「角色管理」里覆盖。
        </p>
        <div class="st-options">
          <button
            class="st-opt" :class="{ active: draftPerson === 'third' }"
            @click="draftPerson = 'third'"
          >
            <b>第三人称</b>
            <span>像小说作者描写她：动作、神态、心理。</span>
          </button>
          <button
            class="st-opt" :class="{ active: draftPerson === 'first' }"
            @click="draftPerson = 'first'"
          >
            <b>第一人称</b>
            <span>她以「我」跟你说话，更像对话。</span>
          </button>
        </div>
      </section>

      <footer class="st-ft">
        <span class="st-status" v-if="status">{{ status }}</span>
        <button class="st-btn" @click="close">取消</button>
        <button class="st-btn primary" :disabled="saving" @click="save">
          {{ saving ? '保存中…' : '保存' }}
        </button>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import api from '../api.js'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'saved'])

const providers = ref([])
const provider = ref('')
const defaultPerson = ref('third')
const draftProvider = ref('')
const draftPerson = ref('third')
const saving = ref(false)
const status = ref('')

async function load() {
  try {
    const r = await api.getSettings()
    providers.value = r.data.providers || []
    provider.value = r.data.provider || ''
    defaultPerson.value = r.data.narrative_person || 'third'
    draftProvider.value = provider.value
    draftPerson.value = defaultPerson.value
  } catch {
    providers.value = []
  }
}

function close() {
  status.value = ''
  emit('update:modelValue', false)
}

async function save() {
  saving.value = true
  try {
    const patch = {}
    if (draftProvider.value && draftProvider.value !== provider.value) patch.provider = draftProvider.value
    if (draftPerson.value !== defaultPerson.value) patch.narrative_person = draftPerson.value
    if (Object.keys(patch).length) await api.updateSettings(patch)
    emit('saved')
    close()
  } catch (e) {
    status.value = '保存失败：' + (e.response?.data?.detail || e.message)
  } finally {
    saving.value = false
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
  width: min(520px, 100%); max-height: 86vh; overflow-y: auto;
  background: #101010; border: 1px solid rgba(255,255,255,0.07);
  border-radius: 14px; padding: 20px 22px 16px;
  box-shadow: 0 24px 64px rgba(0,0,0,0.55);
}
.st-hd { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.st-hd h3 { font-size: 16px; font-weight: 600; color: #E0E0E0; }
.st-close { background: none; border: none; color: #555; cursor: pointer; padding: 4px; border-radius: 6px; }
.st-close:hover { color: #CCC; background: rgba(255,255,255,0.05); }
.st-sec { margin-top: 18px; }
.st-sec h4 { font-size: 13px; font-weight: 600; color: #BBB; margin-bottom: 3px; }
.st-desc { font-size: 12px; color: #5E5E5E; line-height: 1.6; margin-bottom: 10px; }
.st-options { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.st-opt {
  text-align: left; background: #161616; border: 1px solid rgba(255,255,255,0.06);
  border-radius: 9px; padding: 11px 12px; cursor: pointer;
  display: flex; flex-direction: column; gap: 4px; transition: all 0.15s;
  font-family: inherit;
}
.st-opt b { font-size: 13px; color: #C8C8C8; font-weight: 600; }
.st-opt span { font-size: 11.5px; color: #666; line-height: 1.5; }
.st-opt:hover:not(:disabled) { border-color: rgba(255,255,255,0.14); background: #1A1A1A; }
.st-opt.active { border-color: rgba(91,141,239,0.5); background: rgba(91,141,239,0.07); }
.st-opt.active b { color: #8FB3FF; }
.st-opt:disabled { opacity: 0.4; cursor: not-allowed; }
.st-ft { display: flex; align-items: center; justify-content: flex-end; gap: 8px; margin-top: 22px; }
.st-status { margin-right: auto; font-size: 11.5px; color: #C07070; }
.st-btn {
  padding: 8px 16px; border-radius: 7px; border: 1px solid rgba(255,255,255,0.08);
  background: #181818; color: #999; font-size: 13px; cursor: pointer; font-family: inherit;
  transition: all 0.15s;
}
.st-btn:hover { background: #222; color: #CCC; }
.st-btn.primary {
  background: linear-gradient(135deg, #5B8DEF, #6B7FEF); border: none;
  color: #fff; font-weight: 550;
}
.st-btn:disabled { opacity: 0.5; cursor: not-allowed; }
@media (max-width: 768px) {
  .st-options { grid-template-columns: 1fr; }
}
</style>
