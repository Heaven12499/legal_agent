<script setup>
defineProps({ trace: Array });
</script>

<template>
  <details class="trace">
    <summary>查看检索过程（{{ trace.length }} 轮）</summary>
    <div v-for="(t, i) in trace" :key="i">
      第{{ t.round }}轮检索 <code>{{ t.query }}</code> →
      {{ t.hits.length ? t.hits.join("、") : "（未命中）" }}
    </div>
  </details>
</template>
