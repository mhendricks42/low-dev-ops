// M3 exit criteria (docs/ROADMAP.md §M3). Each test uses its own project.
import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Locator, type Page } from '@playwright/test'

// Tall enough that Monaco renders every line of these small files (it only draws visible lines).
test.use({ viewport: { width: 1280, height: 2400 } })

const unique = (prefix: string) => `${prefix}-${Date.now()}`
const RG = 'Resource group (foundation)'
const VNET = 'Virtual network (foundation)'
const NSG = 'Network security group (foundation)'

async function open(page: Page, name: string) {
  await page.goto(`/?project=${name}`)
  await expect(page.getByRole('heading', { level: 1, name: `LowDevOps: ${name}` })).toBeVisible()
}

async function addResource(page: Page, type: string) {
  await page.getByLabel('Resource type').selectOption({ label: type })
  await page.getByRole('button', { name: 'Add resource' }).click()
}

async function saved(page: Page) {
  await expect(page.getByRole('status').first()).toHaveText('All changes saved')
}

const editor = (page: Page) => page.locator('.monaco-editor .view-lines')

// Paste, as a user would: typed text gets Monaco's auto-indent applied line by line.
async function replaceHcl(page: Page, text: string) {
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.evaluate((t) => navigator.clipboard.writeText(t), text)
  await editor(page).click()
  await page.keyboard.press('ControlOrMeta+A')
  await page.keyboard.press('ControlOrMeta+V')
}

async function rgAndVnet(page: Page) {
  await addResource(page, RG)
  await addResource(page, VNET)
  await page.getByLabel('parent_id').selectOption('rg1')
  await saved(page)
}

test('EC1: RG + VNet from the wizard appear on the canvas (nested) and in the HCL', async ({
  page,
}) => {
  await open(page, unique('ec1'))
  await rgAndVnet(page)

  await page.getByRole('tab', { name: 'Canvas' }).click()
  const rg = page.locator('.react-flow__node[data-id="rg1"]')
  const vnet = page.locator('.react-flow__node[data-id="vnet1"]')
  await expect(vnet).toBeVisible()
  const outer = await rg.boundingBox()
  const inner = await vnet.boundingBox()
  expect(outer && inner).toBeTruthy()
  if (outer && inner) {
    expect(inner.x).toBeGreaterThanOrEqual(outer.x)
    expect(inner.y).toBeGreaterThanOrEqual(outer.y)
    expect(inner.x + inner.width).toBeLessThanOrEqual(outer.x + outer.width)
    expect(inner.y + inner.height).toBeLessThanOrEqual(outer.y + outer.height)
  }
  await expect(page.getByRole('row', { name: /vnet1/ })).toContainText('rg1')

  await page.getByRole('tab', { name: 'HCL' }).click()
  await expect(editor(page)).toContainText('module "rg1"')
  await expect(editor(page)).toContainText('module "vnet1"')
  await expect(editor(page)).toContainText('parent_id = module.rg1.resource_id')
})

test('EC2: a value changed in HCL and saved shows up in the wizard', async ({ page }) => {
  const name = unique('ec2')
  await open(page, name)
  await addResource(page, RG)
  await saved(page)
  const project = (await (await page.request.get(`/api/projects/${name}`)).json()).project
  const hcl = (await (await page.request.post('/api/hcl/generate', { data: { project } })).json())
    .hcl
  const oldName = project.resources[0].inputs.name as string

  await page.getByRole('tab', { name: 'HCL' }).click()
  await expect(editor(page)).toContainText('module "rg1"')
  await replaceHcl(page, hcl.replace(`"${oldName}"`, '"rg-renamed-in-hcl"'))
  await page.getByRole('button', { name: 'Save HCL' }).click()
  await expect(page.getByText('HCL saved and in sync with the model.')).toBeVisible()

  await page.getByRole('tab', { name: 'Wizard' }).click()
  await expect(page.getByLabel('name', { exact: true })).toHaveValue('rg-renamed-in-hcl')
})

test('EC3: saving invalid HCL shows an inline error and leaves the model unchanged', async ({
  page,
}) => {
  const name = unique('ec3')
  await open(page, name)
  await addResource(page, RG)
  await saved(page)
  const before = await (await page.request.get(`/api/projects/${name}`)).json()

  await page.getByRole('tab', { name: 'HCL' }).click()
  await expect(editor(page)).toContainText('module "rg1"')
  await replaceHcl(page, 'module "rg1" {\n  name = \n}\n')
  await page.getByRole('button', { name: 'Save HCL' }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'HCL not saved' })).toContainText(
    '(line 2)',
  )

  expect(await (await page.request.get(`/api/projects/${name}`)).json()).toEqual(before)
  await page.getByRole('tab', { name: 'Wizard' }).click()
  await expect(page.getByLabel('name', { exact: true })).toHaveValue(
    before.project.resources[0].inputs.name,
  )
})

async function chooseByKeyboard(page: Page, select: Locator, label: string) {
  await select.focus()
  for (let i = 0; i < 30; i++) {
    if ((await select.evaluate((el: HTMLSelectElement) => el.selectedOptions[0]?.text)) === label)
      return
    await page.keyboard.press('ArrowDown')
  }
  throw new Error(`option "${label}" not reachable by keyboard`)
}

test('EC4: keyboard only, create resources and add a reference', async ({ page }) => {
  await open(page, unique('ec4'))
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

  for (const type of [RG, VNET, NSG]) {
    await chooseByKeyboard(page, page.getByLabel('Resource type'), type)
    await page.getByRole('button', { name: 'Add resource' }).focus()
    await page.keyboard.press('Enter')
  }
  await saved(page)

  await page.getByRole('tab', { name: 'Wizard' }).focus()
  await page.keyboard.press('ArrowRight')
  await expect(page.getByRole('tab', { name: 'Canvas' })).toHaveAttribute('aria-selected', 'true')

  await page.getByRole('button', { name: 'Add reference to vnet1' }).focus()
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('dialog', { name: 'Add a reference to vnet1' })
  await expect(dialog).toBeVisible()
  await chooseByKeyboard(page, dialog.getByLabel('Reference'), 'vnet1.parent_id ← rg1.resource_id')
  await page.keyboard.press('Tab')
  await expect(dialog.getByRole('button', { name: 'Add reference' })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(dialog).toBeHidden()

  await expect(page.getByRole('row', { name: /vnet1/ })).toContainText(
    'parent_id ← rg1.resource_id',
  )
  await saved(page)
  await page.getByRole('tab', { name: 'Canvas' }).focus()
  await page.keyboard.press('ArrowRight')
  await expect(editor(page)).toContainText('parent_id = module.rg1.resource_id')
  expect(
    await page.evaluate(() => (window as unknown as { pointerEvents: number }).pointerEvents),
  ).toBe(0)
})

const WCAG = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

async function expectNoViolations(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(WCAG).analyze()
  expect(
    results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(' | ')}`),
  ).toEqual([])
}

test('EC5: axe-core finds no WCAG 2.2 AA violations on any page', async ({ page }) => {
  await open(page, unique('ec5'))
  await expectNoViolations(page) // empty project
  await rgAndVnet(page)
  await addResource(page, NSG)
  await saved(page)

  await expectNoViolations(page)
  await page.screenshot({ path: '../docs/specs/M3/wizard.png', fullPage: true })

  await page.getByRole('tab', { name: 'Canvas' }).click()
  await expect(page.locator('.react-flow__node[data-id="vnet1"]')).toBeVisible()
  await expectNoViolations(page)
  await page.screenshot({ path: '../docs/specs/M3/canvas.png', fullPage: true })

  await page.getByRole('button', { name: 'Add reference to vnet1' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await expectNoViolations(page)
  await page.keyboard.press('Escape')

  await page.getByRole('tab', { name: 'HCL' }).click()
  await expect(editor(page)).toContainText('module "nsg1"')
  await expect(editor(page)).not.toContainText('= null') // unset ref inputs are omitted, not null
  await expectNoViolations(page)
  await page.screenshot({ path: '../docs/specs/M3/hcl.png', fullPage: true })
})
