<script setup>
import { computed } from "vue";
import { renderMarkdown } from "../markdown.js";
import TraceDetails from "./TraceDetails.vue";

const props = defineProps({ msg: Object });
const html = computed(() =>
  props.msg.role === "assistant" ? renderMarkdown(props.msg.content) : ""
);
</script>

<template>
  <div v-if="msg.role === 'assistant'" class="bubble assistant">
    <div v-html="html"></div>
    <TraceDetails v-if="msg.trace && msg.trace.length" :trace="msg.trace" />
  </div>
  <div v-else class="bubble user">{{ msg.content }}</div>
</template>
