import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import { createPinia } from 'pinia'
import App from './App.vue'
import CharacterManager from './views/CharacterManager.vue'
import MemoryGraph from './views/MemoryGraph.vue'
import PersonalityPanel from './views/PersonalityPanel.vue'
import Chat from './views/Chat.vue'

const routes = [
  { path: '/', redirect: '/chat' },
  { path: '/chat', component: Chat, meta: { label: '对话', icon: 'chat' } },
  { path: '/character', component: CharacterManager, meta: { label: '角色', icon: 'persona' } },
  { path: '/memory', component: MemoryGraph, meta: { label: '记忆图谱', icon: 'graph' } },
  { path: '/personality', component: PersonalityPanel, meta: { label: '性格面板', icon: 'radar' } },
]

const router = createRouter({ history: createWebHashHistory(), routes })

const app = createApp(App)
app.use(router)
app.use(createPinia())
app.mount('#app')
