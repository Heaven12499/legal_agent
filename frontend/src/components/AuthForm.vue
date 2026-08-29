<script setup>
import { ref } from "vue";
import { login, register } from "../api.js";

const emit = defineEmits(["success"]);
const mode = ref("login"); // login | register
const username = ref("");
const password = ref("");
const error = ref("");
const loading = ref(false);

function switchMode(m) {
  mode.value = m;
  error.value = "";
}

async function submit() {
  error.value = "";
  loading.value = true;
  try {
    const data = await (mode.value === "login" ? login : register)(username.value, password.value);
    emit("success", data);
  } catch (e) {
    error.value = e.message || "操作失败";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="auth-wrap">
    <form class="auth-card" @submit.prevent="submit">
      <div class="auth-brand">合同法律检索助手</div>
      <p class="auth-sub">登录以访问你的会话（会话按用户隔离，互不可见）</p>

      <div class="auth-tabs">
        <button type="button" :class="{ active: mode === 'login' }" @click="switchMode('login')">登录</button>
        <button type="button" :class="{ active: mode === 'register' }" @click="switchMode('register')">注册</button>
      </div>

      <label class="auth-field">
        <span>用户名</span>
        <input v-model="username" autocomplete="username" placeholder="2~32 字符" />
      </label>
      <label class="auth-field">
        <span>密码</span>
        <input v-model="password" type="password" autocomplete="current-password" placeholder="至少 6 位" />
      </label>

      <p v-if="error" class="auth-error">{{ error }}</p>

      <button class="auth-submit" type="submit" :disabled="loading || !username || !password">
        {{ loading ? "请稍候…" : mode === "login" ? "登 录" : "注 册" }}
      </button>
    </form>
  </div>
</template>
