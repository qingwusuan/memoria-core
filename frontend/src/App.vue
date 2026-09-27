<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="sb-brand" @click="$router.push('/')">
        <span class="sb-logo">M</span>
        <span class="sb-name">Memoria</span>
      </div>

      <nav class="sb-nav">
        <router-link v-for="r in navRoutes" :key="r.path" :to="r.path" class="sb-link">
          <span class="sb-icon" v-html="icons[r.meta.icon]"></span>
          <span>{{ r.meta.label }}</span>
        </router-link>
      </nav>

      <div class="sb-footer">
        <div class="sb-divider"></div>
        <div class="sb-stats">
          <div class="stat-block">
            <span class="stat-val">{{ stats?.total_memories ?? '—' }}</span>
            <span class="stat-label">记忆</span>
          </div>
          <div class="stat-block">
            <span class="stat-val">{{ stats?.personality?.round_count ?? '—' }}</span>
            <span class="stat-label">回合</span>
          </div>
        </div>
        <div class="sb-version">Memoria v0.1</div>
      </div>
    </aside>

    <main class="main">
      <router-view v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import api from './api.js'

const router = useRouter()
const stats = ref(null)

const navRoutes = computed(() =>
  router.options.routes.filter(r => r.meta?.label)
)

const icons = {
  chat: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
  persona: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="8" r="4"/><path d="M6 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2"/></svg>',
  graph: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="2.5"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
  radar: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5"/><line x1="12" y1="22" x2="12" y2="2"/><line x1="2" y1="8.5" x2="22" y2="15.5"/></svg>',
}

onMounted(async () => {
  try { const r = await api.getStats(); stats.value = r.data } catch {}
})
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Inter", sans-serif;
  background: #0B0B0B; color: #D0D0D0; -webkit-font-smoothing: antialiased;
  letter-spacing: -0.01em;
}

.shell { display: flex; height: 100vh; overflow: hidden; }

.sidebar {
  width: 220px; flex-shrink: 0; background: #0D0D0D;
  border-right: 1px solid rgba(255,255,255,0.04);
  display: flex; flex-direction: column; padding: 20px 10px 14px;
}

.sb-brand {
  display: flex; align-items: center; gap: 9px; padding: 4px 10px 22px;
  cursor: pointer; user-select: none;
}
.sb-logo {
  width: 32px; height: 32px; border-radius: 8px;
  background: linear-gradient(135deg, #5B8DEF, #8B6FE8);
  display: flex; align-items: center; justify-content: center;
  font-size: 15px; font-weight: 700; color: #fff;
  box-shadow: 0 2px 8px rgba(91,141,239,0.25);
}
.sb-name { font-size: 15px; font-weight: 600; color: #CCC; letter-spacing: 0.02em; }

.sb-nav { flex: 1; display: flex; flex-direction: column; gap: 1px; }

.sb-link {
  display: flex; align-items: center; gap: 10px; padding: 9px 10px;
  border-radius: 7px; color: #888; text-decoration: none;
  font-size: 13.5px; font-weight: 450; transition: all 0.18s ease;
  position: relative;
}
.sb-link:hover { background: rgba(255,255,255,0.03); color: #B0B0B0; }
.sb-link.router-link-exact-active {
  background: rgba(255,255,255,0.04); color: #E0E0E0; font-weight: 500;
}
.sb-link.router-link-exact-active::before {
  content: ''; position: absolute; left: 0; top: 50%; transform: translateY(-50%);
  width: 2.5px; height: 16px; border-radius: 2px; background: linear-gradient(180deg, #5B8DEF, #8B6FE8);
}
.sb-icon { display: flex; align-items: center; opacity: 0.55; transition: opacity 0.18s; }
.sb-link:hover .sb-icon { opacity: 0.75; }
.sb-link.router-link-exact-active .sb-icon { opacity: 0.9; }

.sb-footer { padding: 10px 10px 0; }
.sb-divider { height: 1px; background: rgba(255,255,255,0.04); margin-bottom: 12px; }
.sb-stats { display: flex; gap: 22px; margin-bottom: 10px; }
.stat-block { display: flex; flex-direction: column; gap: 1px; }
.stat-val { font-size: 14px; font-weight: 600; color: #B0B0B0; font-variant-numeric: tabular-nums; }
.stat-label { font-size: 10px; color: #555; text-transform: uppercase; letter-spacing: 0.04em; font-weight: 500; }
.sb-version { font-size: 10.5px; color: #3A3A3A; }

.main { flex: 1; overflow: auto; padding: 36px 44px; background: #0B0B0B; }

.page-enter-active, .page-leave-active { transition: opacity 0.18s ease, transform 0.18s ease; }
.page-enter-from { opacity: 0; transform: translateY(8px); }
.page-leave-to { opacity: 0; transform: translateY(-8px); }

::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.06); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.1); }

/* ────────── 移动端适配（<768px）：侧边栏转底部导航 ────────── */
@media (max-width: 768px) {
  .shell { flex-direction: column; }
  .sidebar {
    width: 100%; height: 56px; flex-shrink: 0;
    flex-direction: row; align-items: center;
    border-right: none; border-top: 1px solid rgba(255,255,255,0.05);
    padding: 0 6px; order: 2;
  }
  .sb-brand { display: none; }
  .sb-footer { display: none; }
  .sb-nav { flex-direction: row; justify-content: space-around; gap: 0; }
  .sb-link {
    flex: 1; flex-direction: column; gap: 2px;
    padding: 6px 2px; font-size: 10px; justify-content: center;
    border-radius: 8px;
  }
  .sb-link.router-link-exact-active::before { display: none; }
  .sb-icon svg { width: 20px; height: 20px; }
  .main { padding: 12px 12px 8px; }
}
</style>
