// 极简 markdown -> html：先 escape 防 XSS，再按行处理（不引 marked.js）
export function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// 行内格式：**bold**、`code`
function inline(s) {
  return s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
          .replace(/`(.+?)`/g, "<code>$1</code>");
}

// 覆盖 DeepSeek 输出的常见格式：#/##/###、**bold**、- 列表、> 引用、---、换行
export function renderMarkdown(text) {
  const esc = escapeHtml(text);
  const lines = esc.split("\n");
  let html = "";
  let inList = false;

  for (const line of lines) {
    if (line.trim() === "---") { html += "<hr>"; continue; }
    if (line.trim() === "") { html += "<br>"; continue; }

    const h = line.match(/^(#{1,3})\s+(.*)/);
    if (h) {
      html += `<h${h[1].length}>${h[2]}</h${h[1].length}>`;
      continue;
    }

    const list = line.match(/^[-*]\s+(.*)/);
    if (list) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${inline(list[1])}</li>`;
      continue;
    }
    if (inList) { html += "</ul>"; inList = false; }

    const quote = line.match(/^>\s?(.*)/);
    if (quote) { html += `<blockquote>${inline(quote[1])}</blockquote>`; continue; }

    html += `<p>${inline(line)}</p>`;
  }
  if (inList) html += "</ul>";
  return html;
}
