import { describe, expect, test } from 'vitest'
import { controlFor, newResource, nextId, refOptions } from './catalog'
import { reducer } from './reducer'
import { CATALOG, project, RG, VNET } from './testData'

describe('controlFor', () => {
  test.each([
    [{ tier: 'basic', default: 'x' }, 'text'],
    [{ tier: 'basic', default: true }, 'checkbox'],
    [{ tier: 'basic', default: 3 }, 'number'],
    [{ tier: 'basic', default: ['a'] }, 'json'],
    [{ tier: 'advanced' }, 'json'],
    [{ tier: 'basic', fill: 'name' }, 'text'],
    [{ tier: 'basic', fill: 'location' }, 'text'],
  ])('%j -> %s', (spec, control) => {
    expect(controlFor(spec as never)).toBe(control)
  })
})

test('nextId picks the smallest free number', () => {
  let p = project()
  expect(nextId(p, 'rg')).toBe('rg1')
  p = reducer(p, { type: 'addResource', resource: newResource(RG, p, 'rg1') })
  p = reducer(p, { type: 'addResource', resource: newResource(RG, p, 'rg3') })
  expect(nextId(p, 'rg')).toBe('rg2')
})

test('newResource fills defaults, hidden defaults, name and location but not refs', () => {
  const r = newResource(VNET, project(), 'vnet1')
  expect(r).toEqual({
    id: 'vnet1',
    catalogRef: 'avm-res-network-virtualnetwork@0.22.3',
    parent: null,
    layout: null,
    refs: [],
    inputs: {
      name: 'vnet-app-dev-weu',
      location: 'westeurope',
      address_space: ['10.0.0.0/16'],
      enable_telemetry: false,
    },
  })
})

test('refOptions lists allowed (input, target, output) for existing resources only', () => {
  let p = project()
  expect(refOptions(p, CATALOG, newResource(VNET, p, 'vnet1'))).toEqual([])
  p = reducer(p, { type: 'addResource', resource: newResource(RG, p, 'rg1') })
  p = reducer(p, { type: 'addResource', resource: newResource(VNET, p, 'vnet1') })
  const vnet = p.resources?.[1]
  expect(vnet && refOptions(p, CATALOG, vnet)).toEqual([
    { input: 'parent_id', to: 'rg1', output: 'resource_id' },
  ])
  const rg = p.resources?.[0]
  expect(rg && refOptions(p, CATALOG, rg)).toEqual([]) // an RG takes no refs
})

test('a ref input never gets a literal, even with a null default from the catalog', () => {
  const entry = {
    ...VNET,
    inputs: { ...VNET.inputs, parent_id: { tier: 'basic' as const, default: null as never } },
  }
  expect(newResource(entry, project(), 'vnet1').inputs).not.toHaveProperty('parent_id')
})
