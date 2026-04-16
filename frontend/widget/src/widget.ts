import type { WidgetConfig, ChatMessage, ThreadContext } from "./types";
import { streamChat } from "./stream-client";
import { renderMarkdown } from "./markdown";
import { en } from "./i18n/en";
import styles from "./styles/widget.css?inline";
import logoUrl from "../brand_assets/OpenBorder_Logo.jpeg";

let idCounter = 0;
function uid(): string {
  return `msg-${Date.now()}-${++idCounter}`;
}

const CHAT_SVG = `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>`;
const SEND_SVG = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13"/><path d="M22 2L15 22L11 13L2 9L22 2Z"/></svg>`;
const NEW_CHAT_SVG = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>`;
const MINIMIZE_SVG = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>`;
const BUBBLE_SVG = `<svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor"><path d="M14.187 8.096L15 5.25 15.813 8.096a4.5 4.5 0 003.09 3.091L21.75 12l-2.846.813a4.5 4.5 0 00-3.091 3.091L15 18.75l-.813-2.846a4.5 4.5 0 00-3.091-3.091L8.25 12l2.846-.813a4.5 4.5 0 003.091-3.091zM7.5 4.259l.413 1.445a2.5 2.5 0 001.717 1.717L11.075 7.834 9.63 8.247a2.5 2.5 0 00-1.717 1.717L7.5 11.409l-.413-1.445a2.5 2.5 0 00-1.717-1.717L3.925 7.834 5.37 7.421a2.5 2.5 0 001.717-1.717L7.5 4.259zM7.5 17.259l.413 1.445a2.5 2.5 0 001.717 1.717l1.445.413-1.445.413a2.5 2.5 0 00-1.717 1.717L7.5 24.409l-.413-1.445a2.5 2.5 0 00-1.717-1.717L3.925 20.834l1.445-.413a2.5 2.5 0 001.717-1.717L7.5 17.259z"/></svg>`;

export class Widget {
  private config: WidgetConfig;
  private shadow: ShadowRoot;
  private messages: ChatMessage[] = [];
  private isStreaming = false;
  private abortController: AbortController | null = null;

  private threadId: string | null = null;
  private parentMessageId: number | null = null;
  private isOpen: boolean;

  private root!: HTMLElement;
  private container!: HTMLElement;
  private bubbleBtn!: HTMLElement;
  private messageListEl!: HTMLElement;
  private inputEl!: HTMLTextAreaElement;
  private sendBtn!: HTMLButtonElement;
  private welcomeEl!: HTMLElement;
  private typingEl!: HTMLElement;

  constructor(config: WidgetConfig) {
    this.config = config;
    this.isOpen = config.startOpen ?? false;

    const mount =
      typeof config.mountElement === "string"
        ? document.querySelector<HTMLElement>(config.mountElement)
        : config.mountElement;
    if (!mount) throw new Error(`Mount element not found: ${config.mountElement}`);

    this.shadow = mount.attachShadow({ mode: "open" });
    this.render();
    this.bindEvents();
  }

  /* ------------------------------------------------------------------ */
  /*  Rendering                                                         */
  /* ------------------------------------------------------------------ */

  private render(): void {
    const styleEl = document.createElement("style");
    styleEl.textContent = styles;
    this.shadow.appendChild(styleEl);

    this.root = document.createElement("div");
    this.root.className = "cb-root";
    if (this.config.brandPrimaryColor) {
      this.root.style.setProperty("--cb-primary", this.config.brandPrimaryColor);
    }

    this.container = document.createElement("div");
    this.container.className = [
      "cb-container",
      this.config.compact ? "cb-compact" : "",
      this.config.theme === "dark" ? "cb-dark" : "",
      this.isOpen ? "" : "cb-hidden",
    ]
      .filter(Boolean)
      .join(" ");

    const headerLogo = `<img src="${this.escAttr(logoUrl)}" alt="OB" class="cb-header-logo">`;

    const assistantName = this.esc(this.config.assistantName || "OB Analyst");
    const brandNameForGreeting =
      this.config.brandDisplayName || this.humanizeBrand(this.config.brand) || "there";
    const welcomeTitle = this.esc(
      this.config.welcomeMessage || `Hi ${brandNameForGreeting}! How can I help you today?`,
    );

    const suggestionsHtml = this.config.suggestedPrompts?.length
      ? `<div class="cb-suggestions">${this.config.suggestedPrompts.map((p) => `<button class="cb-suggestion-chip">${this.esc(p)}</button>`).join("")}</div>`
      : "";

    this.container.innerHTML = `
      <div class="cb-header">
        ${headerLogo}
        <div class="cb-header-info">
          <span class="cb-header-name">${assistantName}</span>
          <span class="cb-header-status"><span class="cb-status-dot"></span>${en.onlineStatus}</span>
        </div>
        <button class="cb-new-chat-btn" aria-label="${en.newChat}" title="${en.newChat}">${NEW_CHAT_SVG}</button>
        <button class="cb-minimize-btn" aria-label="Minimize" title="Minimize">${MINIMIZE_SVG}</button>
      </div>
      <div class="cb-messages">
        <div class="cb-welcome">
          <div class="cb-welcome-icon">${CHAT_SVG}</div>
          <h3 class="cb-welcome-title">${welcomeTitle}</h3>
          <p class="cb-welcome-subtitle">${en.welcomeSubtitle}</p>
          ${suggestionsHtml}
        </div>
        <div class="cb-typing cb-hidden">
          <div class="cb-typing-dot"></div>
          <div class="cb-typing-dot"></div>
          <div class="cb-typing-dot"></div>
        </div>
      </div>
      <div class="cb-input">
        <textarea class="cb-input-textarea" placeholder="${en.inputPlaceholder}" rows="1"></textarea>
        <button class="cb-send-btn" aria-label="${en.send}">${SEND_SVG}</button>
      </div>
      <div class="cb-disclaimer">${en.aiDisclaimer}</div>
    `;

    this.bubbleBtn = document.createElement("button");
    this.bubbleBtn.className = `cb-bubble-btn${this.isOpen ? " cb-hidden" : ""}`;
    this.bubbleBtn.setAttribute("aria-label", "Open chat");
    this.bubbleBtn.innerHTML = BUBBLE_SVG;

    this.root.appendChild(this.container);
    this.root.appendChild(this.bubbleBtn);
    this.shadow.appendChild(this.root);

    this.messageListEl = this.shadow.querySelector(".cb-messages")!;
    this.inputEl = this.shadow.querySelector(".cb-input-textarea")!;
    this.sendBtn = this.shadow.querySelector(".cb-send-btn")!;
    this.welcomeEl = this.shadow.querySelector(".cb-welcome")!;
    this.typingEl = this.shadow.querySelector(".cb-typing")!;
  }

  /* ------------------------------------------------------------------ */
  /*  Events                                                            */
  /* ------------------------------------------------------------------ */

  private bindEvents(): void {
    this.sendBtn.addEventListener("click", () => this.handleSend());

    this.inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        this.handleSend();
      }
    });

    this.inputEl.addEventListener("input", () => this.autoGrow());

    this.shadow.querySelectorAll(".cb-suggestion-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        this.inputEl.value = chip.textContent || "";
        this.handleSend();
      });
    });

    this.shadow.querySelector(".cb-new-chat-btn")?.addEventListener("click", () => {
      this.resetConversation();
    });

    this.shadow.querySelector(".cb-minimize-btn")?.addEventListener("click", () => {
      this.toggleOpen(false);
    });

    this.bubbleBtn.addEventListener("click", () => {
      this.toggleOpen(true);
    });

    this.messageListEl.addEventListener("click", (e) => {
      const target = e.target as HTMLElement;
      const exportBtn = target.closest(".cb-table-export") as HTMLElement | null;
      if (!exportBtn) return;
      const wrap = exportBtn.closest(".cb-table-wrap");
      const table = wrap?.querySelector("table.cb-table") as HTMLTableElement | null;
      if (table) this.exportTableAsCsv(table);
    });
  }

  private exportTableAsCsv(table: HTMLTableElement): void {
    const rows: string[][] = [];
    table.querySelectorAll("tr").forEach((tr) => {
      const cells: string[] = [];
      tr.querySelectorAll("th, td").forEach((cell) => {
        cells.push((cell.textContent || "").trim());
      });
      if (cells.length) rows.push(cells);
    });

    const csv = rows
      .map((r) => r.map((c) => this.csvEscape(c)).join(","))
      .join("\r\n");

    // Prepend UTF-8 BOM so Excel opens it with proper encoding.
    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);

    const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    const a = document.createElement("a");
    a.href = url;
    a.download = `chatbot-table-${stamp}.csv`;
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  private csvEscape(value: string): string {
    if (/[",\r\n]/.test(value)) {
      return `"${value.replace(/"/g, '""')}"`;
    }
    return value;
  }

  /* ------------------------------------------------------------------ */
  /*  Chat flow                                                         */
  /* ------------------------------------------------------------------ */

  private async handleSend(): Promise<void> {
    const text = this.inputEl.value.trim();
    if (!text || this.isStreaming) return;

    this.welcomeEl.classList.add("cb-hidden");
    this.inputEl.value = "";
    this.autoGrow();

    const userMsg: ChatMessage = {
      id: uid(),
      role: "user",
      content: text,
      timestamp: new Date(),
    };
    this.addMessage(userMsg);

    await this.streamResponse(text);
  }

  private async streamResponse(prompt: string): Promise<void> {
    this.isStreaming = true;
    this.setInputEnabled(false);
    this.typingEl.classList.remove("cb-hidden");
    this.scrollToBottom();

    const assistantMsg: ChatMessage = {
      id: uid(),
      role: "assistant",
      content: "",
      timestamp: new Date(),
      isStreaming: true,
    };
    let placed = false;
    this.abortController = new AbortController();

    try {
      const token = await this.config.getAccessToken();

      for await (const evt of streamChat(
        this.config.apiBaseUrl,
        token,
        prompt,
        this.abortController.signal,
        this.config.brand,
        this.threadId,
        this.parentMessageId,
      )) {
        if (evt.event === "done") break;

        if (evt.event === "thread") {
          try {
            const ctx: ThreadContext = JSON.parse(evt.data);
            this.threadId = ctx.thread_id;
            this.parentMessageId = ctx.parent_message_id;
          } catch { /* ignore malformed thread data */ }
          continue;
        }

        if (evt.event === "error") {
          this.typingEl.classList.add("cb-hidden");
          this.addMessage({
            id: uid(),
            role: "error",
            content: evt.data,
            timestamp: new Date(),
          });
          break;
        }

        if (evt.event === "markdown") {
          this.showStatus(evt.data);
          continue;
        }

        if (evt.event === "text") {
          this.typingEl.classList.add("cb-hidden");
          if (!placed) {
            this.addMessage(assistantMsg);
            placed = true;
          }
          assistantMsg.content += evt.data;
          this.updateBubble(assistantMsg.id, assistantMsg.content);
        }
      }

      if (placed) {
        assistantMsg.isStreaming = false;
      }
    } catch (err) {
      this.typingEl.classList.add("cb-hidden");
      if ((err as Error).name !== "AbortError") {
        this.addMessage({
          id: uid(),
          role: "error",
          content: en.errorGeneric,
          timestamp: new Date(),
        });
      }
    } finally {
      this.typingEl.classList.add("cb-hidden");
      this.clearStatuses();
      this.isStreaming = false;
      this.setInputEnabled(true);
      this.abortController = null;
      this.inputEl.focus();
    }
  }

  /* ------------------------------------------------------------------ */
  /*  DOM helpers                                                       */
  /* ------------------------------------------------------------------ */

  private addMessage(msg: ChatMessage): void {
    this.messages.push(msg);
    const el = this.buildMessageEl(msg);
    this.messageListEl.insertBefore(el, this.typingEl);
    this.scrollToBottom();
  }

  private buildMessageEl(msg: ChatMessage): HTMLElement {
    const wrapper = document.createElement("div");
    wrapper.className = `cb-message cb-message--${msg.role}`;
    wrapper.dataset.messageId = msg.id;

    const bubble = document.createElement("div");
    bubble.className = "cb-bubble";

    if (msg.role === "user") {
      bubble.textContent = msg.content;
    } else if (msg.role === "error") {
      bubble.innerHTML = `${this.esc(msg.content)}<br><button class="cb-retry-btn">${en.retry}</button>`;
      bubble.querySelector(".cb-retry-btn")?.addEventListener("click", () => {
        const last = [...this.messages].reverse().find((m) => m.role === "user");
        if (last) {
          wrapper.remove();
          this.streamResponse(last.content);
        }
      });
    } else {
      bubble.innerHTML = renderMarkdown(msg.content);
    }

    wrapper.appendChild(bubble);

    if (msg.role === "assistant" || msg.role === "user") {
      const meta = document.createElement("div");
      meta.className = "cb-message-meta";

      const ts = document.createElement("span");
      ts.textContent = this.fmtTime(msg.timestamp);
      meta.appendChild(ts);

      if (msg.role === "assistant") {
        const copyBtn = document.createElement("button");
        copyBtn.className = "cb-copy-btn";
        copyBtn.textContent = en.copyMessage;
        copyBtn.addEventListener("click", async () => {
          await navigator.clipboard.writeText(msg.content);
          copyBtn.textContent = en.copied;
          setTimeout(() => {
            copyBtn.textContent = en.copyMessage;
          }, 1500);
        });
        meta.appendChild(copyBtn);
      }

      wrapper.appendChild(meta);
    }

    return wrapper;
  }

  private updateBubble(id: string, content: string): void {
    const el = this.shadow.querySelector(`[data-message-id="${id}"] .cb-bubble`);
    if (el) {
      el.innerHTML = renderMarkdown(content);
      this.scrollToBottom();
    }
  }

  private showStatus(text: string): void {
    this.clearStatuses();
    const el = document.createElement("div");
    el.className = "cb-message cb-message--status cb-status-transient";
    el.innerHTML = `<div class="cb-bubble">${this.esc(text)}</div>`;
    this.messageListEl.insertBefore(el, this.typingEl);
    this.scrollToBottom();
  }

  private clearStatuses(): void {
    this.shadow.querySelectorAll(".cb-status-transient").forEach((el) => el.remove());
  }

  private scrollToBottom(): void {
    requestAnimationFrame(() => {
      this.messageListEl.scrollTop = this.messageListEl.scrollHeight;
    });
  }

  private autoGrow(): void {
    this.inputEl.style.height = "auto";
    this.inputEl.style.height = Math.min(this.inputEl.scrollHeight, 120) + "px";
  }

  private setInputEnabled(enabled: boolean): void {
    this.inputEl.disabled = !enabled;
    this.sendBtn.disabled = !enabled;
  }

  /* ------------------------------------------------------------------ */
  /*  Utilities                                                         */
  /* ------------------------------------------------------------------ */

  private fmtTime(d: Date): string {
    return d.toLocaleTimeString(this.config.locale, {
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  private esc(text: string): string {
    const el = document.createElement("span");
    el.textContent = text;
    return el.innerHTML;
  }

  private escAttr(text: string): string {
    return text.replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  }

  private humanizeBrand(brand?: string): string {
    if (!brand) return "";
    return brand
      .replace(/[-_]+/g, " ")
      .trim()
      .replace(/\b\w/g, (char) => char.toUpperCase());
  }

  private toggleOpen(open: boolean): void {
    this.isOpen = open;
    if (open) {
      this.container.classList.remove("cb-hidden");
      this.bubbleBtn.classList.add("cb-hidden");
      requestAnimationFrame(() => {
        this.container.classList.add("cb-open");
        this.inputEl.focus();
      });
    } else {
      this.container.classList.remove("cb-open");
      this.container.classList.add("cb-hidden");
      this.bubbleBtn.classList.remove("cb-hidden");
    }
  }

  private resetConversation(): void {
    if (this.isStreaming) {
      this.abortController?.abort();
    }

    this.threadId = null;
    this.parentMessageId = null;
    this.messages = [];

    // Remove all message elements (keep welcome + typing indicator)
    this.shadow
      .querySelectorAll(".cb-message")
      .forEach((el) => el.remove());

    this.welcomeEl.classList.remove("cb-hidden");
    this.clearStatuses();
    this.typingEl.classList.add("cb-hidden");
    this.isStreaming = false;
    this.setInputEnabled(true);
    this.inputEl.value = "";
    this.autoGrow();
    this.inputEl.focus();
  }

  destroy(): void {
    this.abortController?.abort();
    this.threadId = null;
    this.parentMessageId = null;
    while (this.shadow.firstChild) {
      this.shadow.removeChild(this.shadow.firstChild);
    }
  }
}
