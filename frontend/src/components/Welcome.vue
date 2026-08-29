<script setup>
const suggestions = [
  "违约金约定过高能申请调低吗？",
  "没签劳动合同能要两倍工资吗？",
  "试用期最长能约定多久？",
  "合同里约定「最终解释权归甲方」有效吗？",
];
defineEmits(["ask", "review"]);
</script>

<template>
  <div class="welcome">
    <h2 class="welcome-title">合同法律检索助手</h2>
    <p class="welcome-sub">可信检索 · 合同条款核查 + 法律问答</p>
    <button class="review-entry" @click="$emit('review')">
      核查合同 · 定位风险条款，检索并展示对应法条依据
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
