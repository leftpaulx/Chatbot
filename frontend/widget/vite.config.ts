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
    // vega-embed is loaded via dynamic import() in chart.ts. Library IIFE
    // builds can't emit multiple chunks, so inline the dynamic chunk into
    // the main bundle. Gzipped, vega-embed adds ~260 KB.
    rollupOptions: {
      output: {
        assetFileNames: "chatbot-widget.[ext]",
        inlineDynamicImports: true,
      },
    },
  },
});
