import { expect, test } from 'vitest'
import { newResource } from './catalog'
import { reducer } from './reducer'
import { project, RG, VNET } from './testData'
import type { Project } from './project'

function withRgAndVnet(): Project {
  let p = project()
  p = reducer(p, { type: 'addResource', resource: newResource(RG, p, 'rg1') })
  return reducer(p, { type: 'addResource', resource: newResource(VNET, p, 'vnet1') })
}

const vnet = (p: Project) => p.resources?.find((r) => r.id === 'vnet1')

test('setRef on parent_id also sets parent, and replaces a literal input', () => {
  let p = withRgAndVnet()
  p = reducer(p, { type: 'setInput', id: 'vnet1', input: 'parent_id', value: '/subscriptions/x' })
  p = reducer(p, {
    type: 'setRef',
    id: 'vnet1',
    ref: { input: 'parent_id', to: 'rg1', output: 'resource_id' },
  })
  expect(vnet(p)?.parent).toBe('rg1')
  expect(vnet(p)?.inputs).not.toHaveProperty('parent_id')
  expect(vnet(p)?.refs).toEqual([{ input: 'parent_id', to: 'rg1', output: 'resource_id' }])
})

test('refs stay sorted by input and one ref per input', () => {
  let p = withRgAndVnet()
  p = reducer(p, { type: 'setRef', id: 'vnet1', ref: { input: 'z_id', to: 'rg1', output: 'name' } })
  p = reducer(p, { type: 'setRef', id: 'vnet1', ref: { input: 'a_id', to: 'rg1', output: 'name' } })
  p = reducer(p, {
    type: 'setRef',
    id: 'vnet1',
    ref: { input: 'a_id', to: 'rg1', output: 'resource_id' },
  })
  expect(vnet(p)?.refs?.map((r) => [r.input, r.output])).toEqual([
    ['a_id', 'resource_id'],
    ['z_id', 'name'],
  ])
})

test('setInput replaces a ref of the same input; undefined removes the input', () => {
  let p = withRgAndVnet()
  p = reducer(p, {
    type: 'setRef',
    id: 'vnet1',
    ref: { input: 'parent_id', to: 'rg1', output: 'resource_id' },
  })
  p = reducer(p, { type: 'setInput', id: 'vnet1', input: 'parent_id', value: 'literal' })
  expect(vnet(p)?.refs).toEqual([])
  expect(vnet(p)?.parent).toBeNull()
  p = reducer(p, { type: 'setInput', id: 'vnet1', input: 'parent_id', value: undefined })
  expect(vnet(p)?.inputs).not.toHaveProperty('parent_id')
})

test('removeRef on parent_id clears parent', () => {
  let p = withRgAndVnet()
  p = reducer(p, {
    type: 'setRef',
    id: 'vnet1',
    ref: { input: 'parent_id', to: 'rg1', output: 'resource_id' },
  })
  p = reducer(p, { type: 'removeRef', id: 'vnet1', input: 'parent_id' })
  expect(vnet(p)?.refs).toEqual([])
  expect(vnet(p)?.parent).toBeNull()
})

test('removeResource drops refs and parents that pointed at it', () => {
  let p = withRgAndVnet()
  p = reducer(p, {
    type: 'setRef',
    id: 'vnet1',
    ref: { input: 'parent_id', to: 'rg1', output: 'resource_id' },
  })
  p = reducer(p, { type: 'removeResource', id: 'rg1' })
  expect(p.resources?.map((r) => r.id)).toEqual(['vnet1'])
  expect(vnet(p)?.refs).toEqual([])
  expect(vnet(p)?.parent).toBeNull()
})

test('moveNode writes layout; actions never mutate the previous state', () => {
  const before = withRgAndVnet()
  const snapshot = JSON.stringify(before)
  const after = reducer(before, { type: 'moveNode', id: 'rg1', x: 10, y: 20 })
  expect(after.resources?.[0]?.layout).toEqual({ x: 10, y: 20 })
  expect(JSON.stringify(before)).toBe(snapshot)
})

test('replace swaps the whole project', () => {
  const next = project()
  expect(reducer(withRgAndVnet(), { type: 'replace', project: next })).toBe(next)
})
