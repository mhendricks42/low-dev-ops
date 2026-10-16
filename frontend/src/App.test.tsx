import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import App, { projectName } from './App'
import { CATALOG, project } from './model/testData'
import type { Project } from './model/project'

// React Flow needs real layout APIs; the canvas is covered by the Playwright tests.
vi.mock('./canvas/Canvas', () => ({ Canvas: () => null }))

afterEach(() => vi.unstubAllGlobals())

function stubApi(existing?: Partial<Project>) {
  const saved: Project[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/catalog') return Response.json({ entries: CATALOG })
      if (url === '/api/hcl/generate') return Response.json({ hcl: '' })
      if (init?.method === 'PUT') {
        saved.push((JSON.parse(String(init.body)) as { project: Project }).project)
        return Response.json({ issues: [] })
      }
      if (url === '/api/health') return Response.json({ status: 'ok' })
      if (existing) return Response.json({ project: { ...project(), ...existing } })
      return Response.json({ detail: { message: 'none' } }, { status: 404 })
    }),
  )
  return saved
}

test('project name comes from ?project= and falls back to default when invalid', () => {
  expect(projectName('?project=web-dev')).toBe('web-dev')
  expect(projectName('?project=../etc')).toBe('default')
  expect(projectName('')).toBe('default')
})

test('adding an RG then a VNet in the wizard sets the VNet parent and ref', async () => {
  const saved = stubApi()
  render(<App />)
  fireEvent.change(await screen.findByLabelText('Resource type'), {
    target: { value: 'avm-res-resources-resourcegroup' },
  })
  expect(screen.getByLabelText('Resource id')).toHaveValue('rg1')
  fireEvent.click(screen.getByRole('button', { name: 'Add resource' }))
  fireEvent.change(screen.getByLabelText('Resource type'), {
    target: { value: 'avm-res-network-virtualnetwork' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Add resource' }))
  expect(screen.getByRole('heading', { name: 'vnet1 (Virtual network)' })).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('parent_id'), { target: { value: 'rg1' } })

  await waitFor(() => {
    const vnet = saved.at(-1)?.resources?.find((r) => r.id === 'vnet1')
    expect(vnet?.parent).toBe('rg1')
    expect(vnet?.refs).toEqual([{ input: 'parent_id', to: 'rg1', output: 'resource_id' }])
  })
})

test('a duplicate id is refused with an error tied to the field', async () => {
  stubApi()
  render(<App />)
  fireEvent.change(await screen.findByLabelText('Resource type'), {
    target: { value: 'avm-res-resources-resourcegroup' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Add resource' }))
  fireEvent.change(screen.getByLabelText('Resource type'), {
    target: { value: 'avm-res-resources-resourcegroup' },
  })
  fireEvent.change(screen.getByLabelText('Resource id'), { target: { value: 'rg1' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add resource' }))
  const idField = screen.getByLabelText('Resource id')
  expect(idField).toHaveAccessibleDescription('Resource id: "rg1" is already used.')
  expect(idField).toHaveFocus()
})

test('adding without a type puts the error on the type field and announces additions', async () => {
  stubApi()
  render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: 'Add resource' }))
  const type = screen.getByLabelText('Resource type')
  expect(type).toHaveAccessibleDescription('Resource type: choose a type first.')
  expect(type).toHaveFocus()
  fireEvent.change(type, { target: { value: 'avm-res-resources-resourcegroup' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add resource' }))
  expect(screen.getByText('Added rg1 (Resource group).')).toBeInTheDocument()
})

test('hidden inputs never render; advanced ones sit under More options; custom HCL is read-only', async () => {
  stubApi({
    customHcl: [{ id: 'custom_1', hcl: 'locals {}' }],
  })
  render(<App />)
  fireEvent.change(await screen.findByLabelText('Resource type'), {
    target: { value: 'avm-res-network-virtualnetwork' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Add resource' }))
  expect(screen.queryByLabelText('enable_telemetry')).not.toBeInTheDocument()
  const more = screen.getByText('More options').closest('details')
  expect(more).toContainElement(screen.getByLabelText('subnets'))
  expect(more).not.toContainElement(screen.getByLabelText('address_space'))
  const custom = screen.getByText('Custom HCL custom_1').closest('figure')
  expect(custom).toHaveTextContent('locals {}')
  expect(custom?.querySelector('textarea, input')).toBeNull()
})

test('the header shows whether the API is reachable', async () => {
  stubApi()
  render(<App />)
  expect(await screen.findByText('API: ok')).toBeInTheDocument()
})

test('an unreachable API is reported', async () => {
  stubApi()
  const original = globalThis.fetch
  vi.stubGlobal('fetch', (url: string, init?: RequestInit) =>
    url === '/api/health' ? Promise.reject(new Error('down')) : original(url, init),
  )
  render(<App />)
  expect(await screen.findByText('API: unreachable')).toBeInTheDocument()
})
