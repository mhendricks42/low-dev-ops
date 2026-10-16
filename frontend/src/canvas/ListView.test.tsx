import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { newResource } from '../model/catalog'
import { reducer } from '../model/reducer'
import { ProjectProvider, useStore } from '../model/store'
import { CATALOG, project, RG, VNET } from '../model/testData'
import { ListView } from './ListView'

afterEach(() => vi.unstubAllGlobals())

function Refs() {
  const { project } = useStore()
  return (
    <output aria-label="vnet refs">{JSON.stringify(project.resources?.[1]?.refs ?? [])}</output>
  )
}

test('add and remove a reference from the list view', async () => {
  let p = project()
  p = reducer(p, { type: 'addResource', resource: newResource(RG, p, 'rg1') })
  p = reducer(p, { type: 'addResource', resource: newResource(VNET, p, 'vnet1') })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/catalog') return Response.json({ entries: CATALOG })
      if (url === '/api/hcl/generate') return Response.json({ hcl: '' })
      if (init?.method === 'PUT') return Response.json({ issues: [] })
      return Response.json({ project: p })
    }),
  )
  render(
    <ProjectProvider name="demo">
      <ListView />
      <Refs />
    </ProjectProvider>,
  )
  expect(await screen.findByRole('button', { name: 'Add reference to rg1' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Add reference to vnet1' }))
  const dialog = screen.getByRole('dialog', { name: 'Add a reference to vnet1' })
  expect(within(dialog).getByLabelText('Reference')).toHaveDisplayValue(
    'vnet1.parent_id ← rg1.resource_id',
  )
  fireEvent.click(within(dialog).getByRole('button', { name: 'Add reference' }))
  expect(screen.getByLabelText('vnet refs')).toHaveTextContent('"input":"parent_id","to":"rg1"')
  expect(screen.getByRole('row', { name: /vnet1/ })).toHaveTextContent('rg1')
  fireEvent.click(screen.getByRole('button', { name: 'Remove parent_id from vnet1' }))
  expect(screen.getByLabelText('vnet refs')).toHaveTextContent('[]')
})

test('focus lands on stable elements after removals and after the dialog closes', async () => {
  let p = project()
  p = reducer(p, { type: 'addResource', resource: newResource(RG, p, 'rg1') })
  p = reducer(p, { type: 'addResource', resource: newResource(VNET, p, 'vnet1') })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/catalog') return Response.json({ entries: CATALOG })
      if (url === '/api/hcl/generate') return Response.json({ hcl: '' })
      if (init?.method === 'PUT') return Response.json({ issues: [] })
      return Response.json({ project: p })
    }),
  )
  render(
    <ProjectProvider name="demo">
      <ListView />
    </ProjectProvider>,
  )
  const open = await screen.findByRole('button', { name: 'Add reference to vnet1' })
  open.focus()
  fireEvent.click(open)
  fireEvent.click(screen.getByRole('button', { name: 'Add reference' }))
  expect(open).toHaveFocus() // back to the opener

  fireEvent.click(screen.getByRole('button', { name: 'Remove parent_id from vnet1' }))
  expect(screen.getByRole('button', { name: 'Add reference to vnet1' })).toHaveFocus()

  fireEvent.click(screen.getByRole('button', { name: 'Remove vnet1' }))
  expect(screen.getByRole('heading', { name: 'Resources and references' })).toHaveFocus()
})
