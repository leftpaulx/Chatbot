/**
 * Lightweight Markdown-to-HTML renderer for chatbot messages.
 * Supports: bold, italic, inline code, code blocks, headers (h2-h4),
 * bullet lists (nested), numbered lists, links, and line breaks.
 */

// Decorative bullet glyphs the LLM likes to emit instead of "-" / "*".
// Covers: U+2022 •, U+2713 ✓, U+2714 ✔, U+25AA ▪, U+25B8 ▸, U+25BA ►,
// U+2043 ⁃, U+2219 ∙, U+00B7 ·, U+25CF ●, U+25E6 ◦.
const BULLET_GLYPHS = "\u2022\u2713\u2714\u25AA\u25B8\u25BA\u2043\u2219\u00B7\u25CF\u25E6";
const BULLET_GLYPH_CLASS = `[${BULLET_GLYPHS}]`;
const BULLET_INLINE_RE = new RegExp(`([^\\n\\s])(${BULLET_GLYPH_CLASS}\\s)`, "g");
const BULLET_AFTER_COLON_RE = new RegExp(`(:)(${BULLET_GLYPH_CLASS})`, "g");
const BULLET_LINE_RE = new RegExp(`^[-*${BULLET_GLYPHS}]\\s*(.+)$`);

export function renderMarkdown(text: string): string {
  // ---- Pre-process: normalise line breaks the agent sometimes omits ----
  let raw = text;
  // Break a decorative bullet off the previous word ("April—✓ Next").
  raw = raw.replace(BULLET_INLINE_RE, "$1\n$2");
  // Break a bullet that's glued to a trailing colon ("Key Insights:✓").
  raw = raw.replace(BULLET_AFTER_COLON_RE, "$1\n$2 ");
  raw = raw.replace(/([^\n\s])([\n]?)([-*] \*\*)/g, "$1\n$3");
  raw = raw.replace(/([^\n])(#{1,4} )/g, "$1\n$2");
  raw = raw.replace(/([^\n\s*])(\*\*[A-Z])/g, "$1\n$2");
  raw = raw.replace(/([^\n\s])(\d+\.\s)/g, "$1\n$2");

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
  const listStack: string[] = [];

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

    const bullet = t.match(BULLET_LINE_RE);
    if (bullet) {
      const cleaned = cleanStrayMarkers(bullet[1]);
      if (isStandaloneLabel(cleaned) && depth0(lines[i])) {
        closeList();
        out.push(`<p class="cb-sublabel">${stripTrailingColon(cleaned)}:</p>`);
        i++;
        continue;
      }
      const depth = indentDepth(lines[i]);
      ensureList("ul", depth);
      out.push(`<li>${autoStrongLabel(cleaned)}</li>`);
      i++;
      continue;
    }

    const num = t.match(/^\d+\.\s+(.+)$/);
    if (num) {
      const cleaned = cleanStrayMarkers(num[1]);
      if (isStandaloneLabel(cleaned) && depth0(lines[i])) {
        closeList();
        out.push(`<p class="cb-sublabel">${stripTrailingColon(cleaned)}:</p>`);
        i++;
        continue;
      }
      const depth = indentDepth(lines[i]);
      ensureList("ol", depth);
      out.push(`<li>${autoStrongLabel(cleaned)}</li>`);
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

  function ensureList(tag: string, depth: number) {
    while (listStack.length > depth + 1) {
      out.push(`</${listStack.pop()!}>`);
    }

    if (listStack.length === depth + 1 && listStack[listStack.length - 1] !== tag) {
      out.push(`</${listStack.pop()!}>`);
      const cls = listStack.length > 0 ? ' class="cb-nested"' : "";
      out.push(`<${tag}${cls}>`);
      listStack.push(tag);
      return;
    }

    if (listStack.length === depth + 1) return;

    if (listStack.length === 0) {
      out.push(`<${tag}>`);
      listStack.push(tag);
    }
    while (listStack.length < depth + 1) {
      out.push(`<${tag} class="cb-nested">`);
      listStack.push(tag);
    }
  }

  function closeList() {
    while (listStack.length > 0) {
      out.push(`</${listStack.pop()!}>`);
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

/**
 * Strip orphaned * / ** markers left after inline bold/italic replacement.
 * By this point matched pairs are already <strong>/<em> tags, so any
 * remaining boundary asterisks are stray.
 */
function cleanStrayMarkers(content: string): string {
  content = content.replace(/^\*{1,2}\s*/, "");
  content = content.replace(/\s*\*{1,2}$/, "");
  return content;
}

/**
 * True if the text is a short standalone label ending with a colon
 * (e.g. "Recommendation:", "Business Insight:", "**Key Takeaway**:").
 * These should break out of the surrounding list and render as a subtitle.
 */
function isStandaloneLabel(content: string): boolean {
  const stripped = content
    .replace(/<\/?strong>/g, "")
    .replace(/<\/?em>/g, "")
    .trim();
  return /^[A-Z][A-Za-z0-9]*(\s+[A-Za-z0-9]+){0,4}:\s*$/.test(stripped);
}

function stripTrailingColon(content: string): string {
  return content.replace(/:\s*$/, "");
}

function depth0(line: string): boolean {
  return indentDepth(line) === 0;
}

/**
 * Auto-bold list items that look like standalone labels / subtitles
 * (e.g. "Business Insight:", "Key Takeaway:") when the LLM omits ** markers.
 * Skips items that already contain HTML formatting.
 */
function autoStrongLabel(html: string): string {
  if (/<[a-z]/.test(html)) return html;
  const trimmed = html.trim();

  // Standalone label: 1–5 words ending with ':'
  if (/^[A-Z]\S*(\s+\S+){0,4}:\s*$/.test(trimmed)) {
    return `<strong>${trimmed}</strong>`;
  }

  // Label + description: "Key Point: longer text here…" (1–2 title-case words)
  const m = trimmed.match(/^([A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]+)?:)\s+(.+)$/);
  if (m) {
    return `<strong>${m[1]}</strong> ${m[2]}`;
  }

  return html;
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

  let html =
    '<div class="cb-table-wrap">' +
    '<div class="cb-table-toolbar">' +
    '<button type="button" class="cb-table-export" title="Export as CSV">' +
    '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>' +
    '<polyline points="7 10 12 15 17 10"/>' +
    '<line x1="12" y1="15" x2="12" y2="3"/>' +
    "</svg>" +
    "<span>Export CSV</span>" +
    "</button>" +
    "</div>" +
    '<table class="cb-table"><thead><tr>';
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
