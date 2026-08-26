<script setup>
import { computed, ref, watch } from "vue";
import { renderMarkdown } from "../markdown.js";
import TraceDetails from "./TraceDetails.vue";

const props = defineProps({ msg: Object, editing: Boolean });
const emit = defineEmits(["edit", "edit-submit", "edit-cancel", "regenerate"]);

// 有 citation_check 卡片时，把答案末尾的"引用校验"块引用脚注去掉，避免重复
const html = computed(() => {
  if (props.msg.role !== "assistant") return "";
  let content = props.msg.content;
  if (props.msg.citation_check?.total) {
    content = content.replace(/^>\s*[✅⚠️]?\s*引用校验.*$/m, "");
  }
  return renderMarkdown(content);
});

const cc = computed(() => props.msg.citation_check || {});
const validCount = computed(() => (cc.value.valid || []).length);
const invalidList = computed(() =>
  (cc.value.invalid || []).map((c) => `《${c.raw_law}》第${c.raw_num}条`).join("、")
);

// ---- 操作：复制 / 修改 / 重新生成 ----
const copied = ref(false);
async function copyContent() {
  try {
    await navigator.clipboard.writeText(props.msg.content);
    copied.value = true;
    setTimeout(() => (copied.value = false), 1200);
  } catch {
    /* 剪贴板不可用时静默忽略 */
  }
}

// ---- 修改模式：气泡切换成可编辑 textarea ----
const editText = ref("");
watch(
  () => props.editing,
  (on) => {
    if (on) editText.value = props.msg.content;
  },
  { immediate: true }
);
function confirmEdit() {
  const t = editText.value.trim();
  if (t) emit("edit-submit", props.msg, t);
}
</script>

<template>
  <!-- AI 回答：正文 + 引用卡片 + 追踪 + 操作条 -->
  <div v-if="msg.role === 'assistant'" class="bubble assistant">
    <div v-html="html"></div>

    <!-- M6 引用校验：可折叠卡片（原生 details 天然可展开/收起） -->
    <details v-if="cc.total" class="cite-check">
      <summary>
        <span class="cite-status" :class="cc.invalid?.length ? 'warn' : 'ok'">
          {{ cc.invalid?.length ? "⚠️" : "✅" }} 引用校验 {{ validCount }}/{{ cc.total }}
        </span>
        <span class="cite-toggle">点击展开</span>
      </summary>
      <div class="cite-body">
        <p v-if="!cc.invalid?.length" class="cite-msg">所有引用均来自检索语料，条号真实存在。</p>
        <ul class="cite-list">
          <li v-for="(c, i) in cc.valid" :key="i">{{ c.law }} 第{{ c.num }}条</li>
        </ul>
        <p v-if="cc.invalid?.length" class="cite-invalid">⚠️ 未能在语料核实：{{ invalidList }}</p>
      </div>
    </details>

    <TraceDetails v-if="msg.trace && msg.trace.length" :trace="msg.trace" />

    <div class="msg-actions">
      <button type="button" class="msg-act" @click="copyContent">{{ copied ? "已复制" : "复制" }}</button>
      <button type="button" class="msg-act" @click="emit('regenerate', msg)">重新生成</button>
    </div>
  </div>

  <!-- 用户消息：展示 或 修改模式 -->
  <div v-else-if="msg.role === 'user'">
    <div v-if="!editing" class="bubble user">
      <div>{{ msg.content }}</div>
      <div class="msg-actions">
        <button type="button" class="msg-act" @click="copyContent">{{ copied ? "已复制" : "复制" }}</button>
        <button type="button" class="msg-act" @click="emit('edit', msg)">修改</button>
      </div>
    </div>
    <div v-else class="bubble user editing">
      <textarea v-model="editText" rows="3" class="edit-input" @keydown.enter.exact.prevent="confirmEdit"></textarea>
      <div class="edit-actions">
        <button type="button" class="msg-act" @click="emit('edit-cancel')">取消</button>
        <button type="button" class="msg-act primary" @click="confirmEdit">发送</button>
      </div>
    </div>
  </div>
</template>
