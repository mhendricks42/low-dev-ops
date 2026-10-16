import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { ProjectProvider, useStore } from '../model/store'
import { CATALOG, project } from '../model/testData'
import type { Project } from '../model/project'
import { HclView, type EditorProps } from './HclView'

afterEach(() => vi.unstubAllGlobals())

function TextEditor({ value, onChange }: EditorProps) {
  return (
    <textarea aria-label="HCL source" value={value} onChange={(e) => onChange(e.target.value)} />
  )
}

function ModelName() {
  const { project } = useStore()
  return <output aria-label="model name">{project.meta.name}</output>
}

function stub(parse: (body: { hcl: string; previous: Project }) => Response) {
  const parseCalls: { hcl: string; previous: Project }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/catalog') return Response.json({ entries: CATALOG })
      if (url === '/api/hcl/generate') return Response.json({ hcl: 'generated' })
      if (url === '/api/hcl/parse') {
        const body = JSON.parse(String(init?.body)) as { hcl: string; previous: Project }
        parseCalls.push(body)
        return parse(body)
      }
      if (init?.method === 'PUT') return Response.json({ issues: [] })
      return Response.json({ project: project() })
    }),
  )
  return parseCalls
}

function renderView() {
  render(
    <ProjectProvider name="demo">
      <ModelName />
      <HclView Editor={TextEditor} />
    </ProjectProvider>,
  )
}

test('saving edited HCL replaces the model', async () => {
  const calls = stub(() =>
    Response.json({ project: { ...project(), meta: { ...project().meta, name: 'renamed' } } }),
  )
  renderView()
  const editor = await screen.findByLabelText('HCL source')
  await waitFor(() => expect(editor).toHaveValue('generated'))
  fireEvent.change(editor, { target: { value: 'edited' } })
  expect(screen.getByText(/Unsaved HCL edits/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Save HCL' }))
  await waitFor(() => expect(screen.getByLabelText('model name')).toHaveTextContent('renamed'))
  expect(calls[0]?.hcl).toBe('edited')
  expect(calls[0]?.previous.meta.name).toBe('demo')
})

test('a parse error shows inline with its line and leaves the model and edits alone', async () => {
  stub(() => Response.json({ detail: { message: 'line 3: bad token', line: 3 } }, { status: 422 }))
  renderView()
  const editor = await screen.findByLabelText('HCL source')
  fireEvent.change(editor, { target: { value: 'broken {' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save HCL' }))
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'HCL not saved (line 3): line 3: bad token',
  )
  expect(screen.getByLabelText('model name')).toHaveTextContent('demo')
  expect(editor).toHaveValue('broken {')
})

test('discard drops edits and shows the generated HCL again', async () => {
  stub(() => Response.json({}))
  renderView()
  const editor = await screen.findByLabelText('HCL source')
  await waitFor(() => expect(editor).toHaveValue('generated'))
  fireEvent.change(editor, { target: { value: 'scratch' } })
  fireEvent.click(screen.getByRole('button', { name: 'Discard edits' }))
  expect(editor).toHaveValue('generated')
  expect(screen.getByRole('button', { name: 'Save HCL' })).toBeDisabled()
})
