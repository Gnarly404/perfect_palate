const { defineConfig } = require('@playwright/test');
const { randomUUID } = require('node:crypto');
const port = process.env.PORT || '5000';

module.exports = defineConfig({
  testDir: './accessibility',
  reporter: 'list',
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    browserName: 'chromium',
  },
  webServer: {
    command: 'python app.py',
    url: `http://127.0.0.1:${port}/static/js/csrf.js`,
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
    env: {
      FLASK_DEBUG: 'false',
      PORT: port,
      SECRET_KEY: `accessibility-test-${randomUUID()}`,
      PUBLIC_BASE_URL: 'http://127.0.0.1:5000',
    },
  },
});
