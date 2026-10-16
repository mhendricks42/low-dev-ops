import { expect, test } from 'vitest'
import { newResource } from '../model/catalog'
import { reducer } from '../model/reducer'
import { CATALOG, project, RG, VNET } from '../model/testData'
import { connectAction, connectionOptions, finishedMoves, toFlow } from './flow'

function rgAndVnet() {
  let p = project()
  p = reducer(p, { type: 'addResource', resource: newResource(RG, p, 'rg1') })
  p = reducer(p, { type: 'addResource', resource: newResource(VNET, p, 'vnet1') })
  return p
}

test('a resource with a parent is nested in a group node that comes first', () => {
  const p = reducer(rgAndVnet(), {
    type: 'setRef',
    id: 'vnet1',
    ref: { input: 'parent_id', to: 'rg1', output: 'resource_id' },
  })
  const { nodes, edges } = toFlow(p, CATALOG)
  expect(nodes.map((n) => [n.id, n.parentId, n.type])).toEqual([
    ['rg1', undefined, 'default'],
    ['vnet1', 'rg1', undefined],
  ])
  expect(nodes[1]?.ariaLabel).toBe('vnet1, Virtual network, inside rg1')
  expect(edges).toEqual([]) // containment is nesting, not an edge
})

test('non-parent refs become edges from the target to the consumer', () => {
  const p = reducer(rgAndVnet(), {
    type: 'setRef',
    id: 'vnet1',
    ref: { input: 'dns_zone_id', to: 'rg1', output: 'resource_id' },
  })
  expect(toFlow(p, CATALOG).edges.map((e) => [e.source, e.target, e.label])).toEqual([
    ['rg1', 'vnet1', 'dns_zone_id ← resource_id'],
  ])
})

test('layout is used when present; custom HCL gets a view-only node', () => {
  let p = reducer(rgAndVnet(), { type: 'moveNode', id: 'rg1', x: 300, y: 400 })
  p = { ...p, customHcl: [{ id: 'custom_1', hcl: 'locals {}' }] }
  const { nodes } = toFlow(p, CATALOG)
  expect(nodes.find((n) => n.id === 'rg1')?.position).toEqual({ x: 300, y: 400 })
  const custom = nodes.find((n) => n.id === 'custom:custom_1')
  expect(custom?.draggable).toBe(false)
  expect(custom?.connectable).toBe(false)
})

test('a connection is allowed only where the catalog has a ref, in either direction', () => {
  const p = rgAndVnet()
  const expected = [{ id: 'vnet1', ref: { input: 'parent_id', to: 'rg1', output: 'resource_id' } }]
  expect(connectionOptions(p, CATALOG, 'rg1', 'vnet1')).toEqual(expected)
  expect(connectionOptions(p, CATALOG, 'vnet1', 'rg1')).toEqual(expected)
  expect(connectionOptions(p, CATALOG, 'rg1', 'rg1')).toEqual([])
})

test('connectAction sets a single match, asks for several, refuses none', () => {
  const a = { id: 'vnet1', ref: { input: 'parent_id', to: 'rg1', output: 'resource_id' } }
  const b = { id: 'vnet1', ref: { input: 'dns_id', to: 'rg1', output: 'resource_id' } }
  expect(connectAction([a])).toEqual({ kind: 'set', choice: a })
  expect(connectAction([a, b])).toEqual({ kind: 'choose', choices: [a, b] })
  expect(connectAction([])).toEqual({ kind: 'none' })
})

test('finishedMoves keeps completed drags and keyboard moves, not intermediate drag steps', () => {
  expect(
    finishedMoves([
      { type: 'position', id: 'rg1', position: { x: 1, y: 2 }, dragging: true },
      { type: 'position', id: 'rg1', position: { x: 5, y: 6 }, dragging: false },
      { type: 'position', id: 'custom:c1', position: { x: 0, y: 0 }, dragging: false },
      { type: 'select', id: 'rg1', selected: true },
    ]),
  ).toEqual([{ id: 'rg1', x: 5, y: 6 }])
})
