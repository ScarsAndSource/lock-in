import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

/** Stamps a per-build ID into dist/sw.js so every deploy gets its own cache name (old caches are purged on activate). */
function swBuildId(): Plugin {
  const buildId = (process.env.VITE_BUILD_ID || process.env.RENDER_GIT_COMMIT || process.env.VERCEL_GIT_COMMIT_SHA || '')
    .slice(0, 12) || Date.now().toString(36);
  let outDir = 'dist';
  return {
    name: 'sw-build-id',
    apply: 'build',
    configResolved(config) {
      outDir = resolve(config.root, config.build.outDir);
    },
    closeBundle() {
      const file = resolve(outDir, 'sw.js');
      if (!existsSync(file)) return;
      writeFileSync(file, readFileSync(file, 'utf8').replace(/__BUILD_ID__/g, buildId));
    },
  };
}

export default defineConfig({
  plugins: [react(), swBuildId()],
  server: {
    port: 5173,
    host: true,
  },
});
