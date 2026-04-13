import { Widget } from "./widget";
import type { WidgetConfig } from "./types";

export type { WidgetConfig };

export const ChatbotWidget = {
  init(config: WidgetConfig): Widget {
    return new Widget(config);
  },
};

if (typeof window !== "undefined") {
  (window as unknown as Record<string, unknown>).ChatbotWidget = ChatbotWidget;
}
