// M4: guardrail checks and waivers in the UI. The API's scanners are stubs that replay real
// recorded output (playwright.config.ts), so st1 gets the storage-is-public medium finding.
import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Locator, type Page } from '@playwright/test'

test.use({ viewport: { width: 1280, height: 1600 } })

const WCAG = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

async function expectNoViolations(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(WCAG).analyze()
  expect(
    results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(' | ')}`),
  ).toEqual([])
}

async function tabTo(page: Page, target: Locator, max = 150) {
  for (let i = 0; i < max; i++) {
    if (await target.evaluate((el) => el === document.activeElement)) return
    await page.keyboard.press('Tab')
  }
  throw new Error('not reachable with Tab')
}

async function setup(page: Page) {
  const name = `m4-${Date.now()}`
  await page.goto(`/?project=${name}`)
  await expect(page.getByRole('heading', { level: 1, name: `LowDevOps: ${name}` })).toBeVisible()
  for (const type of ['Resource group', 'Storage account']) {
    await page.getByLabel('Resource type').selectOption({ label: type })
    await page.getByRole('button', { name: 'Add resource' }).click()
  }
  await expect(page.getByRole('heading', { level: 3, name: /^st1 / })).toBeVisible()
  await expect(
    page.locator('[role="status"][aria-busy="false"]').filter({ hasText: 'All changes saved' }),
  ).toBeVisible()
}

test('keyboard only: run checks and waive a medium finding', async ({ page }) => {
  await setup(page)
  await page.evaluate(() => {
    const w = window as unknown as { pointerEvents: number }
    w.pointerEvents = 0
    for (const type of ['mousedown', 'mouseup', 'click', 'pointerdown'])
      document.addEventListener(
        type,
        (e) => (e as MouseEvent).detail > 0 && (w.pointerEvents += 1),
        true,
      )
  })

  await tabTo(page, page.getByRole('tab', { name: 'Wizard' }))
  await page.keyboard.press('End') // last tab: Run (M5)
  await page.keyboard.press('ArrowLeft') // Checks
  await expect(page.getByRole('tab', { name: 'Checks' })).toHaveAttribute('aria-selected', 'true')
  await expectNoViolations(page) // before any run
  const runButton = page.getByRole('button', { name: 'Run checks' })
  await tabTo(page, runButton)
  await page.keyboard.press('Enter')
  const status = page.getByRole('status').filter({ hasText: /^(Apply|No blocking)/ })
  await expect(status).toHaveText(
    /^No blocking findings, with \d+ findings to review\. Apply also needs a scanned plan/,
  )
  await expect(runButton).toBeFocused() // focus is not dropped to the body while it runs
  const waive = page.getByRole('button', { name: 'Waive LDO_ST_PUBLIC on st1' })
  await expect(waive).toBeVisible()
  // One row per finding: ids are unique per resource, so rows and the count agree.
  const count = Number((await status.textContent())?.match(/with (\d+) findings/)?.[1])
  const rows = page.getByRole('region', { name: 'Open findings' }).locator('tbody tr')
  await expect(rows).toHaveCount(count)
  expect(new Set(await rows.allInnerTexts()).size).toBe(count)
  await expectNoViolations(page) // findings

  await tabTo(page, waive)
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('dialog', { name: 'Waive LDO_ST_PUBLIC on st1' })
  await expect(dialog.getByLabel('Reason')).toBeFocused()
  await page.keyboard.press('Enter') // empty: errors name their field
  await expect(dialog.getByLabel('Reason')).toHaveAccessibleDescription(
    /write at least 10 characters/,
  )
  await expect(dialog.getByRole('alert')).toHaveText(/^Reason: write at least 10 characters/)
  await expectNoViolations(page) // dialog with an error
  await page.keyboard.type('Public on purpose for the demo; no data is kept in it.')
  await page.keyboard.press('Tab')
  await expect(dialog.getByLabel('Your name')).toBeFocused()
  await page.keyboard.type('Sam')
  await page.keyboard.press('Enter')

  await expect(dialog).toBeHidden()
  await expect(page.getByRole('heading', { name: 'Waived findings' })).toBeFocused()
  const row = page.getByRole('row', { name: /LDO_ST_PUBLIC \(medium\)/ })
  await expect(row).toContainText('Public on purpose for the demo')
  await expect(row).toContainText('Sam')
  await expect(waive).toHaveCount(0)
  await expect(page.getByText(/^Waived LDO_ST_PUBLIC on st1\.$/)).toBeAttached() // announced
  await expectNoViolations(page) // waived
  await page.screenshot({ path: '../docs/specs/M4/checks.png', fullPage: true })

  // The waiver is in project.json, as the PRD requires.
  const name = new URL(page.url()).searchParams.get('project') ?? ''
  await expect
    .poll(
      async () => (await (await page.request.get(`/api/projects/${name}`)).json()).project.waivers,
    )
    .toEqual([expect.objectContaining({ findingId: 'LDO_ST_PUBLIC', resource: 'st1', by: 'Sam' })])

  // Remove the waiver again, by keyboard; focus lands on the findings it rejoins.
  await tabTo(page, page.getByRole('button', { name: 'Remove waiver for LDO_ST_PUBLIC on st1' }))
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { name: 'Findings', exact: true })).toBeFocused()
  await expect(waive).toBeVisible()
  await expect(page.getByText('No waived findings.')).toBeVisible()
  expect(
    await page.evaluate(() => (window as unknown as { pointerEvents: number }).pointerEvents),
  ).toBe(0)
})

// 320 CSS px is also what a 1280 px window shows at 400% zoom.
test.describe('reflow at 320 CSS pixels (WCAG 1.4.10)', () => {
  test.use({ viewport: { width: 320, height: 800 } })

  const overflow = (page: Page) =>
    page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)

  test('the Checks tab and the waive dialog do not scroll sideways', async ({ page }) => {
    await setup(page)
    await tabTo(page, page.getByRole('tab', { name: 'Wizard' }))
    await page.keyboard.press('End')
    await page.keyboard.press('ArrowLeft') // Checks, left of Run
    await tabTo(page, page.getByRole('button', { name: 'Run checks' }))
    await page.keyboard.press('Enter')
    const waive = page.getByRole('button', { name: 'Waive LDO_ST_PUBLIC on st1' })
    await expect(waive).toBeAttached()
    expect(await overflow(page), 'Checks overflows').toBeLessThanOrEqual(0)
    await expectNoViolations(page)
    await tabTo(page, waive)
    await page.keyboard.press('Enter')
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    const box = await dialog.boundingBox()
    expect(box && box.x >= 0 && box.x + box.width <= 320).toBe(true)
    expect(await overflow(page), 'dialog overflows').toBeLessThanOrEqual(0)
    await expectNoViolations(page)
  })
})
