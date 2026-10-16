import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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

function Busy() {
  const { pending, dispatch, project } = useStore()
  return (
    <>
      <p data-pending={String(pending)}>pending</p>
      <button
        onClick={() =>
          dispatch({ type: 'replace', project: { ...project, tags: { changed: 'yes' } } })
        }
      >
        Change
      </button>
    </>
  )
}

test('a change is pending from the moment it is made until its own save succeeds', async () => {
  let release: (() => void) | undefined
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/catalog') return Response.json({ entries: CATALOG })
      if (url === '/api/hcl/generate') return Response.json({ hcl: '' })
      if (init?.method === 'PUT') {
        if (String(init.body).includes('changed')) await new Promise<void>((r) => (release = r))
        return Response.json({ issues: [] })
      }
      return Response.json({ project: project() })
    }),
  )
  render(
    <ProjectProvider name="demo">
      <Busy />
    </ProjectProvider>,
  )
  const flag = await screen.findByText('pending')
  await waitFor(() => expect(flag).toHaveAttribute('data-pending', 'false')) // initial save done
  fireEvent.click(screen.getByRole('button', { name: 'Change' }))
  expect(flag).toHaveAttribute('data-pending', 'true') // immediately, before the debounce
  await waitFor(() => expect(release).toBeDefined())
  expect(flag).toHaveAttribute('data-pending', 'true') // still, while the PUT is in flight
  release?.()
  await waitFor(() => expect(flag).toHaveAttribute('data-pending', 'false'))
})
