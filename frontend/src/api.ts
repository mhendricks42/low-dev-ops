import type { CheckReport } from './checks/types'
import type { CatalogEntry } from './model/catalog-entry'
import type { Project } from './model/project'
import type { Account, Backend, Current } from './run/types'

export class ApiError extends Error {
  readonly status: number
  readonly line: number | null

  constructor(status: number, message: string, line: number | null = null) {
    super(message)
    this.status = status
    this.line = line
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data: unknown = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = (data as { detail?: unknown }).detail
    if (detail && typeof detail === 'object' && 'message' in detail) {
      const { message, line } = detail as { message: unknown; line?: unknown }
      throw new ApiError(response.status, String(message), typeof line === 'number' ? line : null)
    }
    throw new ApiError(response.status, `Request failed (${response.status})`)
  }
  return data as T
}

export const api = {
  catalog: () => call<{ entries: CatalogEntry[] }>('GET', '/api/catalog').then((d) => d.entries),
  getProject: (name: string) =>
    call<{ project: Project }>('GET', `/api/projects/${encodeURIComponent(name)}`).then(
      (d) => d.project,
    ),
  saveProject: (project: Project) =>
    call<{ issues: unknown[] }>('PUT', `/api/projects/${encodeURIComponent(project.meta.name)}`, {
      project,
    }),
  generate: (project: Project) =>
    call<{ hcl: string }>('POST', '/api/hcl/generate', { project }).then((d) => d.hcl),
  check: (project: Project) =>
    call<CheckReport>('POST', '/api/guardrails/check', { project, plan: null }),
  account: () => call<Account>('GET', '/api/azure/account'),
  // null when no backend is recorded for the subscription yet (404).
  backend: (subscriptionId: string) =>
    call<Backend>('GET', `/api/backends/${encodeURIComponent(subscriptionId)}`).catch(
      (e: unknown) => {
        if (e instanceof ApiError && e.status === 404) return null
        throw e
      },
    ),
  bootstrap: (subscriptionId: string, location: string) =>
    call<{ runId: string }>(
      'POST',
      `/api/backends/${encodeURIComponent(subscriptionId)}/bootstrap`,
      { location, confirmSubscriptionId: subscriptionId },
    ).then((d) => d.runId),
  currentRun: (name: string) =>
    call<Current>('GET', `/api/projects/${encodeURIComponent(name)}/runs/current`),
  plan: (name: string, subscriptionId: string) =>
    call<{ runId: string }>('POST', `/api/projects/${encodeURIComponent(name)}/runs/plan`, {
      subscriptionId,
    }).then((d) => d.runId),
  apply: (name: string, planSha256: string, confirmName: string, confirmDestroy: boolean) =>
    call<{ runId: string }>('POST', `/api/projects/${encodeURIComponent(name)}/runs/apply`, {
      planSha256,
      confirmName,
      confirmDestroy,
    }).then((d) => d.runId),
  logUrl: (runId: string) => `/api/runs/${encodeURIComponent(runId)}/log`,
  parse: (hcl: string, previous: Project) =>
    call<{ project: Project }>('POST', '/api/hcl/parse', { hcl, previous }).then((d) => d.project),
}
