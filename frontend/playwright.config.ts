import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { delimiter, join, resolve } from 'node:path'
import { defineConfig } from '@playwright/test'

// A throwaway workspace, so e2e runs never touch ~/lowdevops.
const workspace = mkdtempSync(join(tmpdir(), 'lowdevops-e2e-'))

export default defineConfig({
  testDir: 'e2e',
  forbidOnly: !!process.env.CI,
  use: { baseURL: 'http://127.0.0.1:5173' },
  webServer: [
    {
      command: 'uv run uvicorn app.main:app --host 127.0.0.1 --port 8000',
      cwd: '../backend',
      url: 'http://127.0.0.1:8000/api/health',
      // Guardrail scanners are stubs that replay real recorded output (backend/tests/bin), so
      // e2e needs no Conftest/Checkov/Trivy install: the UI is under test here, not the scanners.
      env: {
        LOWDEVOPS_WORKSPACE: workspace,
        PATH: `${resolve('../backend/tests/bin')}${delimiter}${process.env.PATH ?? ''}`,
        LOWDEVOPS_STUB_DIR: resolve('../backend/tests/fixtures/guardrails/waived-medium'),
      },
      reuseExistingServer: !process.env.CI,
    },
    {
      command: 'npm run dev -- --port 5173 --strictPort',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: !process.env.CI,
    },
  ],
})
