<template>
  <div class="graph-page">
    <header class="page-hd">
      <div>
        <h1>记忆图谱</h1>
        <p class="hd-sub">事件与对话片段的关联网络可视化</p>
      </div>
      <div class="filters">
        <div class="imp-slider">
          <label>重要度 ≥ {{ (minImportance * 100).toFixed(0) }}%</label>
          <input type="range" min="0" max="95" step="5" v-model.number="impPct" @input="onImpChange" />
        </div>
        <button :class="['chip', { on: showEvents }]" @click="showEvents = !showEvents; updateFilter()">
          <span class="dot" style="background:#5B8DEF"></span>事件
        </button>
        <button :class="['chip', { on: showSnippets }]" @click="showSnippets = !showSnippets; updateFilter()">
          <span class="dot" style="background:#E89060"></span>片段
        </button>
        <span class="count" v-if="nodes.length">{{ visibleNodes.length }} / {{ nodes.length }} 节点</span>
      </div>
    </header>

    <div class="graph-box">
      <svg ref="svgRef"></svg>
      <div class="empty-state" v-if="!nodes.length">
        <div class="es-icon">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
            <circle cx="12" cy="12" r="2.5"/><path d="M12 2v4m0 12v4M2 12h4m12 0h4M5.64 5.64l2.83 2.83m7.07 7.07 2.83 2.83M5.64 18.36l2.83-2.83m7.07-7.07 2.83-2.83"/>
          </svg>
        </div>
        <p class="es-title">暂无记忆数据</p>
        <p class="es-desc">导入对话数据后，AI 提取的事件与对话片段将在此以力导向图呈现关联</p>
      </div>
    </div>

    <transition name="slide">
      <div class="detail-pop" v-if="detail">
        <div class="dp-type" :class="detail.type">{{ detail.type === 'event' ? '事件' : '片段' }}</div>
        <p class="dp-text">{{ detailText }}</p>
        <div class="dp-meta">
          <span v-if="detail.importance !== undefined">重要性 {{ (detail.importance * 100).toFixed(0) }}%</span>
        </div>
        <button class="dp-close" @click="detail = null">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
        </button>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import * as d3 from 'd3'
import api from '../api.js'

const svgRef = ref(null)
const nodes = ref([])
const detail = ref(null)
const showEvents = ref(true)
const showSnippets = ref(false)
const visibleNodes = ref([])
const minImportance = ref(0.6)
const impPct = ref(60)

const detailText = computed(() => {
  if (!detail.value) return ''
  return detail.value.full_text || detail.value.label || ''
})

function onImpChange() {
  minImportance.value = impPct.value / 100
  load()
}

function updateFilter() {
  visibleNodes.value = nodes.value.filter(n =>
    (n.type === 'event' && showEvents.value) || (n.type === 'snippet' && showSnippets.value)
  )
  nextTick(() => draw())
}

async function load() {
  try {
    const r = await api.getMemoryGraph(minImportance.value);
    nodes.value = r.data.nodes || []
    visibleNodes.value = nodes.value.filter(n => n.type === 'event');
    await nextTick();
    draw()
  } catch {}
}

function draw() {
  if (!svgRef.value || !visibleNodes.value.length) return
  const svg = d3.select(svgRef.value); svg.selectAll('*').remove()
  const W = svgRef.value.clientWidth || 900, H = svgRef.value.clientHeight || 520
  const sim = d3.forceSimulation(visibleNodes.value)
    .force('charge', d3.forceManyBody().strength(-140))
    .force('center', d3.forceCenter(W/2, H/2))
    .force('collide', d3.forceCollide(36))

  const g = svg.append('g')
  svg.call(d3.zoom().scaleExtent([0.25, 4]).on('zoom', e => g.attr('transform', e.transform)))

  const node = g.selectAll('g.node-group').data(visibleNodes.value).join('g')
    .attr('class', 'node-group').style('cursor', 'pointer')
    .on('click', (e, d) => { e.stopPropagation(); detail.value = d })
    .call(d3.drag()
      .on('start', (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y })
      .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y })
      .on('end', (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null }))

  node.append('circle')
    .attr('r', d => (d.type === 'event' ? 4.5 + (d.importance || 0.5) * 11 : 4))
    .attr('fill', d => d.type === 'event' ? '#5B8DEF' : '#E89060')
    .attr('stroke', '#0B0B0B').attr('stroke-width', 2.5)
    .attr('opacity', 0.85)

  node.append('text')
    .text(d => (d.label?.length > 28 ? d.label.slice(0, 28) + '…' : d.label || ''))
    .attr('x', 15).attr('y', 4).attr('fill', '#777').style('font-size', '10.5px')
    .style('font-family', 'inherit').style('pointer-events', 'none').style('font-weight', '450')

  sim.on('tick', () => { node.attr('transform', d => `translate(${d.x},${d.y})`) })
  svg.on('click', () => { detail.value = null })
}

onMounted(load)
</script>

<style scoped>
.graph-page { height: calc(100vh - 72px); display: flex; flex-direction: column; width: 100%; max-width: 1200px; margin: 0 auto; }
.page-hd { display: flex; align-items: flex-start; gap: 16px; margin-bottom: 16px; }
.page-hd h1 { font-size: 22px; font-weight: 600; color: #E0E0E0; letter-spacing: -0.02em; }
.hd-sub { font-size: 12.5px; color: #666; margin-top: 4px; }

.filters { display: flex; align-items: center; gap: 8px; margin-left: auto; flex-wrap: wrap; }
.imp-slider { display: flex; align-items: center; gap: 6px; }
.imp-slider label { font-size: 11.5px; color: #888; white-space: nowrap; min-width: 80px; }
.imp-slider input[type="range"] { 
  width: 90px; height: 4px; -webkit-appearance: none; appearance: none;
  background: #2A2A2A; border-radius: 2px; outline: none; cursor: pointer;
}
.imp-slider input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none; width: 12px; height: 12px; border-radius: 50%;
  background: #5B8DEF; cursor: pointer;
}
.chip {
  display: inline-flex; align-items: center; gap: 6px; padding: 5px 13px;
  border-radius: 18px; border: 1px solid rgba(255,255,255,0.05);
  background: #111; color: #888; font-size: 12px; font-weight: 500;
  cursor: pointer; transition: all 0.2s;
}
.chip:hover { border-color: rgba(255,255,255,0.1); color: #B0B0B0; }
.chip.on { background: rgba(91,141,239,0.10); border-color: rgba(91,141,239,0.3); color: #5B8DEF; }
.dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; flex-shrink: 0; }
.count { font-size: 11.5px; color: #555; margin-left: 8px; font-variant-numeric: tabular-nums; }

.graph-box {
  flex: 1; background: #0E0E0E; border: 1px solid rgba(255,255,255,0.04);
  border-radius: 12px; position: relative; overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}
.graph-box svg { width: 100%; height: 100%; }

.empty-state {
  position: absolute; inset: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
}
.es-icon {
  width: 64px; height: 64px; border-radius: 16px;
  background: linear-gradient(135deg, rgba(91,141,239,0.06), rgba(232,144,96,0.06));
  display: inline-flex; align-items: center; justify-content: center;
  color: #666; margin-bottom: 20px;
}
.es-title { font-size: 16px; font-weight: 600; color: #999; margin-bottom: 6px; }
.es-desc { font-size: 13px; color: #555; line-height: 1.6; max-width: 300px; text-align: center; }

.detail-pop {
  position: fixed; bottom: 28px; right: 40px; width: 300px;
  background: #151515; border: 1px solid rgba(255,255,255,0.06);
  border-radius: 12px; padding: 18px 20px; z-index: 50;
  box-shadow: 0 12px 40px rgba(0,0,0,0.55);
}
.dp-type { font-size: 10.5px; font-weight: 600; letter-spacing: 0.06em; margin-bottom: 8px; }
.dp-type.event { color: #5B8DEF; }
.dp-type.snippet { color: #E89060; }
.detail-pop p { font-size: 13px; line-height: 1.7; color: #999; margin-bottom: 8px; }
.dp-text { max-height: 200px; overflow-y: auto; white-space: pre-wrap; word-break: break-word; }
.dp-meta { font-size: 11px; color: #666; }
.dp-close { position: absolute; top: 10px; right: 10px; background: none; border: none; color: #444; cursor: pointer; padding: 4px; border-radius: 6px; }
.dp-close:hover { color: #BBB; background: rgba(255,255,255,0.04); }

.slide-enter-active, .slide-leave-active { transition: all 0.22s ease; }
.slide-enter-from, .slide-leave-to { opacity: 0; transform: translateY(14px); }

/* ────────── 移动端适配（<768px）────────── */
@media (max-width: 768px) {
  .graph-page { height: calc(100vh - 76px); }
  .page-hd { flex-direction: column; gap: 10px; margin-bottom: 12px; }
  .page-hd h1 { font-size: 19px; }
  .filters { margin-left: 0; width: 100%; gap: 6px; }
  .imp-slider { flex: 1; min-width: 0; }
  .imp-slider label { min-width: 0; }
  .imp-slider input[type="range"] { flex: 1; width: auto; }
  .count { margin-left: 0; }

  /* 详情弹层 → 底部全宽 */
  .detail-pop {
    left: 10px; right: 10px; bottom: 10px; width: auto;
    max-height: 60vh; overflow-y: auto;
  }
}
</style>
