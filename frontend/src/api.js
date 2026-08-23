// 后端 API：VITE_API_BASE 可覆盖（默认走 Vite dev proxy /api）
const BASE = import.meta.env.VITE_API_BASE || "/api";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

export function sendChat(message, sessionId) {
  return request("/chat", {
    method: "POST",
    body: JSON.stringify({ message, session_id: sessionId }),
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
