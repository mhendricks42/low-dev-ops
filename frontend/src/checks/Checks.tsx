// Guardrail checks (M4): run them, see what blocks apply, and waive medium/low findings with a
// written reason that is stored in project.json like any other model change.
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { api } from '../api'
import { Alert, Button, Dialog, Status, TextField } from '../design-system/components'
import type { Project, Waiver } from '../model/project'
import { reducer, type Action } from '../model/reducer'
import { useStore } from '../model/store'
import { statusText } from './status'
import type { CheckReport, Finding } from './types'

const MIN_REASON = 10
const label = (s: string) => s[0].toUpperCase() + s.slice(1)

function WaiveDialog({
  finding,
  onWaive,
  onClose,
}: {
  finding: Finding
  onWaive: (waiver: Waiver) => void
  onClose: () => void
}) {
  const [reason, setReason] = useState('')
  const [by, setBy] = useState('')
  const [errors, setErrors] = useState<{ reason?: string; by?: string }>({})
  const [summary, setSummary] = useState('')
  const reasonRef = useRef<HTMLInputElement>(null)
  const byRef = useRef<HTMLInputElement>(null)

  function submit(e: FormEvent) {
    e.preventDefault()
    const next = {
      reason:
        reason.trim().length < MIN_REASON
          ? `Reason: write at least ${MIN_REASON} characters on why this is acceptable.`
          : undefined,
      by: by.trim() ? undefined : 'Your name: enter who is accepting this finding.',
    }
    setErrors(next)
    // The field may already have focus, so focusing it again says nothing: the alert does.
    setSummary([next.reason, next.by].filter(Boolean).join(' '))
    if (next.reason) return reasonRef.current?.focus()
    if (next.by) return byRef.current?.focus()
    onWaive({
      findingId: finding.id,
      resource: finding.resource,
      reason: reason.trim(),
      by: by.trim(),
      at: new Date().toISOString(),
    })
  }

  return (
    <Dialog title={`Waive ${finding.id} on ${finding.resource}`} open onClose={onClose}>
      <p>{finding.message}</p>
      <form onSubmit={submit} noValidate>
        <p role="alert" className="ds-error">
          {summary}
        </p>
        <TextField
          label="Reason (required)"
          hint={`At least ${MIN_REASON} characters. Stored in project.json and shown with the plan.`}
          value={reason}
          error={errors.reason}
          required
          inputRef={reasonRef}
          onChange={setReason}
        />
        <TextField
          label="Your name (required)"
          value={by}
          error={errors.by}
          required
          inputRef={byRef}
          onChange={setBy}
        />
        <div className="toolbar">
          <Button type="submit" variant="primary">
            Waive finding
          </Button>
          <Button onClick={onClose}>Cancel</Button>
        </div>
      </form>
    </Dialog>
  )
}

export function Checks() {
  const { project, dispatch, announce } = useStore()
  const [report, setReport] = useState<CheckReport | null>(null)
  const [checked, setChecked] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [waiving, setWaiving] = useState<Finding | null>(null)
  // Where focus goes once the next run lands: the row the user acted on is gone by then.
  const focusAfterRun = useRef<string | null>(null)

  useEffect(() => {
    if (!report || !focusAfterRun.current) return
    document.getElementById(focusAfterRun.current)?.focus()
    focusAfterRun.current = null
  }, [report])

  function run(target: Project) {
    setRunning(true)
    setError(null)
    api
      .check(target)
      .then((r) => {
        // One update, so the status text and the busy flag change together.
        setReport(r)
        setChecked(JSON.stringify(target))
        setRunning(false)
      })
      .catch((e: unknown) => {
        focusAfterRun.current = null // no result to move focus to
        setError(`Checks did not run: ${(e as Error).message}`)
        setRunning(false)
      })
  }

  // Apply the change to the model (saved like any edit) and re-check that same model.
  function change(action: Action, message: string, focusId: string) {
    dispatch(action)
    announce(message)
    focusAfterRun.current = focusId
    run(reducer(project, action))
  }

  const stale = report !== null && checked !== JSON.stringify(project)
  const waivers = report
    ? [
        ...report.ignored_waivers.map((i) => ({ waiver: i.waiver, note: i.reason })),
        ...report.unused_waivers.map((w) => ({ waiver: w, note: 'no matching finding' })),
      ]
    : []

  return (
    <section aria-labelledby="checks-heading" className="checks">
      <h2 id="checks-heading" tabIndex={-1}>
        Guardrail checks
      </h2>
      <p>
        Naming, required tags and policies run on the project. Checkov and Trivy also scan the plan
        once planning is available.
      </p>
      <div className="toolbar">
        {/* aria-disabled, not disabled: a disabled button drops focus to the page body. */}
        <Button
          variant="primary"
          aria-disabled={running}
          onClick={() => {
            if (!running) run(project)
          }}
        >
          {running ? 'Running checks…' : 'Run checks'}
        </Button>
      </div>
      {error && <Alert>{error}</Alert>}
      {/* Always present, outside the busy region, so every change is announced. */}
      <Status>
        {running ? 'Running checks…' : report ? statusText(report) : 'Checks have not run yet.'}
      </Status>
      <div aria-busy={running}>
        {stale && <p>Results are out of date. Run checks again.</p>}
        {report && (
          <>
            <h3 id="findings-heading" tabIndex={-1}>
              Findings
            </h3>
            {report.findings.length === 0 ? (
              <p>No open findings.</p>
            ) : (
              <TableScroll label="Open findings">
                <table className="list-view">
                  <caption className="ds-sr-only">Open findings, most severe first</caption>
                  <thead>
                    <tr>
                      <th scope="col">Severity</th>
                      <th scope="col">Finding</th>
                      <th scope="col">Resource</th>
                      <th scope="col">Source</th>
                      <th scope="col">Message</th>
                      <th scope="col">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.findings.map((f) => (
                      <tr key={`${f.id}:${f.resource}`} data-severity={f.severity}>
                        <td>{label(f.severity)}</td>
                        <th scope="row">{f.id}</th>
                        <td>{f.resource}</td>
                        <td>{f.source}</td>
                        <td>{f.message}</td>
                        <td>
                          {f.waivable ? (
                            <Button onClick={() => setWaiving(f)}>
                              Waive {f.id} on {f.resource}
                            </Button>
                          ) : (
                            'Must be fixed'
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableScroll>
            )}
            <h3 id="waived-heading" tabIndex={-1}>
              Waived findings
            </h3>
            {report.waived.length === 0 ? (
              <p>No waived findings.</p>
            ) : (
              <TableScroll label="Waived findings">
                <table className="list-view">
                  <caption className="ds-sr-only">Waived findings and their reasons</caption>
                  <thead>
                    <tr>
                      <th scope="col">Finding</th>
                      <th scope="col">Resource</th>
                      <th scope="col">Reason</th>
                      <th scope="col">By, date</th>
                      <th scope="col">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.waived.map(({ finding: f, waiver: w }) => (
                      <tr key={`${f.id}:${f.resource}`}>
                        <th scope="row">
                          {f.id} ({f.severity})
                        </th>
                        <td>{f.resource}</td>
                        <td>{w.reason}</td>
                        <td>
                          {w.by}, <time dateTime={w.at}>{w.at.slice(0, 10)}</time>
                        </td>
                        <td>
                          <RemoveWaiver waiver={w} onRemove={change} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableScroll>
            )}
            {waivers.length > 0 && (
              <>
                <h3>Waivers with no effect</h3>
                <ul>
                  {waivers.map(({ waiver: w, note }) => (
                    <li key={`${w.findingId}:${w.resource}`}>
                      {w.findingId} on {w.resource}: {note}.{' '}
                      <RemoveWaiver waiver={w} onRemove={change} />
                    </li>
                  ))}
                </ul>
              </>
            )}
            <p className="ds-hint">Checked: {report.scanners.join(', ')}.</p>
          </>
        )}
      </div>
      {waiving && (
        <WaiveDialog
          finding={waiving}
          onClose={() => setWaiving(null)}
          onWaive={(waiver) => {
            setWaiving(null)
            change(
              { type: 'addWaiver', waiver },
              `Waived ${waiver.findingId} on ${waiver.resource}.`,
              'waived-heading',
            )
          }}
        />
      )}
    </section>
  )
}

function RemoveWaiver({
  waiver: w,
  onRemove,
}: {
  waiver: Waiver
  onRemove: (action: Action, message: string, focusId: string) => void
}) {
  return (
    <Button
      variant="danger"
      onClick={() =>
        onRemove(
          { type: 'removeWaiver', findingId: w.findingId, resource: w.resource },
          `Removed the waiver for ${w.findingId} on ${w.resource}.`,
          'findings-heading',
        )
      }
    >
      Remove waiver for {w.findingId} on {w.resource}
    </Button>
  )
}

// Wide tables scroll inside a focusable region at narrow widths (WCAG 1.4.10 allows this for
// data tables); tabIndex lets keyboard users scroll it (axe scrollable-region-focusable).
function TableScroll({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="table-scroll" role="region" aria-label={label} tabIndex={0}>
      {children}
    </div>
  )
}
