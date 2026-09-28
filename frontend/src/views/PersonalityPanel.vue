<template>
  <div class="pp-page">
    <header class="page-hd">
      <div>
        <h1>性格面板</h1>
        <p class="hd-sub">对话积累中动态变迁的多维性格档案</p>
      </div>
      <div class="hd-right">
        <span class="meta" v-if="data">
          第 {{ data.round_count }} 轮 &middot; 亲密度 {{ (data.intimacy * 100).toFixed(0) }}%
        </span>
        <button class="btn btn-danger" v-if="data?.round_count" @click="reset">重置</button>
      </div>
    </header>

    <div class="empty-state" v-if="!data">
      <div class="es-icon">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
          <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5"/>
        </svg>
      </div>
      <p class="es-title">暂无性格数据</p>
      <p class="es-desc">随着对话的累积，AI 将从交互中提取性格信号，绘制表层与深层的多维画像</p>
    </div>

    <div class="pp-grid" v-else>
      <div class="card radar-card">
        <h3>维度雷达</h3>
        <canvas ref="canvas" width="440" height="440"></canvas>
        <div class="legend">
          <span><i style="background:#5B8DEF"></i>表层</span>
          <span><i style="background:#E89060"></i>深层</span>
        </div>
      </div>

      <div class="card table-card">
        <h3>维度详情</h3>
        <table>
          <thead><tr><th>维度</th><th>表层 (0–1)</th><th>深层 (0–1)</th><th>偏差</th></tr></thead>
          <tbody>
            <tr v-for="d in sorted" :key="d.index" :class="{ warn: Math.abs(d.gap) > 0.25 }">
              <td class="dim-name">{{ d.name }}</td>
              <td>
                <div class="bar"><div class="bar-fill s" :style="{width: d.surface*100+'%'}"></div><span>{{ d.surface.toFixed(2) }}</span></div>
              </td>
              <td>
                <div class="bar"><div class="bar-fill d" :style="{width: d.deep*100+'%'}"></div><span>{{ d.deep.toFixed(2) }}</span></div>
              </td>
              <td class="gap-cell" :class="{ alert: Math.abs(d.gap) > 0.25 }">
                {{ d.gap > 0 ? '+' : '' }}{{ d.gap.toFixed(2) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card sens-card" v-if="data.sensitive_points?.length">
        <h3>敏感点</h3>
        <div class="sens-list">
          <div class="sens-item" v-for="(sp, i) in data.sensitive_points" :key="i">
            <span class="sens-kw">{{ sp.keywords?.join(' / ') }}</span>
            <span class="sens-arrow">&rarr;</span>
            <span class="sens-dim">{{ sp.dimension }}</span>
            <span class="sens-delta" :class="{ pos: sp.delta > 0, neg: sp.delta < 0 }">
              {{ sp.delta > 0 ? '+' : '' }}{{ sp.delta }}
            </span>
            <span class="sens-desc" v-if="sp.description">— {{ sp.description }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import api from '../api.js'

const data = ref(null)
const canvas = ref(null)

const sorted = computed(() => {
  if (!data.value?.dimensions) return []
  return [...data.value.dimensions].sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap))
})

async function load() {
  try {
    const r = await api.getPersonality()
    data.value = r.data
    await nextTick()
    drawRadar()
  } catch (e) {
    data.value = null
    alert('加载性格数据失败：' + (e.response?.data?.detail || e.message))
  }
}

function drawRadar() {
  const cvs = canvas.value; if (!cvs || !data.value?.dimensions) return
  const ctx = cvs.getContext('2d'), dims = data.value.dimensions
  const w = 440, h = 440, cx = w/2, cy = h/2, R = 160, n = dims.length

  ctx.clearRect(0, 0, w, h)

  for (let r = 1; r <= 5; r++) {
    ctx.beginPath()
    for (let i = 0; i < n; i++) {
      const a = Math.PI*2*i/n - Math.PI/2
      const x = cx + R * r/5 * Math.cos(a), y = cy + R * r/5 * Math.sin(a)
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)
    }
    ctx.closePath(); ctx.strokeStyle = 'rgba(255,255,255,0.04)'; ctx.stroke()
  }

  for (let i = 0; i < n; i++) {
    const a = Math.PI*2*i/n - Math.PI/2
    ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + R * Math.cos(a), cy + R * Math.sin(a))
    ctx.strokeStyle = 'rgba(255,255,255,0.03)'; ctx.stroke()
  }

  ctx.fillStyle = '#757575'; ctx.font = '11px -apple-system, "PingFang SC", sans-serif'; ctx.textAlign = 'center'
  for (let i = 0; i < n; i++) {
    const a = Math.PI*2*i/n - Math.PI/2
    ctx.fillText(dims[i].name, cx + (R + 26) * Math.cos(a), cy + (R + 26) * Math.sin(a) + 4)
  }

  drawPoly(ctx, dims.map(d => d.surface * 5), '#5B8DEF', 0.28)
  drawPoly(ctx, dims.map(d => d.deep * 5), '#E89060', 0.28)
}

function drawPoly(ctx, vals, color, alpha) {
  const n = vals.length, cx = 220, cy = 220, R = 160
  ctx.beginPath()
  for (let i = 0; i < n; i++) {
    const a = Math.PI * 2 * i / n - Math.PI / 2, r = Math.min(vals[i], 5)
    const x = cx + R * r / 5 * Math.cos(a), y = cy + R * r / 5 * Math.sin(a)
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)
  }
  ctx.closePath()
  const hex = Math.round(alpha * 255).toString(16).padStart(2, '0')
  ctx.fillStyle = color + hex; ctx.fill()
  ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.lineJoin = 'round'; ctx.stroke()
}

async function reset() {
  if (!confirm('确定重置所有性格数据？此操作不可撤销。')) return
  try {
    await api.resetPersonality()
    data.value = null
  } catch (e) {
    alert('重置失败：' + (e.response?.data?.detail || e.message))
  }
}

onMounted(load)
</script>

<style scoped>
.pp-page { max-width: 980px; margin: 0 auto; }
.page-hd { display: flex; align-items: flex-start; margin-bottom: 32px; }
.page-hd h1 { font-size: 22px; font-weight: 600; color: #E0E0E0; letter-spacing: -0.02em; }
.hd-sub { font-size: 12.5px; color: #666; margin-top: 4px; }
.hd-right { margin-left: auto; display: flex; align-items: center; gap: 14px; }
.meta { font-size: 13px; color: #757575; font-variant-numeric: tabular-nums; }

.empty-state { text-align: center; padding: 80px 20px 60px; max-width: 420px; margin: 0 auto; }
.es-icon {
  width: 64px; height: 64px; border-radius: 16px;
  background: linear-gradient(135deg, rgba(91,141,239,0.06), rgba(232,144,96,0.06));
  display: inline-flex; align-items: center; justify-content: center;
  color: #666; margin-bottom: 20px;
}
.es-title { font-size: 16px; font-weight: 600; color: #999; margin-bottom: 6px; }
.es-desc { font-size: 13px; color: #555; line-height: 1.7; }

.pp-grid { display: grid; grid-template-columns: 440px 1fr; gap: 12px; }
.card {
  background: #111; border: 1px solid rgba(255,255,255,0.04);
  border-radius: 12px; padding: 22px; box-shadow: 0 1px 3px rgba(0,0,0,0.3);
}
.card h3 { font-size: 13.5px; font-weight: 600; color: #999; margin-bottom: 16px; }

.radar-card { display: flex; flex-direction: column; align-items: center; }
.radar-card canvas { max-width: 100%; }
.legend { display: flex; gap: 22px; margin-top: 4px; font-size: 12px; color: #757575; }
.legend i { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 5px; }

.table-card { max-height: 440px; overflow-y: auto; }
.table-card table { width: 100%; border-collapse: collapse; font-size: 13px; }
.table-card th { text-align: left; padding: 8px 10px 8px 0; color: #666; font-weight: 500; font-size: 11px; border-bottom: 1px solid rgba(255,255,255,0.04); }
.table-card td { padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.02); }
.dim-name { font-weight: 550; color: #B0B0B0; }
tr.warn td { background: rgba(224, 80, 80, 0.04); }
.bar { display: flex; align-items: center; gap: 8px; }
.bar-fill { height: 5px; border-radius: 3px; min-width: 2px; }
.bar-fill.s { background: #5B8DEF; }
.bar-fill.d { background: #E89060; }
.bar span { font-size: 12px; color: #757575; min-width: 36px; font-variant-numeric: tabular-nums; }
.gap-cell { font-variant-numeric: tabular-nums; }
.gap-cell.alert { color: #D06060; font-weight: 600; }

.sens-card { grid-column: 1 / -1; }
.sens-list { display: flex; flex-direction: column; gap: 4px; }
.sens-item { padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.02); font-size: 13px; color: #999; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.sens-kw { color: #E89060; font-weight: 550; }
.sens-arrow { color: #555; }
.sens-dim { color: #B0B0B0; font-weight: 500; }
.sens-delta { font-weight: 600; font-size: 12px; padding: 1px 6px; border-radius: 4px; }
.sens-delta.pos { background: rgba(91,141,239,0.1); color: #5B8DEF; }
.sens-delta.neg { background: rgba(224,80,80,0.1); color: #D06060; }
.sens-desc { color: #666; font-size: 12px; }

.btn {
  display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px;
  border: 1px solid rgba(255,255,255,0.06); background: #181818; color: #999;
  border-radius: 7px; cursor: pointer; font-size: 13px; font-weight: 500;
  transition: all 0.18s;
}
.btn:hover { background: #222; border-color: rgba(255,255,255,0.1); color: #CCC; }
.btn-danger:hover { background: rgba(224,80,80,0.12); border-color: rgba(224,80,80,0.25); color: #D06060; }

/* ────────── 移动端适配（<768px）────────── */
@media (max-width: 768px) {
  .page-hd { flex-direction: column; gap: 10px; margin-bottom: 20px; }
  .page-hd h1 { font-size: 19px; }
  .hd-right { margin-left: 0; width: 100%; justify-content: space-between; }
  .pp-grid { grid-template-columns: 1fr; }
  .radar-card canvas { max-width: 100%; height: auto; }
  .table-card { max-height: none; overflow-x: auto; }
  .table-card table { min-width: 460px; }
  .sens-card { grid-column: 1; }
}
</style>
