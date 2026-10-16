// Response of POST /api/guardrails/check (backend/app/api/guardrails.py).
import type { Waiver } from '../model/project'

export type Severity = 'critical' | 'high' | 'medium' | 'low'

export interface Finding {
  id: string
  resource: string
  severity: Severity
  source: string
  message: string
  waivable: boolean
}

export interface CheckReport {
  findings: Finding[]
  waived: { finding: Finding; waiver: Waiver }[]
  ignored_waivers: { waiver: Waiver; reason: string }[]
  unused_waivers: Waiver[]
  scanners: string[]
  apply_allowed: boolean
}
