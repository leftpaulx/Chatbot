import { defineConfig } from "vite";
import { resolve } from "path";

export default defineConfig({
  build: {
    lib: {
      entry: resolve(__dirname, "src/index.ts"),
      name: "ChatbotWidget",
      fileName: "chatbot-widget",
      formats: ["iife", "es"],
    },
    rollupOptions: {
      output: {
        assetFileNames: "chatbot-widget.[ext]",
      },
    },
  },
});
