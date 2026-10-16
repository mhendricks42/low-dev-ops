import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useEffect } from 'react'
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

// #12: the live save status changes only when the outcome does, so typing pauses are silent.
let seen: string[] = []
function SaveText() {
  const { saveStatus, saving, pending, dispatch, project } = useStore()
  useEffect(() => {
    seen.push(saveStatus) // every committed value of the live text
  }, [saveStatus])
  return (
    <>
      <p data-saving={String(saving)} data-pending={String(pending)}>
        {saveStatus}
      </p>
      <button
        onClick={() =>
          dispatch({
            type: 'replace',
            project: { ...project, tags: { n: String(Number(project.tags?.n ?? 0) + 1) } },
          })
        }
      >
        Change
      </button>
    </>
  )
}

function stubPuts(results: (() => Promise<Response>)[]) {
  seen = []
  let calls = 0
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/catalog') return Response.json({ entries: CATALOG })
      if (url === '/api/hcl/generate') return Response.json({ hcl: '' })
      if (init?.method === 'PUT') return (results[calls++] ?? results.at(-1))?.()
      return Response.json({ project: project() })
    }),
  )
}

test('edits between saves never put "Saving…" in the live status text', async () => {
  let release: (() => void) | undefined
  const ok = () => Response.json({ issues: [] })
  const held = () => new Promise<Response>((r) => (release = () => r(ok())))
  stubPuts([async () => ok(), async () => ok(), held])
  render(
    <ProjectProvider name="demo">
      <SaveText />
    </ProjectProvider>,
  )
  const status = await screen.findByText('All changes saved')
  await waitFor(() => expect(status).toHaveAttribute('data-pending', 'false'))
  fireEvent.click(screen.getByRole('button', { name: 'Change' })) // first edit: saved at once
  await waitFor(() => expect(status).toHaveAttribute('data-pending', 'false'))
  fireEvent.click(screen.getByRole('button', { name: 'Change' })) // second edit: save held
  expect(status).toHaveAttribute('data-pending', 'true') // aria-busy from the edit on
  await waitFor(() => expect(release).toBeDefined())
  expect(status).toHaveAttribute('data-saving', 'true') // shown visually, not announced
  expect(status).toHaveAttribute('data-pending', 'true')
  expect(status).toHaveTextContent('All changes saved')
  release?.()
  await waitFor(() => expect(status).toHaveAttribute('data-pending', 'false'))
  expect(status).toHaveAttribute('data-saving', 'false')
  expect(seen).toEqual(['Loaded', 'All changes saved'])
})

test('a failed save reads "Not saved" until the next save succeeds', async () => {
  stubPuts([
    async () => Response.json({ issues: [] }),
    async () => {
      await new Promise((r) => setTimeout(r, 50)) // long enough for an in-flight render
      return Response.json({ detail: { message: 'disk full' } }, { status: 500 })
    },
    async () => Response.json({ issues: [] }),
  ])
  render(
    <ProjectProvider name="demo">
      <SaveText />
    </ProjectProvider>,
  )
  await screen.findByText('All changes saved')
  fireEvent.click(screen.getByRole('button', { name: 'Change' }))
  expect(await screen.findByText('Not saved')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Change' }))
  expect(await screen.findByText('All changes saved')).toBeInTheDocument()
  expect(seen).toEqual(['Loaded', 'All changes saved', 'Not saved', 'All changes saved'])
})
