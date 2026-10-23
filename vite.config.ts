import { resolve } from "node:path";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const siteUrl = process.env.SITE_URL || loadEnv(mode, process.cwd(), "").SITE_URL;
  let origin: string | undefined;
  if (siteUrl) {
    const url = new URL(siteUrl);
    if (!["http:", "https:"].includes(url.protocol) || url.pathname !== "/" || url.search || url.hash || url.username || url.password) {
      throw new Error("SITE_URL must be an http(s) origin without a path, credentials, query, or fragment");
    }
    origin = url.origin;
  }
  return {
    plugins: [react(), {
      name: "site-metadata",
      transformIndexHtml(_html, context) {
        if (!origin) return [];
        const path = context.path.replace(/index\.html$/, "");
        const url = origin + path;
        return [
          { tag: "link", attrs: { rel: "canonical", href: url }, injectTo: "head" },
          { tag: "meta", attrs: { property: "og:url", content: url }, injectTo: "head" },
          ...(path.includes("mb4x-radio-archive") ? [{ tag: "meta", attrs: { property: "og:image", content: origin + "/og.png" }, injectTo: "head" as const }] : []),
        ];
      },
    }],
    build: {
      rollupOptions: {
        input: {
          home: resolve(process.cwd(), "index.html"),
          archive: resolve(
            process.cwd(),
            "projects/mb4x-radio-archive/index.html",
          ),
        },
      },
    },
  };
});
