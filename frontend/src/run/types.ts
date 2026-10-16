// Responses of the M5 run API (backend/app/api/{azure,backends,project_runs,runs}.py).
import type { CheckReport } from '../checks/types'

export interface Account {
  user: string
  subscriptionId: string
  subscriptionName: string
  tenantId: string
}

export interface Backend {
  resourceGroup: string
  storageAccount: string
  container: string
  location: string
}

export type RunKind = 'bootstrap' | 'plan' | 'apply'

export interface RunSummary {
  id: string
  key: string
  kind: RunKind
  status: 'running' | 'succeeded' | 'failed'
  exitCode: number | null
  startedAt: string
  finishedAt: string | null
}

export interface Change {
  address: string
  action: 'create' | 'update' | 'delete' | 'replace'
}

export interface PlanRecord {
  planSha256: string
  modelSha256: string
  subscriptionId: string
  createdAt: string
  summary: { changes: Change[]; destroys: string[]; text: string }
  guardrails: CheckReport
}

export interface Current {
  run: RunSummary | null
  plan: PlanRecord | null
}

export interface RunExit {
  exitCode: number | null
  status: RunSummary['status']
}
