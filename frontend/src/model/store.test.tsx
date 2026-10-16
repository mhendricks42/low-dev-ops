import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { ProjectProvider, useStore } from './store'
import { CATALOG, project } from './testData'

afterEach(() => vi.unstubAllGlobals())

function Probe() {
  const { project, hcl, saveStatus } = useStore()
  return <p>{`${project.meta.name}|${hcl}|${saveStatus}`}</p>
}

function stubApi(getStatus: number) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/catalog') return Response.json({ entries: CATALOG })
    if (url === '/api/hcl/generate') return Response.json({ hcl: 'HCL' })
    if (init?.method === 'PUT') return Response.json({ issues: [] })
    if (getStatus === 404)
      return Response.json({ detail: { message: 'no project' } }, { status: 404 })
    return Response.json({ project: project() })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

test('a missing project starts empty, then is saved and its HCL generated', async () => {
  const fetchMock = stubApi(404)
  render(
    <ProjectProvider name="fresh">
      <Probe />
    </ProjectProvider>,
  )
  expect(await screen.findByText('fresh|HCL|All changes saved')).toBeInTheDocument()
  const put = fetchMock.mock.calls.find(([, init]) => init?.method === 'PUT')
  expect(put?.[0]).toBe('/api/projects/fresh')
})

test('a load error is announced', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => Response.json({}, { status: 500 })),
  )
  render(
    <ProjectProvider name="x">
      <Probe />
    </ProjectProvider>,
  )
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Could not load project'))
})
