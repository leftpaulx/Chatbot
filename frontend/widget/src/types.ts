export interface WidgetConfig {
  mountElement: string | HTMLElement;
  apiBaseUrl: string;
  getAccessToken: () => Promise<string>;

  brand?: string;
  brandDisplayName?: string;
  assistantName?: string;
  brandPrimaryColor?: string;

  locale?: string;
  theme?: "light" | "dark";
  compact?: boolean;
  startOpen?: boolean;

  welcomeMessage?: string;
  suggestedPrompts?: string[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "status" | "error";
  content: string;
  timestamp: Date;
  isStreaming?: boolean;
}

export interface SSEEvent {
  event: "markdown" | "text" | "error" | "done" | "thread";
  data: string;
}

export interface ThreadContext {
  thread_id: string;
  parent_message_id: number;
}

/** @deprecated Threads now handle conversation history server-side. */
export interface ChatHistoryEntry {
  role: "user" | "assistant";
  message: string;
}
