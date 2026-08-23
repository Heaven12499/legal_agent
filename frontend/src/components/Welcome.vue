<script setup>
const suggestions = [
  "被裁员有没有赔偿？",
  "试用期最长能约定多久？",
  "没签劳动合同能要两倍工资吗？",
  "离职后还能拿年终奖吗？",
];
defineEmits(["ask"]);
</script>

<template>
  <div class="welcome">
    <h2 class="welcome-title">援法助手</h2>
    <p class="welcome-sub">检索增强 · 依据劳动与社会保障法条文与官方案例作答</p>
    <div class="suggestions">
      <button
        v-for="q in suggestions"
        :key="q"
        class="suggest-chip"
        @click="$emit('ask', q)"
      >{{ q }}</button>
    </div>
  </div>
</template>
