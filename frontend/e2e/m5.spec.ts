// M5: bootstrap, plan and apply with typed confirmations. The API runs the fake az and terraform
// from backend/tests/bin (playwright.config.ts), so nothing here reaches Azure.
import AxeBuilder from '@axe-core/playwright'
import { readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { expect, test, type Locator, type Page } from '@playwright/test'

test.use({ viewport: { width: 1280, height: 1600 } })

const WCAG = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']
const API = 'http://127.0.0.1:8000'
const FIXTURE = resolve('../backend/tests/fixtures/guardrails/clean/project.json')
const tfState = () => process.env.LOWDEVOPS_FAKE_TF_STATE ?? ''

// Forget the state backend (the fake az's resources and settings.json), so bootstrap runs again.
function resetBackend() {
  const azState = process.env.LOWDEVOPS_FAKE_AZ_STATE ?? ''
  for (const entry of readdirSync(azState)) rmSync(join(azState, entry), { force: true })
  rmSync(join(process.env.LOWDEVOPS_E2E_WORKSPACE ?? '', 'settings.json'), { force: true })
}

async function expectNoViolations(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(WCAG).analyze()
  expect(
    results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(' | ')}`),
  ).toEqual([])
}

async function tabTo(page: Page, target: Locator, max = 200) {
  for (let i = 0; i < max; i++) {
    if (await target.evaluate((el) => el === document.activeElement)) return
    await page.keyboard.press('Tab')
  }
  throw new Error('not reachable with Tab')
}

// A saved project targeting the fake subscription, opened on the Run tab.
async function openRunTab(page: Page): Promise<string> {
  const name = `m5-${Date.now()}`
  const project = JSON.parse(readFileSync(FIXTURE, 'utf8')) as { meta: { name: string } }
  project.meta.name = name
  const saved = await page.request.put(`${API}/api/projects/${name}`, { data: { project } })
  expect(saved.ok()).toBe(true)
  await page.goto(`/?project=${name}`)
  await expect(page.getByRole('heading', { level: 1, name: `LowDevOps: ${name}` })).toBeVisible()
  await page.getByRole('tab', { name: 'Run' }).click()
  await expect(page.getByText(/^Signed in as sam@example.com/)).toBeVisible()
  return name
}

const runStatus = (page: Page) => page.locator('.run > [role="status"]')

async function bootstrapIfNeeded(page: Page) {
  const bootstrap = page.getByRole('button', { name: 'Bootstrap state backend' })
  const stored = page.getByText(/^State is stored in storage account/)
  await expect(bootstrap.or(stored)).toBeVisible()
  if (await stored.isVisible()) return
  await expect(bootstrap).toHaveAttribute('aria-disabled', 'true')
  await page.getByRole('checkbox', { name: /^Create the state backend in subscription/ }).check()
  await bootstrap.click()
  await expect(runStatus(page)).toHaveText('State backend ready.')
  await expect(stored).toBeVisible()
}

async function plan(page: Page, summary: string) {
  await page.getByRole('checkbox', { name: /^I confirm subscription .* for this plan$/ }).check()
  await page.getByRole('button', { name: 'Plan' }).click()
  await expect(runStatus(page)).toHaveText(`Plan ready: ${summary}.`)
  await expect(page.getByRole('region', { name: 'Run log' })).toContainText('$ terraform plan')
}

test.afterEach(() => rmSync(join(tfState(), 'destroy'), { force: true }))

test('keyboard only: bootstrap, plan, then apply once the name is typed', async ({ page }) => {
  resetBackend()
  const name = await openRunTab(page)
  await expectNoViolations(page) // before any run

  // Bootstrap with the keyboard only.
  const create = page.getByRole('checkbox', { name: /^Create the state backend in subscription/ })
  const bootstrap = page.getByRole('button', { name: 'Bootstrap state backend' })
  await expect(bootstrap).toHaveAttribute('aria-disabled', 'true')
  await tabTo(page, create)
  await page.keyboard.press('Space')
  await tabTo(page, bootstrap)
  await page.keyboard.press('Enter')
  await expect(runStatus(page)).toHaveText('State backend ready.')
  // The bootstrap controls are gone; focus moves on to the plan confirmation.
  await expect(
    page.getByRole('checkbox', { name: /^I confirm subscription .* for this plan$/ }),
  ).toBeFocused()
  await expectNoViolations(page)

  // Plan with the keyboard only.
  const confirm = page.getByRole('checkbox', { name: /^I confirm subscription .* for this plan$/ })
  await tabTo(page, confirm)
  await page.keyboard.press('Space')
  await tabTo(page, page.getByRole('button', { name: 'Plan' }))
  await page.keyboard.press('Enter')
  await expect(runStatus(page)).toHaveText('Plan ready: 5 to add, 0 to change, 0 to destroy.')
  await expect(page.getByRole('table', { name: 'Planned changes' })).toContainText(
    'module.rg1.azurerm_resource_group.this',
  )

  const apply = page.getByRole('button', { name: 'Apply' })
  await expect(apply).toHaveAttribute('aria-disabled', 'true')
  await expect(apply).toHaveAccessibleDescription('Type the project name to apply.')
  await expectNoViolations(page) // plan ready, apply unavailable
  await page.screenshot({ path: '../docs/specs/M5/run.png', fullPage: true })

  await tabTo(page, page.getByLabel(/^Type the project name to apply/))
  await page.keyboard.type(name.slice(0, -1))
  await expect(apply).toHaveAttribute('aria-disabled', 'true') // almost is not enough
  await page.keyboard.type(name.slice(-1))
  await expect(apply).toHaveAttribute('aria-disabled', 'false')
  await expectNoViolations(page)
  await tabTo(page, apply)
  await page.keyboard.press('Enter')
  await expect(runStatus(page)).toHaveText('Apply complete.')
  await expect(page.getByRole('region', { name: 'Run log' })).toContainText('Apply complete!')
  await expect(apply).toBeHidden() // the plan is used up
  await expect(page.getByRole('region', { name: 'Run log' })).toBeFocused()
  await expectNoViolations(page)
})

test('a plan that destroys needs the second confirmation too', async ({ page }) => {
  const name = await openRunTab(page)
  await bootstrapIfNeeded(page)
  writeFileSync(join(tfState(), 'destroy'), '')
  await plan(page, '4 to add, 0 to change, 2 to destroy')
  const table = page.getByRole('table', { name: 'Planned changes' })
  await expect(table.getByRole('row', { name: /resource_group/ })).toContainText('Destroy')
  await expect(table.getByRole('row', { name: /storage_account/ })).toContainText('Replace')

  await page.getByLabel(/^Type the project name to apply/).fill(name)
  const apply = page.getByRole('button', { name: 'Apply' })
  await expect(apply).toHaveAttribute('aria-disabled', 'true')
  await expect(apply).toHaveAccessibleDescription(
    'Confirm the resources this plan destroys or replaces.',
  )
  await apply.focus()
  await page.keyboard.press('Enter') // nothing happens while it is unavailable
  await expect(runStatus(page)).toHaveText('Plan ready: 4 to add, 0 to change, 2 to destroy.')
  await expectNoViolations(page)

  await page
    .getByRole('checkbox', { name: 'I understand this destroys or replaces 2 resources' })
    .check()
  await expect(apply).toHaveAttribute('aria-disabled', 'false')
  await apply.click()
  await expect(runStatus(page)).toHaveText('Apply complete.')
})

test.describe('reflow at 320 CSS pixels (WCAG 1.4.10)', () => {
  test.use({ viewport: { width: 320, height: 800 } })

  test('the Run tab with a plan does not scroll sideways', async ({ page }) => {
    await openRunTab(page)
    await bootstrapIfNeeded(page)
    await plan(page, '5 to add, 0 to change, 0 to destroy')
    // A wide font, so the check does not depend on which fonts the machine has (CI's are wider).
    await page.addStyleTag({
      content: '* { font-family: monospace !important; font-size: 17px !important; }',
    })
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow, `Run overflows by ${overflow}px`).toBeLessThanOrEqual(0)
    await expectNoViolations(page)
  })
})
