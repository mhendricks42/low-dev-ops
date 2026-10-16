// Model -> React Flow graph. Containment (parent) is nesting; every other ref is an edge.
import type { Edge, Node } from '@xyflow/react'
import { entryFor, refOptions } from '../model/catalog'
import type { CatalogEntry } from '../model/catalog-entry'
import type { Project, Ref } from '../model/project'
import { PARENT_INPUT } from '../model/reducer'

export interface NodeData extends Record<string, unknown> {
  label: string
}

const NODE_W = 200
const NODE_H = 60
const GAP = 40
const PAD = 20
const HEADER = 40

export function toFlow(
  p: Project,
  catalog: CatalogEntry[],
): { nodes: Node<NodeData>[]; edges: Edge[] } {
  const resources = p.resources ?? []
  const ids = new Set(resources.map((r) => r.id))
  const childrenOf = (id: string) => resources.filter((r) => r.parent === id)
  const nodes: Node<NodeData>[] = []
  let top = 0

  // React Flow needs a parent before its children, so walk top-level resources first.
  for (const r of resources.filter((r) => !r.parent || !ids.has(r.parent))) {
    const kids = childrenOf(r.id)
    const title = entryFor(catalog, r)?.title ?? r.catalogRef
    const width = kids.length ? NODE_W + 2 * PAD : NODE_W
    const height = kids.length ? HEADER + kids.length * (NODE_H + PAD) + PAD : NODE_H
    nodes.push({
      id: r.id,
      position: r.layout ? { x: r.layout.x, y: r.layout.y } : { x: GAP, y: GAP + top },
      data: { label: `${r.id} · ${title}` },
      ariaLabel: `${r.id}, ${title}${kids.length ? `, contains ${kids.map((k) => k.id).join(', ')}` : ''}`,
      style: { width, height },
      type: kids.length ? 'group' : 'default',
    })
    top += height + GAP
    kids.forEach((k, i) => {
      const kidTitle = entryFor(catalog, k)?.title ?? k.catalogRef
      nodes.push({
        id: k.id,
        parentId: r.id,
        extent: 'parent',
        position: k.layout
          ? { x: k.layout.x, y: k.layout.y }
          : { x: PAD, y: HEADER + i * (NODE_H + PAD) },
        data: { label: `${k.id} · ${kidTitle}` },
        ariaLabel: `${k.id}, ${kidTitle}, inside ${r.id}`,
        style: { width: NODE_W, height: NODE_H },
      })
    })
  }
  ;(p.customHcl ?? []).forEach((c) => {
    nodes.push({
      id: `custom:${c.id}`,
      position: { x: GAP + NODE_W + 3 * GAP, y: GAP + top },
      data: { label: `Custom HCL · ${c.id}` },
      ariaLabel: `Custom HCL ${c.id}, view only`,
      draggable: false,
      connectable: false,
      style: { width: NODE_W, height: NODE_H },
    })
    top += NODE_H + GAP
  })

  const edges: Edge[] = resources.flatMap((r) =>
    (r.refs ?? [])
      .filter((ref) => ref.input !== PARENT_INPUT && ids.has(ref.to))
      .map((ref) => ({
        id: `${r.id}.${ref.input}`,
        source: ref.to,
        target: r.id,
        label: `${ref.input} ← ${ref.output}`,
        ariaLabel: `${r.id}.${ref.input} uses ${ref.to}.${ref.output}`,
      })),
  )
  return { nodes, edges }
}

// Refs a connection between two nodes could mean, in either direction (the catalog decides).
export function connectionOptions(
  p: Project,
  catalog: CatalogEntry[],
  a: string,
  b: string,
): { id: string; ref: Ref }[] {
  const byId = (id: string) => (p.resources ?? []).find((r) => r.id === id)
  return [
    [a, b],
    [b, a],
  ].flatMap(([consumer, target]) => {
    const r = consumer ? byId(consumer) : undefined
    return r
      ? refOptions(p, catalog, r)
          .filter((ref) => ref.to === target)
          .map((ref) => ({ id: r.id, ref }))
      : []
  })
}
