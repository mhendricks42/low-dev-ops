import { expect, test } from '@playwright/test'

test('health endpoint returns 200', async ({ request }) => {
  const response = await request.get('/api/health')
  expect(response.status()).toBe(200)
  expect(await response.json()).toEqual({ status: 'ok' })
})

test('hello page renders with a live API', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Hello, LowDevOps' })).toBeVisible()
  await expect(page.getByRole('status')).toHaveText('API: ok')
  await page.screenshot({ path: '../docs/specs/M0/hello.png' })
})
