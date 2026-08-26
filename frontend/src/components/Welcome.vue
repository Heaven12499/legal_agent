<script setup>
const suggestions = [
  "被裁员有没有赔偿？",
  "试用期最长能约定多久？",
  "没签劳动合同能要两倍工资吗？",
  "离职后还能拿年终奖吗？",
];
defineEmits(["ask", "review"]);
</script>

<template>
  <div class="welcome">
    <h2 class="welcome-title">援法助手</h2>
    <p class="welcome-sub">检索增强 · 法律问答 + 合同审查</p>
    <button class="review-entry" @click="$emit('review')">
      审查合同 · 粘贴采购/买卖合同，识别风险条款并附法条依据
    </button>
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
