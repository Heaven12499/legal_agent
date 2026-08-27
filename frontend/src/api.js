// 后端 API：VITE_API_BASE 可覆盖（默认走 Vite dev proxy /api）
// M9 鉴权：token 存 localStorage，所有请求自动带 Authorization: Bearer，401 统一清 token
const BASE = import.meta.env.VITE_API_BASE || "/api";
const TOKEN_KEY = "auth_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(t) {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function request(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401) clearToken(); // 未登录 / token 失效
    const err = new Error(data.detail || res.statusText);
    err.status = res.status;
    throw err;
  }
  return data;
}

// ---- 认证 ----
export function register(username, password) {
  return request("/register", { method: "POST", body: JSON.stringify({ username, password }) });
}
export function login(username, password) {
  return request("/login", { method: "POST", body: JSON.stringify({ username, password }) });
}
export function me() {
  return request("/me");
}

export function sendChat(message, sessionId, contract) {
  return request("/chat", {
    method: "POST",
    body: JSON.stringify({ message, session_id: sessionId, ...(contract ? { contract } : {}) }),
  });
}

export function listSessions() {
  return request("/chat/sessions");
}

export function getHistory(sessionId) {
  return request(`/chat/sessions/${encodeURIComponent(sessionId)}/history`);
}

export function removeSession(sessionId) {
  return request(`/chat/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
}

// 修改重发：截断到 fromId 之前，让位给重新发送的一轮
export function truncateHistory(sessionId, fromId) {
  return request(`/chat/sessions/${encodeURIComponent(sessionId)}/truncate`, {
    method: "POST",
    body: JSON.stringify({ from_id: fromId }),
  });
}

// 重新生成：后端删掉最后一条回答，对最后一条用户问题重跑 agent
export function regenerateChat(sessionId) {
  return request(`/chat/sessions/${encodeURIComponent(sessionId)}/regenerate`, { method: "POST" });
}

// 导出修订版 Word：返回 .docx 的 Blob，由调用方触发下载
export async function exportDocx(sessionId) {
  const headers = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${BASE}/chat/sessions/${encodeURIComponent(sessionId)}/revise-docx`, {
    method: "POST",
    headers,
  });
  if (!res.ok) {
    if (res.status === 401) clearToken();
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || res.statusText);
  }
  return res.blob();
}

// 上传合同：multipart，不能带 JSON Content-Type，但仍带 Bearer
export function uploadFile(file) {
  const fd = new FormData();
  fd.append("file", file);
  const headers = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return fetch(`${BASE}/upload`, { method: "POST", body: fd, headers }).then(async (res) => {
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (res.status === 401) clearToken();
      throw new Error(data.detail || res.statusText);
    }
    return data;
  });
}
