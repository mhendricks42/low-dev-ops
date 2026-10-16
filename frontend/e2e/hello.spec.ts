import { expect, test } from '@playwright/test'

test('health endpoint returns 200', async ({ request }) => {
  const response = await request.get('/api/health')
  expect(response.status()).toBe(200)
  expect(await response.json()).toEqual({ status: 'ok' })
})

test('the app loads a project from the API', async ({ page }) => {
  await page.goto(`/?project=hello-${Date.now()}`)
  await expect(page.getByRole('heading', { level: 1, name: /^LowDevOps: hello-/ })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Wizard' })).toHaveAttribute('aria-selected', 'true')
})
