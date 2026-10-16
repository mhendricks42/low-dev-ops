// Run tab (M5): who is signed in, the state backend, then plan and apply with typed confirmations.
// Every run streams its log from /api/runs/{id}/log; the server enforces every gate shown here.
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { api } from '../api'
import { statusText } from '../checks/status'
import { Alert, Button, Checkbox, Status, TextField } from '../design-system/components'
import { useStore } from '../model/store'
import type { Account, Backend, Change, Current, RunExit, RunKind } from './types'

const ACTION: Record<Change['action'], string> = {
  create: 'Create',
  update: 'Update',
  delete: 'Destroy',
  replace: 'Replace',
}
const LOCATION = /^[a-z0-9]{2,40}$/ // as the API checks it
const RUNNING: Record<RunKind, string> = {
  bootstrap: 'Creating the state backend…',
  plan: 'Planning…',
  apply: 'Applying…',
}

function outcome(kind: RunKind, exit: RunExit, current: Current | null): string {
  const ok = exit.status === 'succeeded'
  if (kind === 'bootstrap')
    return ok ? 'State backend ready.' : `Bootstrap failed (exit ${exit.exitCode}).`
  if (kind === 'apply') return ok ? 'Apply complete.' : `Apply failed (exit ${exit.exitCode}).`
  if (!ok) return `Plan failed (exit ${exit.exitCode}).`
  return current?.plan ? `Plan ready: ${current.plan.summary.text}.` : 'Plan finished.'
}

function useLog(runId: string | null, onExit: (exit: RunExit) => void): string[] {
  // Lines belong to a run id, so a new run starts from an empty log without a reset.
  const [log, setLog] = useState<{ runId: string | null; lines: string[] }>({
    runId: null,
    lines: [],
  })
  // The latest callback, without re-subscribing (which would replay the whole log).
  const exitRef = useRef(onExit)
  useEffect(() => {
    exitRef.current = onExit
  }, [onExit])
  useEffect(() => {
    if (!runId) return
    const source = new EventSource(api.logUrl(runId))
    source.addEventListener('line', (e) => {
      const line = JSON.parse((e as MessageEvent<string>).data) as string
      setLog((previous) =>
        previous.runId === runId
          ? { runId, lines: [...previous.lines, line] }
          : { runId, lines: [line] },
      )
    })
    source.addEventListener('exit', (e) => {
      source.close() // or EventSource reconnects and replays the log
      exitRef.current(JSON.parse((e as MessageEvent<string>).data) as RunExit)
    })
    return () => source.close()
  }, [runId])
  return log.runId === runId ? log.lines : []
}

interface Loaded {
  account: Account | null
  accountError: string | null
  backend: Backend | null
  current: Current | null
}

async function load(name: string, subscriptionId: string): Promise<Loaded> {
  const [who, state, now] = await Promise.allSettled([
    api.account(),
    api.backend(subscriptionId),
    api.currentRun(name),
  ])
  return {
    account: who.status === 'fulfilled' ? who.value : null,
    accountError: who.status === 'rejected' ? (who.reason as Error).message : null,
    backend: state.status === 'fulfilled' ? state.value : null,
    current: now.status === 'fulfilled' ? now.value : null,
  }
}

export function Run() {
  const { project, pending } = useStore()
  const name = project.meta.name
  const subscriptionId = project.subscription.id.toLowerCase()
  const [account, setAccount] = useState<Account | null>(null)
  const [accountError, setAccountError] = useState<string | null>(null)
  const [backend, setBackend] = useState<Backend | null | undefined>(undefined)
  const [current, setCurrent] = useState<Current | null>(null)
  const [active, setActive] = useState<{ id: string; kind: RunKind } | null>(null)
  const [running, setRunning] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [location, setLocation] = useState(project.subscription.location)
  const [bootstrapConfirmed, setBootstrapConfirmed] = useState(false)
  const [planConfirmed, setPlanConfirmed] = useState(false)
  const [typedName, setTypedName] = useState('')
  const [destroyConfirmed, setDestroyConfirmed] = useState(false)

  const show = useCallback((loaded: Loaded) => {
    setAccount(loaded.account)
    setAccountError(loaded.accountError)
    setBackend(loaded.backend)
    setCurrent(loaded.current)
    return loaded.current
  }, [])
  const refresh = useCallback(
    () => load(name, subscriptionId).then(show),
    [name, subscriptionId, show],
  )

  useEffect(() => {
    let cancelled = false
    void load(name, subscriptionId).then((loaded) => {
      if (cancelled) return
      const now = show(loaded)
      // Pick up a run that is still going (e.g. after a reload): its log replays from the start.
      if (now?.run?.status === 'running') {
        setActive({ id: now.run.id, kind: now.run.kind })
        setRunning(true)
        setStatus(RUNNING[now.run.kind])
      }
    })
    return () => {
      cancelled = true
    }
  }, [name, subscriptionId, show])

  const planConfirmRef = useRef<HTMLInputElement>(null)
  const logRef = useRef<HTMLDivElement>(null)
  const onExit = useCallback(
    (exit: RunExit) => {
      const kind = active?.kind ?? 'plan'
      void refresh().then((now) => {
        setRunning(false)
        setStatus(outcome(kind, exit, now))
        setTypedName('')
        setDestroyConfirmed(false)
        if (exit.status !== 'succeeded') return
        // The controls the user acted on are gone after these: move focus on, not to <body>.
        // Both targets stay mounted, so they can take focus now.
        if (kind === 'bootstrap') planConfirmRef.current?.focus()
        if (kind === 'apply') logRef.current?.focus()
      })
    },
    [active, refresh],
  )
  const lines = useLog(active?.id ?? null, onExit)
  function start(kind: RunKind, call: () => Promise<string>) {
    setError(null)
    setRunning(true)
    setStatus(RUNNING[kind])
    call()
      .then((id) => setActive({ id, kind }))
      .catch((e: unknown) => {
        setRunning(false)
        setStatus('')
        setError((e as Error).message)
      })
  }

  const subscriptionLabel = `${account?.subscriptionName ?? 'the project subscription'} (${subscriptionId})`
  const mismatch = account !== null && account.subscriptionId.toLowerCase() !== subscriptionId
  const plan = current?.plan ?? null
  const destroys = plan?.summary.destroys.length ?? 0

  const locationError = LOCATION.test(location.trim())
    ? null
    : 'Location: enter an Azure region name, such as westeurope.'
  const bootstrapBlocker = running
    ? 'Wait for the current run to finish.'
    : locationError
      ? 'Enter a valid location.'
      : !bootstrapConfirmed
        ? 'Tick the box to confirm the subscription.'
        : null
  const planBlocker = running
    ? 'Wait for the current run to finish.'
    : pending
      ? 'Wait for your changes to save.'
      : !backend
        ? 'Create the state backend first.'
        : !planConfirmed
          ? 'Tick the box to confirm the subscription.'
          : null
  const applyBlocker = !plan
    ? null
    : running
      ? 'Wait for the current run to finish.'
      : !plan.guardrails.apply_allowed
        ? `Guardrails block apply: ${statusText(plan.guardrails)}.`
        : typedName !== name
          ? 'Type the project name to apply.'
          : destroys > 0 && !destroyConfirmed
            ? 'Confirm the resources this plan destroys or replaces.'
            : null

  return (
    <section aria-labelledby="run-heading" className="run">
      <h2 id="run-heading">Plan and apply</h2>
      <p>
        Terraform runs as you, through your Azure CLI sign-in. Nothing is applied without a reviewed
        plan and your typed confirmation.
      </p>
      {error && <Alert>{error}</Alert>}
      {/* Never aria-busy: a busy live region may hold back "Planning…" (WCAG 4.1.3). */}
      <Status>{status || 'No run yet.'}</Status>

      <h3>Azure account</h3>
      {accountError ? (
        <Alert>
          Not signed in to Azure: {accountError} Run <code>az login</code> in the dev container,
          then check again.
        </Alert>
      ) : account ? (
        <p>
          Signed in as {account.user}, on subscription {account.subscriptionName} (
          {account.subscriptionId}).
        </p>
      ) : (
        <p>Checking your Azure sign-in…</p>
      )}
      <p>This project targets subscription {subscriptionId}.</p>
      {mismatch && (
        <Alert>
          The Azure CLI default is a different subscription. Runs still use the project&apos;s
          subscription, and your account needs access to it.
        </Alert>
      )}
      <div className="toolbar">
        <Button onClick={() => void refresh()}>Check again</Button>
      </div>

      <h3>State backend</h3>
      {backend === undefined ? (
        <p>Checking the state backend…</p>
      ) : backend ? (
        <p>
          State is stored in storage account {backend.storageAccount}, container {backend.container}{' '}
          (resource group {backend.resourceGroup}, {backend.location}).
        </p>
      ) : (
        <>
          <p>
            No state backend yet. One shared backend per subscription keeps every project&apos;s
            Terraform state, with versioning, soft delete and Entra-only access.
          </p>
          <TextField
            label="Location"
            hint="The Azure region for the state backend, such as westeurope."
            value={location}
            error={locationError}
            onChange={setLocation}
            required
          />
          <Checkbox
            label={`Create the state backend in subscription ${subscriptionLabel}`}
            checked={bootstrapConfirmed}
            onChange={setBootstrapConfirmed}
          />
          <Gate blocker={bootstrapBlocker} id="bootstrap-blocker">
            <Button
              variant="primary"
              aria-disabled={bootstrapBlocker !== null}
              aria-describedby={bootstrapBlocker ? 'bootstrap-blocker' : undefined}
              onClick={() => {
                if (!bootstrapBlocker)
                  start('bootstrap', () => api.bootstrap(subscriptionId, location.trim()))
              }}
            >
              Bootstrap state backend
            </Button>
          </Gate>
        </>
      )}

      <h3>Plan</h3>
      <Checkbox
        label={`I confirm subscription ${subscriptionLabel} for this plan`}
        checked={planConfirmed}
        onChange={setPlanConfirmed}
        inputRef={planConfirmRef}
      />
      <Gate blocker={planBlocker} id="plan-blocker">
        <Button
          variant="primary"
          aria-disabled={planBlocker !== null}
          aria-describedby={planBlocker ? 'plan-blocker' : undefined}
          onClick={() => {
            if (!planBlocker) start('plan', () => api.plan(name, subscriptionId))
          }}
        >
          Plan
        </Button>
      </Gate>

      {active && (
        <>
          <h3>Run log</h3>
          {/* Not live: a screen reader would read every line. The status line says how it ends. */}
          <div
            ref={logRef}
            className="run-log"
            role="region"
            aria-label="Run log"
            tabIndex={0}
            aria-live="off"
            aria-busy={running}
          >
            <pre>{lines.join('\n')}</pre>
          </div>
        </>
      )}

      {plan && (
        <>
          <h3>Plan summary</h3>
          <p>
            {plan.summary.text}. Planned <time dateTime={plan.createdAt}>{plan.createdAt}</time>.
          </p>
          {plan.summary.changes.length > 0 && (
            <div className="table-scroll" role="region" aria-label="Planned changes" tabIndex={0}>
              <table className="list-view">
                <caption className="ds-sr-only">Planned changes</caption>
                <thead>
                  <tr>
                    <th scope="col">Change</th>
                    <th scope="col">Resource address</th>
                  </tr>
                </thead>
                <tbody>
                  {plan.summary.changes.map((c) => (
                    <tr key={c.address} data-action={c.action}>
                      <td>{ACTION[c.action]}</td>
                      <th scope="row">{c.address}</th>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <h3>Guardrails on this plan</h3>
          <p>{statusText(plan.guardrails)}.</p>
          {plan.guardrails.findings.length > 0 && (
            <ul>
              {plan.guardrails.findings.map((f) => (
                <li key={`${f.id}:${f.resource}`}>
                  {f.severity[0].toUpperCase() + f.severity.slice(1)}: {f.id} on {f.resource}.{' '}
                  {f.message}
                </li>
              ))}
            </ul>
          )}

          <h3>Apply</h3>
          <TextField
            label="Type the project name to apply"
            hint={`Type ${name}`}
            value={typedName}
            onChange={setTypedName}
            required
          />
          {destroys > 0 && (
            <Checkbox
              label={`I understand this destroys or replaces ${destroys} resource${destroys === 1 ? '' : 's'}`}
              checked={destroyConfirmed}
              onChange={setDestroyConfirmed}
            />
          )}
          <Gate blocker={applyBlocker} id="apply-blocker">
            <Button
              variant="danger"
              aria-disabled={applyBlocker !== null}
              aria-describedby={applyBlocker ? 'apply-blocker' : undefined}
              onClick={() => {
                if (!applyBlocker)
                  start('apply', () =>
                    api.apply(name, plan.planSha256, typedName, destroyConfirmed),
                  )
              }}
            >
              Apply
            </Button>
          </Gate>
        </>
      )}
    </section>
  )
}

// A gated button with the reason it is unavailable, as text next to it.
function Gate({
  blocker,
  id,
  children,
}: {
  blocker: string | null
  id: string
  children: ReactNode
}) {
  return (
    <div className="toolbar">
      {children}
      {blocker && (
        <span id={id} className="ds-hint">
          {blocker}
        </span>
      )}
    </div>
  )
}
