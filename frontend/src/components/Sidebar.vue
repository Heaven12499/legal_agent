<script setup>
defineProps({ sessions: Array, activeId: String, username: String });
const emit = defineEmits(["open", "new", "delete", "logout"]);

function relTime(ts) {
  const diff = Math.max(0, Date.now() / 1000 - ts);
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  return new Date(ts * 1000).toLocaleString("zh-CN", { month: "numeric", day: "numeric" });
}
</script>

<template>
  <aside class="sidebar">
    <div class="brand">
      <span class="brand-name">合同审查助手</span>
    </div>

    <button id="new-chat-btn" type="button" @click="emit('new')">＋ 新对话</button>

    <div class="sidebar-scroll">
      <div class="sidebar-title">历史会话</div>
      <div v-if="!sessions.length" class="session-item empty">暂无历史会话</div>
      <div
        v-for="s in sessions"
        :key="s.session_id"
        class="session-item"
        :class="{ active: s.session_id === activeId }"
        @click="emit('open', s.session_id)"
      >
        <div class="session-title">{{ s.first_message || "（空会话）" }}</div>
        <div class="session-meta">{{ s.message_count }} 条 · {{ relTime(s.updated_at) }}</div>
        <button
          class="session-del"
          title="删除该会话"
          @click.stop="emit('delete', s.session_id)"
        >✕</button>
      </div>
    </div>

    <div class="sidebar-footer">
      <div class="footer-row"><span class="dot"></span> deepseek-chat</div>
      <!-- 语料统计：改 corpus/chunks.json 后请同步此处（无案例库，案例恒为 0） -->
      <div class="footer-meta">8 部法 · 1023 条 · 0 案例</div>
      <div class="footer-user">
        <span class="footer-username" :title="username">{{ username }}</span>
        <button type="button" class="logout-btn" @click="emit('logout')">退出</button>
      </div>
    </div>
  </aside>
</template>
