import {
  vitePlugin as remix,
  cloudflareDevProxyVitePlugin as remixCloudflareDevProxy,
} from "@remix-run/dev";
import { defineConfig } from "vite";
import tsconfigPaths from "vite-tsconfig-paths";

declare module "@remix-run/cloudflare" {
  interface Future {
    v3_singleFetch: true;
  }
}

let defineData;
console.log("NODE_ENV:", process.env.NODE_ENV);

if (process.env.NODE_ENV === "production") {
  defineData = {
    "process.env.XATA_BRANCH": JSON.stringify(process.env.XATA_BRANCH),
    "process.env.XATA_API_KEY": JSON.stringify(process.env.XATA_API_KEY),
    "process.env.XATA_DATABASE_URL": JSON.stringify(
      process.env.XATA_DATABASE_URL
    ),
  };
}

export default defineConfig({
  plugins: [
    remixCloudflareDevProxy(),
    remix({
      future: {
        v3_fetcherPersist: true,
        v3_relativeSplatPath: true,
        v3_throwAbortReason: true,
        v3_singleFetch: true,
        v3_lazyRouteDiscovery: true,
      },
    }),
    tsconfigPaths(),
  ],
  define: defineData,
});
