import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import type { Project } from '../model/project'
import { ProjectProvider, useStore } from '../model/store'
import { CATALOG, project } from '../model/testData'
import { Checks } from './Checks'
import type { CheckReport, Finding } from './types'

afterEach(() => vi.unstubAllGlobals())

const HIGH: Finding = {
  id: 'LDO_ST_TLS',
  resource: 'st1',
  severity: 'high',
  source: 'conftest',
  message: 'storage must require TLS 1.2',
  waivable: false,
}
const MEDIUM: Finding = { ...HIGH, id: 'LDO_ST_PUBLIC', severity: 'medium', waivable: true }

// The fake API answers like the real one: a waiver in the posted project moves its finding.
function report(p: Project, findings: Finding[]): CheckReport {
  const waived = findings.flatMap((finding) => {
    const waiver = (p.waivers ?? []).find(
      (w) => w.findingId === finding.id && w.resource === finding.resource,
    )
    return waiver && finding.waivable ? [{ finding, waiver }] : []
  })
  return {
    findings: findings.filter((f) => !waived.some((x) => x.finding === f)),
    waived,
    ignored_waivers: [],
    unused_waivers: [],
    scanners: ['naming', 'tags', 'conftest'],
    apply_allowed: !findings.some((f) => !f.waivable),
  }
}

function stub(findings: Finding[]) {
  const checks: Project[] = []
  const saves: Project[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/catalog') return Response.json({ entries: CATALOG })
      if (url === '/api/hcl/generate') return Response.json({ hcl: '' })
      if (url === '/api/guardrails/check') {
        const posted = JSON.parse(String(init?.body)).project as Project
        checks.push(posted)
        return Response.json(report(posted, findings))
      }
      if (init?.method === 'PUT') {
        saves.push(JSON.parse(String(init.body)).project as Project)
        return Response.json({ issues: [] })
      }
      return Response.json({ project: project() })
    }),
  )
  return { checks, saves }
}

function Rename() {
  const { dispatch, project: p } = useStore()
  return (
    <button
      onClick={() => dispatch({ type: 'replace', project: { ...p, tags: { changed: 'yes' } } })}
    >
      Edit model
    </button>
  )
}

function renderChecks() {
  render(
    <ProjectProvider name="demo">
      <Checks />
      <Rename />
    </ProjectProvider>,
  )
}

test('a high finding blocks apply and cannot be waived', async () => {
  stub([HIGH, MEDIUM])
  renderChecks()
  fireEvent.click(await screen.findByRole('button', { name: 'Run checks' }))
  expect(await screen.findByRole('status')).toHaveTextContent(
    'Apply blocked: 1 high or critical finding',
  )
  const high = screen.getByRole('row', { name: /LDO_ST_TLS/ })
  expect(within(high).queryByRole('button')).toBeNull()
  expect(high).toHaveTextContent('Must be fixed')
  expect(screen.getByRole('button', { name: 'Waive LDO_ST_PUBLIC on st1' })).toBeInTheDocument()
})

test('waiving needs a reason and a name, saves the waiver and re-checks', async () => {
  const { checks, saves } = stub([MEDIUM])
  renderChecks()
  fireEvent.click(await screen.findByRole('button', { name: 'Run checks' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Waive LDO_ST_PUBLIC on st1' }))
  const dialog = screen.getByRole('dialog', { name: 'Waive LDO_ST_PUBLIC on st1' })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Waive finding' }))
  const reason = within(dialog).getByLabelText('Reason')
  expect(reason).toHaveAccessibleDescription(/write at least 10 characters/)
  expect(reason).toHaveFocus()
  fireEvent.change(reason, { target: { value: 'Public on purpose for the demo.' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Waive finding' }))
  expect(within(dialog).getByLabelText('Your name')).toHaveFocus()
  fireEvent.change(within(dialog).getByLabelText('Your name'), { target: { value: 'Sam' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Waive finding' }))

  const waived = await screen.findByRole('row', { name: /LDO_ST_PUBLIC \(medium\)/ })
  expect(waived).toHaveTextContent('Public on purpose for the demo.')
  expect(screen.getByRole('heading', { name: 'Waived findings' })).toHaveFocus()
  expect(checks.at(-1)?.waivers?.[0]).toMatchObject({ findingId: 'LDO_ST_PUBLIC', by: 'Sam' })
  await waitFor(() =>
    expect(saves.at(-1)?.waivers?.[0]?.reason).toBe('Public on purpose for the demo.'),
  )

  fireEvent.click(screen.getByRole('button', { name: 'Remove waiver for LDO_ST_PUBLIC on st1' }))
  expect(
    await screen.findByRole('button', { name: 'Waive LDO_ST_PUBLIC on st1' }),
  ).toBeInTheDocument()
  expect(checks.at(-1)?.waivers ?? []).toEqual([])
})

test('results say when the model changed after the last run', async () => {
  stub([])
  renderChecks()
  fireEvent.click(await screen.findByRole('button', { name: 'Run checks' }))
  expect(await screen.findByRole('status')).toHaveTextContent('Apply allowed')
  expect(screen.queryByText(/out of date/)).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Edit model' }))
  expect(screen.getByText('Results are out of date. Run checks again.')).toBeInTheDocument()
})

test('a failed check run is shown as an alert', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url === '/api/catalog') return Response.json({ entries: CATALOG })
      if (url === '/api/guardrails/check') return Response.json({}, { status: 500 })
      if (url === '/api/hcl/generate') return Response.json({ hcl: '' })
      return Response.json({ project: project(), issues: [] })
    }),
  )
  renderChecks()
  fireEvent.click(await screen.findByRole('button', { name: 'Run checks' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Checks did not run')
})
