/**
 * Lightweight Markdown-to-HTML renderer for chatbot messages.
 * Supports: bold, italic, inline code, code blocks, headers (h2-h4),
 * bullet lists (nested), numbered lists, links, and line breaks.
 */

export function renderMarkdown(text: string): string {
  // ---- Pre-process: normalise line breaks the agent sometimes omits ----
  let raw = text;
  raw = raw.replace(/([^\n])•/g, "$1\n•");
  raw = raw.replace(/([^\n\s])([\n]?)([-*] \*\*)/g, "$1\n$3");
  raw = raw.replace(/([^\n])(#{1,4} )/g, "$1\n$2");
  raw = raw.replace(/([^\n\s*])(\*\*[A-Z])/g, "$1\n$2");

  const codeBlocks: string[] = [];
  let src = raw.replace(/```(\w*)\n?([\s\S]*?)```/g, (_m, _lang, code) => {
    codeBlocks.push(
      `<pre class="cb-code-block"><code>${escapeHtml(code.trim())}</code></pre>`,
    );
    return `\x00CBLK${codeBlocks.length - 1}\x00`;
  });

  src = escapeHtml(src);

  src = src.replace(/\x00CBLK(\d+)\x00/g, (_m, idx) => codeBlocks[parseInt(idx)]);

  src = src.replace(/`([^`]+)`/g, '<code class="cb-code-inline">$1</code>');
  src = src.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  src = src.replace(/(?<!\w)\*(.+?)\*(?!\w)/g, "<em>$1</em>");

  const lines = src.split("\n");
  const out: string[] = [];
  let inList = false;
  let listTag = "";
  let curDepth = 0;

  let i = 0;
  while (i < lines.length) {
    const t = lines[i].trim();

    // ---- Table detection: lines starting with | ----
    if (isTableRow(t)) {
      closeList();
      const tableLines: string[] = [];
      while (i < lines.length) {
        const row = lines[i].trim();
        if (isTableRow(row)) {
          tableLines.push(row);
          i++;
        } else if (row === "") {
          let peek = i + 1;
          while (peek < lines.length && lines[peek].trim() === "") peek++;
          if (peek < lines.length && isTableRow(lines[peek].trim())) {
            i = peek;
          } else {
            break;
          }
        } else {
          break;
        }
      }
      out.push(buildTable(tableLines));
      continue;
    }

    if (t.startsWith("### ")) {
      closeList();
      out.push(`<h4>${t.slice(4)}</h4>`);
      i++;
      continue;
    }
    if (t.startsWith("## ")) {
      closeList();
      out.push(`<h3>${t.slice(3)}</h3>`);
      i++;
      continue;
    }
    if (t.startsWith("# ")) {
      closeList();
      out.push(`<h2>${t.slice(2)}</h2>`);
      i++;
      continue;
    }

    const bullet = t.match(/^[-*•]\s*(.+)$/);
    if (bullet) {
      const depth = indentDepth(lines[i]);
      openList("ul");
      adjustDepth(depth);
      out.push(`<li>${cleanStrayMarkers(bullet[1])}</li>`);
      i++;
      continue;
    }

    const num = t.match(/^\d+\.\s+(.+)$/);
    if (num) {
      const depth = indentDepth(lines[i]);
      openList("ol");
      adjustDepth(depth);
      out.push(`<li>${cleanStrayMarkers(num[1])}</li>`);
      i++;
      continue;
    }

    closeList();

    if (t === "") {
      const last = out[out.length - 1];
      if (last && last !== '<div class="cb-spacer"></div>') {
        out.push('<div class="cb-spacer"></div>');
      }
    } else {
      out.push(`<p>${t}</p>`);
    }
    i++;
  }
  closeList();

  let html = out.join("");
  html = html.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
  );
  return html;

  function openList(tag: string) {
    if (inList && listTag !== tag) closeList();
    if (!inList) {
      out.push(`<${tag}>`);
      inList = true;
      listTag = tag;
      curDepth = 0;
    }
  }

  function adjustDepth(target: number) {
    while (curDepth < target) {
      out.push(`<${listTag} class="cb-nested">`);
      curDepth++;
    }
    while (curDepth > target) {
      out.push(`</${listTag}>`);
      curDepth--;
    }
  }

  function closeList() {
    if (inList) {
      while (curDepth > 0) {
        out.push(`</${listTag}>`);
        curDepth--;
      }
      out.push(`</${listTag}>`);
      inList = false;
      listTag = "";
    }
  }
}

/** Count leading spaces to determine nesting depth. */
function indentDepth(line: string): number {
  const spaces = line.match(/^(\s*)/)?.[1].length ?? 0;
  if (spaces >= 4) return 2;
  if (spaces >= 2) return 1;
  return 0;
}

/** Strip orphaned leading asterisks that aren't part of bold/italic pairs. */
function cleanStrayMarkers(content: string): string {
  return content.replace(/^\*(?![*\s])/, "").replace(/^\*\s/, "");
}

function isTableRow(line: string): boolean {
  return line.startsWith("|") && line.includes("|", 1);
}

function isSeparatorRow(row: string): boolean {
  return /^\|[\s:|-]+\|?\s*$/.test(row);
}

function parseTableRow(row: string): string[] {
  let s = row.trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|")) s = s.slice(0, -1);
  return s.split("|").map((cell) => cell.trim());
}

function buildTable(rows: string[]): string {
  const meaningful = rows.filter((r) => !isSeparatorRow(r));
  if (meaningful.length === 0) return "";

  const headers = parseTableRow(meaningful[0]);
  const colCount = headers.length;
  const dataRows = meaningful.slice(1);

  let html = '<div class="cb-table-wrap"><table class="cb-table"><thead><tr>';
  for (const h of headers) {
    html += `<th>${h}</th>`;
  }
  html += "</tr></thead><tbody>";

  for (const row of dataRows) {
    const cells = parseTableRow(row);
    html += "<tr>";
    for (let c = 0; c < colCount; c++) {
      html += `<td>${cells[c] ?? ""}</td>`;
    }
    html += "</tr>";
  }

  html += "</tbody></table></div>";
  return html;
}

function escapeHtml(text: string): string {
  const map: Record<string, string> = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  };
  return text.replace(/[&<>"']/g, (ch) => map[ch]);
}
