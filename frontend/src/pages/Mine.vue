<template>
  <div class="wall">
    <h1 class="serif">我的认领</h1>
    <input v-model="name" @change="load" placeholder="认领人名" />
    <p v-if="err" class="err">{{ err }}</p>
    <article v-for="w in rows" :key="w.id" class="card" @click="$router.push('/wishes/'+w.id)">
      <h3>{{ w.title }}</h3>
      <p>{{ w.note }}</p>
      <span class="tag">{{ w.status }} · rev {{ w.note_rev }} · 到期 {{ w.expires_at }}</span>
      <span v-if="w.awaiting_ack" class="badge">附言待确认</span>
      <div v-if="w.awaiting_ack" style="margin-top:8px">
        <button @click.stop="ack(w)">确认附言 rev {{ w.note_rev }}</button>
      </div>
    </article>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
const name = ref('访客')
const rows = ref([])
const err = ref('')
async function load() { rows.value = await api('/mine?claimer=' + encodeURIComponent(name.value)) }
async function ack(w) {
  err.value = ''
  try {
    await api('/wishes/' + w.id + '/note/ack', { method: 'POST', body: JSON.stringify({ claimer: name.value }) })
    await load()
  } catch (e) { err.value = e.message }
}
onMounted(load)
</script>
