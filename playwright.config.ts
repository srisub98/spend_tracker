import { defineConfig, devices } from '@playwright/test';

// Playwright boots its own Flask server against a throwaway DB so e2e never
// touches your real data. Locally, point PYTHON at the venv so Flask resolves:
//   PYTHON=.venv/bin/python npx playwright test
const PORT = Number(process.env.E2E_PORT || 5099);
const PY = process.env.PYTHON || 'python3';
const DB = 'data/e2e_test.db'; // under data/ (git-ignored); recreated each run

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: `rm -f ${DB} && ${PY} scripts/seed_test_db.py && ${PY} app.py`,
    url: `http://127.0.0.1:${PORT}/dashboard`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    env: {
      DB_PATH: DB,
      PORT: String(PORT),
      FLASK_DEBUG: '0',
      ANTHROPIC_API_KEY: '',
    },
  },
});
