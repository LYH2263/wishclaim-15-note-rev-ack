<template>
  <div class="wall">
    <h1 class="serif">愿望墙</h1>
    <p class="tag">无顶栏 · 瀑布流 · 点卡片认领</p>
    <div class="masonry">
      <article v-for="w in rows" :key="w.id" class="card" @click="$router.push('/wishes/'+w.id)">
        <h3>{{ w.title || '（无标题）' }}</h3>
        <p>{{ w.note }} <span class="tag">v{{ w.note_rev }}</span></p>
        <span v-if="w.awaiting_ack" class="tag" style="color:#a33">附言待确认 · </span>
        <span class="tag">{{ w.status }} · {{ w.data_quality }}</span>
      </article>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
const rows = ref([])
onMounted(async () => { rows.value = await api('/wishes') })
</script>
