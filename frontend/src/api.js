import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 30000 })

export default {
  getStats: () => api.get('/stats'),
  // 运行时设置：供应商 / 模型 / 叙事视角
  getSettings: () => api.get('/settings'),
  updateSettings: (patch) => api.put('/settings', patch),
  setApiKey: (provider, key) => api.put('/settings/keys', { provider, key }),
  listProviders: () => api.get('/providers'),
  addProvider: (label, baseUrl, model) => api.post('/providers', { label, base_url: baseUrl, model }),
  deleteProvider: (id) => api.delete(`/providers/${encodeURIComponent(id)}`),
  chat: (message, history, options = {}, config = {}) => api.post('/chat', { message, history, ...options }, { timeout: 300000, ...config }),
  // 流式对话：返回未解析的 fetch Response（SSE），由调用方逐段读取
  chatStream: (message, history, options = {}, config = {}) => fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history, ...options }),
    ...config,
  }),
  ingestDialogue: (dialogue, runPersonality = false) =>
    api.post('/dialogue/ingest', { dialogue, run_personality: runPersonality }),
  uploadDialogue: (formData) => api.post('/dialogue/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300000
  }),
  searchMemories: (q, topK = 10) => api.get('/memories/search', { params: { q, top_k: topK } }),
  searchSnippets: (q, topK = 5) => api.get('/snippets/search', { params: { q, top_k: topK } }),
  getPersonality: () => api.get('/personality'),
  resetPersonality: () => api.post('/personality/reset'),
  // 用户资料（自定义昵称）
  getProfile: () => api.get('/user/profile'),
  updateProfile: (nickname) => api.put('/user/profile', { nickname }),
  listPersonas: () => api.get('/personas'),
  getPersona: (name) => api.get(`/personas/${encodeURIComponent(name)}`),
  createPersona: (name, guide, narrativePerson = '') => api.post('/personas', { name, guide, narrative_person: narrativePerson }),
  updatePersona: (name, guide, narrativePerson = '') => api.put(`/personas/${encodeURIComponent(name)}`, { name, guide, narrative_person: narrativePerson }),
  activatePersona: (name) => api.post(`/personas/${encodeURIComponent(name)}/activate`),
  deletePersona: (name) => api.delete(`/personas/${encodeURIComponent(name)}`),
  getMemoryGraph: (minImportance = 0) => api.get('/memories/graph', { params: { min_importance: minImportance } }),
  // 聊天会话
  createSession: (title) => api.post('/chat/sessions', title ? { title } : {}),
  listSessions: () => api.get('/chat/sessions'),
  getSession: (id) => api.get(`/chat/sessions/${id}`),
  saveSession: (id, messages) => api.put(`/chat/sessions/${id}`, { messages }),
  deleteSession: (id) => api.delete(`/chat/sessions/${id}`),
  // 回收站（删除角色的完整备份）
  listTrash: () => api.get('/trash'),
  restoreTrash: (id, overwrite = false) => api.post(
    `/trash/${encodeURIComponent(id)}/restore`,
    null,
    { params: overwrite ? { overwrite: true } : {} }
  ),
  purgeTrash: (id) => api.delete(`/trash/${encodeURIComponent(id)}`),
}
