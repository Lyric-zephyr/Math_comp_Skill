import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './tests',
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:8124', browserName: 'chromium', channel: process.platform === 'win32' ? 'msedge' : undefined, headless: true, screenshot: 'only-on-failure' },
  webServer: { command: 'python ../tests/browser_server.py', url: 'http://127.0.0.1:8124/?session=browser-test', reuseExistingServer: false, timeout: 30000 },
})
