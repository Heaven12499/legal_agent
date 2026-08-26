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
  const res = await fetch(`${BASE}/chat/sessions/${encodeURIComponent(sessionId)}/revise-docx`, {
    method: "POST",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || res.statusText);
  }
  return res.blob();
}

// 上传合同：multipart，不能带 JSON Content-Type
export function uploadFile(file) {
  const fd = new FormData();
  fd.append("file", file);
  return fetch(`${BASE}/upload`, { method: "POST", body: fd })
    .then(async (res) => {
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || res.statusText);
      return data;
    });
}
