<template>
  <div class="wall">
    <h1 class="serif">我的认领</h1>
    <input v-model="name" @change="load" placeholder="认领人名" />
    <article v-for="w in rows" :key="w.id" class="card" @click="$router.push('/wishes/'+w.id)">
      <h3>{{ w.title }}</h3>
      <p>{{ w.note }} <span class="tag">v{{ w.note_rev }}</span></p>
      <span class="tag">{{ w.status }} · 到期 {{ w.expires_at }}</span>
      <div v-if="w.awaiting_ack" style="margin-top:8px" @click.stop>
        <span class="tag" style="color:#a33">附言待确认 · r{{ w.pending_rev }}</span><br />
        <button style="margin-top:6px" @click="ack(w)">确认新版</button>
      </div>
    </article>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
const name = ref('访客')
const rows = ref([])
async function load() { rows.value = await api('/mine?claimer=' + encodeURIComponent(name.value)) }
async function ack(w) {
  try {
    await api('/wishes/' + w.id + '/ack', { method: 'POST', body: JSON.stringify({ claimer: name.value }) })
    await load()
  } catch (e) { alert(e.message) }
}
onMounted(load)
</script>
