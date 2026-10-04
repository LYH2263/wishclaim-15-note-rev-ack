<template>
  <div class="wall">
    <h1 class="serif">{{ w.title }}</h1>
    <p>
      {{ w.note }}
      <span class="tag">v{{ w.note_rev }}</span>
    </p>
    <p class="tag">状态 {{ w.status }} · 认领人 {{ w.claimer || '—' }}</p>

    <div v-if="w.awaiting_ack" class="pending-box">
      <strong>附言待确认</strong>
      <p style="margin:6px 0">{{ w.pending_note }} <span class="tag">r{{ w.pending_rev }}</span></p>
      <p class="tag">请在 {{ w.pending_expires_at }} 前确认，超时自动驳回</p>
      <button @click="ack">确认新版</button>
    </div>

    <details class="history-box">
      <summary class="tag">回看上一版</summary>
      <div v-for="rv in revisions" :key="rv.rev">
        <p style="margin:6px 0">
          <span class="tag">v{{ rv.rev }} · {{ rv.state }}{{ rv.acked_at ? ' · 已确认 ' + rv.acked_at : '' }}</span><br />
          {{ rv.note }}
        </p>
      </div>
    </details>

    <p v-if="err" class="err">{{ err }}</p>
    <p v-if="msg" class="tag">{{ msg }}</p>
    <input v-model="claimer" placeholder="你的名字" />
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button @click="claim">认领锁定</button>
      <button class="ghost" @click="release">释放</button>
      <button class="ghost" :disabled="w.awaiting_ack" :title="w.awaiting_ack ? '附言待确认，暂不可核销' : ''" @click="fulfill">核销完成</button>
    </div>

    <hr style="border:0;border-top:1px dashed var(--line);margin:18px 0" />
    <h3 class="serif">修改附言</h3>
    <textarea v-model="draft" rows="4" placeholder="新附言" />
    <button @click="save">保存附言</button>
  </div>
</template>
<script setup>
import { ref, onMounted, watch } from 'vue'
import { api } from '../api'
const props = defineProps({ id: String })
const w = ref({})
const claimer = ref('访客')
const draft = ref('')
const err = ref('')
const msg = ref('')
const revisions = ref([])
async function load() {
  w.value = await api('/wishes/' + props.id)
  draft.value = w.value.pending_note || w.value.note || ''
  revisions.value = (w.value.revisions || []).filter(rv => rv.state === 'history').slice(0, 1)
}
async function act(path, body) {
  err.value = ''; msg.value = ''
  try { await api('/wishes/' + props.id + path, { method: 'POST', body: JSON.stringify(body || {}) }); await load() }
  catch (e) { err.value = e.message }
}
const claim = () => act('/claim', { claimer: claimer.value })
const release = () => act('/release')
const fulfill = () => act('/fulfill')
const ack = () => act('/ack', { claimer: claimer.value })
async function save() {
  err.value = ''; msg.value = ''
  try {
    const r = await api('/wishes/' + props.id + '/note', {
      method: 'PATCH', body: JSON.stringify({ note: draft.value }),
    })
    msg.value = r.mode === 'direct' ? '附言已更新'
      : (w.value.awaiting_ack ? '已替换待确认版本，等待认领人确认' : '已提交，等待认领人确认后生效')
    await load()
  } catch (e) { err.value = e.message }
}
watch(() => props.id, load)
onMounted(load)
</script>
