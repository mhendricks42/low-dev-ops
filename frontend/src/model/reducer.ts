import type { Project, Ref, Resource } from './project'

// The ref input that means "contained in": setting it also sets `parent`, drawn as nesting.
export const PARENT_INPUT = 'parent_id'

export type Action =
  | { type: 'replace'; project: Project }
  | { type: 'addResource'; resource: Resource }
  | { type: 'removeResource'; id: string }
  | { type: 'setInput'; id: string; input: string; value: unknown }
  | { type: 'setRef'; id: string; ref: Ref }
  | { type: 'removeRef'; id: string; input: string }
  | { type: 'moveNode'; id: string; x: number; y: number }

function update(p: Project, id: string, change: (r: Resource) => Resource): Project {
  return { ...p, resources: (p.resources ?? []).map((r) => (r.id === id ? change(r) : r)) }
}

function withoutRef(r: Resource, input: string): Resource {
  const refs = (r.refs ?? []).filter((ref) => ref.input !== input)
  return { ...r, refs, parent: input === PARENT_INPUT ? null : (r.parent ?? null) }
}

function withoutInput(r: Resource, input: string): Resource {
  const inputs = Object.fromEntries(Object.entries(r.inputs ?? {}).filter(([k]) => k !== input))
  return { ...r, inputs }
}

export function reducer(p: Project, action: Action): Project {
  switch (action.type) {
    case 'replace':
      return action.project
    case 'addResource':
      return { ...p, resources: [...(p.resources ?? []), action.resource] }
    case 'removeResource':
      return {
        ...p,
        resources: (p.resources ?? [])
          .filter((r) => r.id !== action.id)
          .map((r) => ({
            ...r,
            refs: (r.refs ?? []).filter((ref) => ref.to !== action.id),
            parent: r.parent === action.id ? null : (r.parent ?? null),
          })),
      }
    case 'setInput':
      return update(p, action.id, (r) => {
        const cleared = withoutInput(withoutRef(r, action.input), action.input)
        if (action.value === undefined) return cleared
        return { ...cleared, inputs: { ...cleared.inputs, [action.input]: action.value } }
      })
    case 'setRef':
      return update(p, action.id, (r) => {
        const cleared = withoutInput(withoutRef(r, action.ref.input), action.ref.input)
        const refs = [...(cleared.refs ?? []), action.ref].sort((a, b) =>
          a.input < b.input ? -1 : 1,
        )
        const parent = action.ref.input === PARENT_INPUT ? action.ref.to : cleared.parent
        return { ...cleared, refs, parent }
      })
    case 'removeRef':
      return update(p, action.id, (r) => withoutRef(r, action.input))
    case 'moveNode':
      return update(p, action.id, (r) => ({ ...r, layout: { x: action.x, y: action.y } }))
  }
}
