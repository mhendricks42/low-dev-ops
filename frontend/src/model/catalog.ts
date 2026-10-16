// Pure helpers over the catalog: which control an input gets, new resources, allowed refs.
import type { CatalogEntry, InputSpec } from './catalog-entry'
import type { Project, Ref, Resource } from './project'

export type Control = 'text' | 'checkbox' | 'number' | 'json'

export function defaultOf(spec: InputSpec): unknown {
  // The generated type narrows `default` to an object; it is any JSON value.
  return (spec as { default?: unknown }).default
}

// Catalog inputs carry no type, so the control follows the default's type (M3 spec).
export function controlFor(spec: InputSpec): Control {
  if (spec.fill) return 'text'
  const d = defaultOf(spec)
  if (typeof d === 'string') return 'text'
  if (typeof d === 'boolean') return 'checkbox'
  if (typeof d === 'number') return 'number'
  return 'json'
}

export const moduleOf = (r: Resource) => r.catalogRef.split('@')[0]

export function entryFor(catalog: CatalogEntry[], r: Resource): CatalogEntry | undefined {
  return catalog.find((e) => `${e.module}@${e.version}` === r.catalogRef)
}

export function nextId(p: Project, abbreviation: string): string {
  const ids = new Set((p.resources ?? []).map((r) => r.id))
  let n = 1
  while (ids.has(`${abbreviation}${n}`)) n += 1
  return `${abbreviation}${n}`
}

// shortcut: plain pattern substitution, no CAF length/character rules; those are M4 naming.
export function suggestedName(entry: CatalogEntry, p: Project): string {
  return p.naming.pattern
    .replaceAll('{type}', entry.cafAbbreviation)
    .replaceAll('{workload}', p.naming.workload)
    .replaceAll('{env}', p.naming.env)
    .replaceAll('{region}', p.naming.region)
}

export function newResource(entry: CatalogEntry, p: Project, id: string): Resource {
  const inputs: Record<string, unknown> = {}
  const refInputs = new Set((entry.refs ?? []).map((r) => r.input))
  for (const [name, spec] of Object.entries(entry.inputs)) {
    if (refInputs.has(name)) continue // set by a reference, never by a literal
    if (spec.fill === 'name') inputs[name] = suggestedName(entry, p)
    else if (spec.fill === 'location') inputs[name] = p.subscription.location
    else if (spec.fill === 'tenant_id') inputs[name] = p.subscription.tenantId
    else if (spec.tier !== 'advanced' && defaultOf(spec) !== undefined)
      inputs[name] = defaultOf(spec)
  }
  return {
    id,
    catalogRef: `${entry.module}@${entry.version}`,
    parent: null,
    layout: null,
    refs: [],
    inputs,
  }
}

// Every (input, target, output) the catalog allows for this resource, among existing resources.
export function refOptions(p: Project, catalog: CatalogEntry[], r: Resource): Ref[] {
  const entry = entryFor(catalog, r)
  if (!entry) return []
  return (entry.refs ?? []).flatMap((allowed) =>
    (p.resources ?? [])
      .filter((target) => target.id !== r.id && moduleOf(target) === allowed.from)
      .map((target) => ({ input: allowed.input, to: target.id, output: allowed.output })),
  )
}

export function emptyProject(name: string): Project {
  return {
    schemaVersion: 1,
    meta: { name, created: new Date().toISOString(), lowdevopsVersion: '0.1.0' },
    subscription: { id: '', tenantId: '', location: 'westeurope' },
    naming: {
      workload: name,
      env: 'dev',
      region: 'weu',
      pattern: '{type}-{workload}-{env}-{region}',
    },
    tags: {},
    resources: [],
    customHcl: [],
    waivers: [],
  }
}
