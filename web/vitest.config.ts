import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config.ts'

// Tests of the web app in a simulated browser (jsdom): no backend, fetch and WebSocket are faked (src/test/).
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      setupFiles: ['src/test/setup.ts'],
      // Node 25+ has a localStorage of its own (Web Storage), undefined without a file, and it hides jsdom's: the
      // pages' localStorage would be undefined. Turned off in the test workers only.
      execArgv: ['--no-experimental-webstorage'],
    },
  }),
)
