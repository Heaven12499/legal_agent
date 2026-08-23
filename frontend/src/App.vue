<script setup>
import { ref, onMounted, watch, nextTick } from "vue";
import Sidebar from "./components/Sidebar.vue";
import MessageBubble from "./components/MessageBubble.vue";
import ConfirmDialog from "./components/ConfirmDialog.vue";
import Welcome from "./components/Welcome.vue";
import { sendChat, listSessions, getHistory, removeSession } from "./api.js";

const sessionId = ref(crypto.randomUUID());
const messages = ref([]); // {role, content, trace?}
const sessions = ref([]);
const input = ref("");
const sending = ref(false);
const pendingDelete = ref(null); // 待删除的 session_id，非空则弹确认框

async function loadSessions() {
  try {
    sessions.value = (await listSessions()).sessions;
  } catch (e) {
    sessions.value = [];
  }
}

async function openSession(sid) {
  const data = await getHistory(sid);
  sessionId.value = sid;
  messages.value = data.history;
  loadSessions();
}

function askDelete(sid) {
  pendingDelete.value = sid;
}

function cancelDelete() {
  pendingDelete.value = null;
}

async function doDelete() {
  const sid = pendingDelete.value;
  pendingDelete.value = null;
  if (!sid) return;
  await removeSession(sid);
  if (sid === sessionId.value) {
    sessionId.value = crypto.randomUUID();
    messages.value = [];
  }
  loadSessions();
}

function newChat() {
  // 只开一个全新的空会话，不删当前会话（保留在侧栏可点回）
  sessionId.value = crypto.randomUUID();
  messages.value = [];
  loadSessions();
}

// 点欢迎区快捷问题：填入输入框并直接发送
function ask(q) {
  input.value = q;
  submit();
}

async function submit() {
  const text = input.value.trim();
  if (!text || sending.value) return;
  messages.value.push({ role: "user", content: text });
  input.value = "";
  sending.value = true;
  try {
    const data = await sendChat(text, sessionId.value);
    messages.value.push({ role: "assistant", content: data.answer, trace: data.trace });
    loadSessions();
  } catch (err) {
    messages.value.push({ role: "assistant", content: `请求失败：${err.message}` });
  } finally {
    sending.value = false;
  }
}

onMounted(loadSessions);

// 每次新消息加入后自动滚到对话底部，免手动滑动
async function scrollToBottom() {
  await nextTick();
  const el = document.getElementById("messages");
  if (el) el.scrollTop = el.scrollHeight;
}
watch(() => messages.value.length, scrollToBottom);
</script>

<template>
  <div class="layout">
    <Sidebar :sessions="sessions" :active-id="sessionId" @open="openSession" @new="newChat" @delete="askDelete" />

    <main>
      <div id="messages" aria-live="polite">
        <Welcome v-if="!messages.length" @ask="ask" />
        <template v-else>
          <MessageBubble v-for="(m, i) in messages" :key="i" :msg="m" />
        </template>
      </div>

      <form id="chat-form" @submit.prevent="submit">
        <textarea
          v-model="input"
          rows="2"
          placeholder="输入你的问题，例如：被裁员有没有赔偿？"
          @keydown.enter.exact.prevent="submit"
          required
        ></textarea>
        <button type="submit" id="send-btn" :disabled="sending">
          {{ sending ? "思考中…" : "发送" }}
        </button>
      </form>
      <p class="form-hint">Enter 发送 · Shift+Enter 换行 · 内容基于检索到的法条与官方案例，请以官方文本为准</p>
    </main>
  </div>

  <ConfirmDialog
    :visible="!!pendingDelete"
    message="确定删除这个会话吗？此操作不可恢复。"
    @confirm="doDelete"
    @cancel="cancelDelete"
  />
</template>
