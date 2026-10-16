import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import type { CheckReport } from '../checks/types'
import { ProjectProvider } from '../model/store'
import { CATALOG, project } from '../model/testData'
import { Run } from './Run'
import type { Change, Current } from './types'

const SUB = '00000000-0000-0000-0000-000000000000'
const SHA = 'a'.repeat(64)
const ACCOUNT = {
  user: 'sam@example.com',
  subscriptionId: SUB,
  subscriptionName: 'Sandbox',
  tenantId: 't-1',
}
const BACKEND = {
  resourceGroup: 'rg-lowdevops-state',
  storageAccount: 'stlowdevopsabc',
  container: 'tfstate',
  location: 'westeurope',
}
const ALLOWED: CheckReport = {
  findings: [],
  waived: [],
  ignored_waivers: [],
  unused_waivers: [],
  scanners: ['naming', 'tags', 'conftest', 'checkov', 'trivy'],
  plan_scanned: true,
  blocked: false,
  apply_allowed: true,
}

// A stand-in EventSource the test drives: emit() delivers one SSE event.
class FakeEventSource {
  static last: FakeEventSource | null = null
  readonly url: string
  closed = false
  private listeners: Record<string, ((e: MessageEvent<string>) => void)[]> = {}
  constructor(url: string) {
    this.url = url
    FakeEventSource.last = this
  }
  addEventListener(type: string, listener: (e: MessageEvent<string>) => void) {
    ;(this.listeners[type] ??= []).push(listener)
  }
  close() {
    this.closed = true
  }
  emit(type: string, data: unknown) {
    const event = new MessageEvent(type, { data: JSON.stringify(data) })
    act(() => this.listeners[type]?.forEach((l) => l(event)))
  }
}

interface Server {
  backend: typeof BACKEND | null
  current: Current
  posts: { url: string; body: unknown }[]
  signedIn: boolean
}

function plan(changes: Change[], guardrails: CheckReport = ALLOWED): Current['plan'] {
  const destroys = changes
    .filter((c) => c.action === 'delete' || c.action === 'replace')
    .map((c) => c.address)
  return {
    planSha256: SHA,
    modelSha256: 'b'.repeat(64),
    subscriptionId: SUB,
    createdAt: '2026-10-16T19:00:00+00:00',
    summary: { changes, destroys, text: '1 to add, 0 to change, 2 to destroy' },
    guardrails,
  }
}

function serve(server: Server) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/hcl/generate') return Response.json({ hcl: '' })
      if (init?.method === 'POST') {
        server.posts.push({ url, body: JSON.parse(String(init.body)) })
        return Response.json({ runId: `run-${server.posts.length}` }, { status: 202 })
      }
      if (url === '/api/catalog') return Response.json({ entries: CATALOG })
      if (url === '/api/hcl/generate') return Response.json({ hcl: '' })
      if (url === '/api/azure/account')
        return server.signedIn
          ? Response.json(ACCOUNT)
          : Response.json(
              { detail: { message: "Please run 'az login' to setup account." } },
              { status: 401 },
            )
      if (url.startsWith('/api/backends/'))
        return server.backend
          ? Response.json(server.backend)
          : Response.json({ detail: { message: 'no state backend' } }, { status: 404 })
      if (url.endsWith('/runs/current')) return Response.json(server.current)
      if (init?.method === 'PUT') return Response.json({ issues: [] })
      return Response.json({
        project: { ...project(), subscription: { ...project().subscription, id: SUB } },
      })
    }),
  )
}

function server(overrides: Partial<Server> = {}): Server {
  const s: Server = {
    backend: BACKEND,
    current: { run: null, plan: null },
    posts: [],
    signedIn: true,
    ...overrides,
  }
  serve(s)
  return s
}

beforeEach(() => vi.stubGlobal('EventSource', FakeEventSource))
afterEach(() => {
  vi.unstubAllGlobals()
  FakeEventSource.last = null
})

function renderRun() {
  render(
    <ProjectProvider name="demo">
      <Run />
    </ProjectProvider>,
  )
}

const status = () => screen.getAllByRole('status').find((s) => s.closest('.run'))

test('says how to sign in when the Azure CLI is logged out', async () => {
  server({ signedIn: false })
  renderRun()
  expect(await screen.findByRole('alert')).toHaveTextContent(/Not signed in to Azure.*az login/)
})

test('bootstrap needs the subscription confirmed, then streams its log', async () => {
  const s = server({ backend: null })
  renderRun()
  const button = await screen.findByRole('button', { name: 'Bootstrap state backend' })
  expect(button).toHaveAttribute('aria-disabled', 'true')
  expect(button).toHaveAccessibleDescription('Tick the box to confirm the subscription.')
  fireEvent.click(button)
  expect(s.posts).toEqual([])

  fireEvent.click(
    screen.getByRole('checkbox', {
      name: `Create the state backend in subscription Sandbox (${SUB})`,
    }),
  )
  expect(button).toHaveAttribute('aria-disabled', 'false')
  fireEvent.click(button)
  await waitFor(() =>
    expect(s.posts).toEqual([
      {
        url: `/api/backends/${SUB}/bootstrap`,
        body: { location: 'westeurope', confirmSubscriptionId: SUB },
      },
    ]),
  )
  expect(status()).toHaveTextContent('Creating the state backend…')
  await waitFor(() => expect(FakeEventSource.last?.url).toBe('/api/runs/run-1/log'))
  const source = FakeEventSource.last
  source?.emit('line', 'Creating resource group rg-lowdevops-state in westeurope…')
  expect(screen.getByRole('region', { name: 'Run log' })).toHaveTextContent(
    'Creating resource group rg-lowdevops-state',
  )
  s.backend = BACKEND
  source?.emit('exit', { exitCode: 0, status: 'succeeded' })
  await waitFor(() => expect(status()).toHaveTextContent('State backend ready.'))
  expect(source?.closed).toBe(true)
  // The bootstrap controls are gone: focus moves on to the next step, not to <body>.
  expect(
    screen.getByRole('checkbox', { name: `I confirm subscription Sandbox (${SUB}) for this plan` }),
  ).toHaveFocus()
  expect(screen.getByText(/State is stored in storage account stlowdevopsabc/)).toBeInTheDocument()
})

test('plan needs the subscription confirmed; the plan lists destroys and replaces in text', async () => {
  const s = server()
  renderRun()
  const button = await screen.findByRole('button', { name: 'Plan' })
  await waitFor(() =>
    expect(button).toHaveAccessibleDescription('Tick the box to confirm the subscription.'),
  )
  fireEvent.click(
    screen.getByRole('checkbox', { name: `I confirm subscription Sandbox (${SUB}) for this plan` }),
  )
  await waitFor(() => expect(button).toHaveAttribute('aria-disabled', 'false'))
  fireEvent.click(button)
  await waitFor(() =>
    expect(s.posts).toEqual([
      { url: '/api/projects/demo/runs/plan', body: { subscriptionId: SUB } },
    ]),
  )
  expect(status()).toHaveTextContent('Planning…')
  expect(status()).not.toHaveAttribute('aria-busy', 'true') // or "Planning…" may go unread
  await waitFor(() => expect(FakeEventSource.last?.url).toBe('/api/runs/run-1/log'))
  s.current = {
    run: null,
    plan: plan([
      { address: 'module.rg1.azurerm_resource_group.this', action: 'create' },
      { address: 'module.st1.azurerm_storage_account.this', action: 'delete' },
      { address: 'module.kv1.azurerm_key_vault.this', action: 'replace' },
    ]),
  }
  FakeEventSource.last?.emit('exit', { exitCode: 0, status: 'succeeded' })
  await waitFor(() =>
    expect(status()).toHaveTextContent('Plan ready: 1 to add, 0 to change, 2 to destroy.'),
  )
  const table = screen.getByRole('table', { name: 'Planned changes' })
  expect(within(table).getByRole('row', { name: /storage_account/ })).toHaveTextContent('Destroy')
  expect(within(table).getByRole('row', { name: /key_vault/ })).toHaveTextContent('Replace')
})

test('a failed plan says so with its exit code', async () => {
  server()
  renderRun()
  fireEvent.click(await screen.findByRole('checkbox', { name: /I confirm subscription/ }))
  const button = screen.getByRole('button', { name: 'Plan' })
  await waitFor(() => expect(button).toHaveAttribute('aria-disabled', 'false'))
  fireEvent.click(button)
  await waitFor(() => expect(FakeEventSource.last).not.toBeNull())
  FakeEventSource.last?.emit('exit', { exitCode: 1, status: 'failed' })
  await waitFor(() => expect(status()).toHaveTextContent('Plan failed (exit 1).'))
})

test('apply needs the typed name and, for destroys, a second confirmation', async () => {
  const destroying = plan([
    { address: 'module.rg1.azurerm_resource_group.this', action: 'create' },
    { address: 'module.st1.azurerm_storage_account.this', action: 'delete' },
    { address: 'module.kv1.azurerm_key_vault.this', action: 'replace' },
  ])
  const s = server({ current: { run: null, plan: destroying } })
  renderRun()
  const apply = await screen.findByRole('button', { name: 'Apply' })
  expect(apply).toHaveAttribute('aria-disabled', 'true')
  expect(apply).toHaveAccessibleDescription('Type the project name to apply.')
  fireEvent.click(apply)
  fireEvent.change(screen.getByLabelText(/^Type the project name to apply/), {
    target: { value: 'demo' },
  })
  expect(apply).toHaveAttribute('aria-disabled', 'true') // the name alone is not enough
  expect(apply).toHaveAccessibleDescription('Confirm the resources this plan destroys or replaces.')
  fireEvent.click(apply)
  expect(s.posts).toEqual([])
  fireEvent.click(
    screen.getByRole('checkbox', { name: 'I understand this destroys or replaces 2 resources' }),
  )
  expect(apply).toHaveAttribute('aria-disabled', 'false')
  fireEvent.click(apply)
  await waitFor(() =>
    expect(s.posts).toEqual([
      {
        url: '/api/projects/demo/runs/apply',
        body: { planSha256: SHA, confirmName: 'demo', confirmDestroy: true },
      },
    ]),
  )
  s.current = { run: null, plan: null }
  await waitFor(() => expect(FakeEventSource.last?.url).toBe('/api/runs/run-1/log'))
  FakeEventSource.last?.emit('exit', { exitCode: 0, status: 'succeeded' })
  await waitFor(() => expect(status()).toHaveTextContent('Apply complete.'))
  expect(screen.queryByRole('button', { name: 'Apply' })).toBeNull() // the plan is used up
  expect(screen.getByRole('region', { name: 'Run log' })).toHaveFocus()
})

test('guardrails that block keep apply unavailable, with the reason', async () => {
  const blocked: CheckReport = {
    ...ALLOWED,
    findings: [
      {
        id: 'LDO_ST_TLS',
        resource: 'st1',
        severity: 'high',
        source: 'checkov',
        message: 'storage must require TLS 1.2',
        waivable: false,
      },
    ],
    blocked: true,
    apply_allowed: false,
  }
  server({ current: { run: null, plan: plan([], blocked) } })
  renderRun()
  fireEvent.change(await screen.findByLabelText(/^Type the project name to apply/), {
    target: { value: 'demo' },
  })
  const apply = screen.getByRole('button', { name: 'Apply' })
  expect(apply).toHaveAttribute('aria-disabled', 'true')
  expect(apply).toHaveAccessibleDescription(
    'Guardrails block apply: Apply blocked: 1 high or critical finding.',
  )
  expect(screen.getByText(/High: LDO_ST_TLS on st1/)).toBeInTheDocument()
})

test('the bootstrap location must be a region name, and the field says so', async () => {
  const s = server({ backend: null })
  renderRun()
  const location = await screen.findByLabelText(/^Location/)
  fireEvent.change(location, { target: { value: 'West Europe' } })
  expect(location).toHaveAccessibleDescription(/Location: enter an Azure region name/)
  fireEvent.click(screen.getByRole('checkbox', { name: /^Create the state backend/ }))
  const button = screen.getByRole('button', { name: 'Bootstrap state backend' })
  expect(button).toHaveAttribute('aria-disabled', 'true')
  expect(button).toHaveAccessibleDescription('Enter a valid location.')
  fireEvent.click(button)
  expect(s.posts).toEqual([])
  fireEvent.change(location, { target: { value: 'northeurope' } })
  expect(button).toHaveAttribute('aria-disabled', 'false')
})
