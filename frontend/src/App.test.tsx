import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import App, { projectName } from './App'
import { CATALOG } from './model/testData'
import type { Project } from './model/project'

afterEach(() => vi.unstubAllGlobals())

function stubApi() {
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
  expect(screen.getByLabelText('Resource id')).toHaveAccessibleDescription('"rg1" is already used.')
})
