import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 30000 })

export default {
  getStats: () => api.get('/stats'),
  chat: (message, history, options = {}) => api.post('/chat', { message, history, ...options }, { timeout: 300000 }),
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
  createPersona: (name, guide) => api.post('/personas', { name, guide }),
  updatePersona: (name, guide) => api.put(`/personas/${encodeURIComponent(name)}`, { name, guide }),
  activatePersona: (name) => api.post(`/personas/${encodeURIComponent(name)}/activate`),
  deletePersona: (name) => api.delete(`/personas/${encodeURIComponent(name)}`),
  getMemoryGraph: (minImportance = 0) => api.get('/memories/graph', { params: { min_importance: minImportance } }),
  // 聊天会话
  createSession: (title) => api.post('/chat/sessions', title ? { title } : {}),
  listSessions: () => api.get('/chat/sessions'),
  getSession: (id) => api.get(`/chat/sessions/${id}`),
  saveSession: (id, messages) => api.put(`/chat/sessions/${id}`, { messages }),
  deleteSession: (id) => api.delete(`/chat/sessions/${id}`),
}
