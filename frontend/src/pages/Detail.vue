<template>
  <div class="wall">
    <h1 class="serif">{{ w.title }}</h1>
    <p>{{ w.note }}</p>
    <p class="tag">
      状态 {{ w.status }} · 认领人 {{ w.claimer || '—' }} · 附言 rev {{ w.note_rev }}
      <span v-if="w.awaiting_ack" class="badge">待确认</span>
    </p>
    <div v-if="w.awaiting_ack && w.previous_note != null" style="margin-bottom:12px">
      <button class="ghost" @click="showPrev = !showPrev">
        {{ showPrev ? '隐藏上一版' : '回看上一版 rev ' + w.previous_rev }}
      </button>
      <p v-if="showPrev" class="prev-note">{{ w.previous_note }}</p>
    </div>
    <p v-if="err" class="err">{{ err }}</p>
    <input v-model="claimer" placeholder="你的名字" />
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button @click="claim">认领锁定</button>
      <button class="ghost" @click="release">释放</button>
      <button class="ghost" :disabled="w.fulfill_blocked" @click="fulfill">核销完成</button>
      <button v-if="w.awaiting_ack" @click="ack">确认附言 rev {{ w.note_rev }}</button>
    </div>
    <template v-if="w.status && w.status !== 'fulfilled'">
      <h3 class="serif" style="margin-top:24px">修改附言</h3>
      <textarea v-model="draft" rows="3" placeholder="新的附言" />
      <button @click="saveNote">保存附言</button>
      <p v-if="w.status === 'claimed'" class="tag">已认领：保存后进入待确认，认领人确认前不可核销</p>
    </template>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
const props = defineProps({ id: String })
const w = ref({})
const claimer = ref('访客')
const draft = ref('')
const showPrev = ref(false)
const err = ref('')
async function load() {
  w.value = await api('/wishes/' + props.id)
  draft.value = w.value.note || ''
}
async function run(fn) {
  err.value = ''
  try { await fn(); await load() } catch (e) { err.value = e.message }
}
const claim = () => run(() => api('/wishes/' + props.id + '/claim', { method: 'POST', body: JSON.stringify({ claimer: claimer.value }) }))
const release = () => run(() => api('/wishes/' + props.id + '/release', { method: 'POST', body: '{}' }))
const fulfill = () => run(() => api('/wishes/' + props.id + '/fulfill', { method: 'POST', body: '{}' }))
const ack = () => run(() => api('/wishes/' + props.id + '/note/ack', { method: 'POST', body: JSON.stringify({ claimer: claimer.value }) }))
const saveNote = () => run(() => api('/wishes/' + props.id + '/note', { method: 'POST', body: JSON.stringify({ note: draft.value }) }))
onMounted(load)
</script>
