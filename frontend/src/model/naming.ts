// CAF names that fit each resource type's Azure limits (M4). Mirrors
// backend/app/guardrails/naming.py; both run backend/tests/fixtures/naming-cases.json.
import type { CatalogEntry } from './catalog-entry'
import type { Naming } from './project'

const SEPARATORS = '-_.'
// Function Apps share the web-site module with App Service; CAF names them func-*.
const KIND_ABBREVIATIONS: Record<string, string> = { 'avm-res-web-site|functionapp': 'func' }

type NamedEntry = Pick<CatalogEntry, 'module' | 'cafAbbreviation' | 'nameRules'>

export function abbreviation(entry: NamedEntry, kind?: string): string {
  return KIND_ABBREVIATIONS[`${entry.module}|${kind ?? ''}`] ?? entry.cafAbbreviation
}

function strip(text: string): string {
  let start = 0
  let end = text.length
  while (start < end && SEPARATORS.includes(text[start])) start += 1
  while (end > start && SEPARATORS.includes(text[end - 1])) end -= 1
  return text.slice(start, end)
}

function clean(text: string, entry: NamedEntry): string {
  const rules = entry.nameRules
  if (!rules) return text
  if (rules.lowercase) text = text.toLowerCase()
  text = text.replace(new RegExp(`[^${rules.chars}]`, 'g'), '')
  // One separator at a time, never at either end.
  text = text.replace(/[-_.]{2,}/g, (run) => run[0])
  return strip(text)
}

function render(naming: Naming, entry: NamedEntry, kind: string | undefined, workload: string) {
  const name = naming.pattern
    .replaceAll('{type}', abbreviation(entry, kind))
    .replaceAll('{workload}', workload)
    .replaceAll('{env}', naming.env)
    .replaceAll('{region}', naming.region)
  return clean(name, entry)
}

// Fill the pattern, drop characters the type does not allow, and trim {workload} first when
// the name is too long, so env and region survive.
export function cafName(entry: NamedEntry, naming: Naming, kind?: string): string {
  const name = render(naming, entry, kind, naming.workload)
  const rules = entry.nameRules
  if (!rules || name.length <= rules.max) return name
  const workload = clean(naming.workload, entry)
  const excess = name.length - rules.max
  const trimmed = render(
    naming,
    entry,
    kind,
    workload.slice(0, Math.max(workload.length - excess, 0)),
  )
  return strip(trimmed.slice(0, rules.max))
}
