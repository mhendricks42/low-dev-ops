import type { CatalogEntry } from './catalog-entry'
import type { Project } from './project'

export const RG: CatalogEntry = {
  schemaVersion: 1,
  module: 'avm-res-resources-resourcegroup',
  version: '0.4.0',
  title: 'Resource group',
  category: 'foundation',
  cafAbbreviation: 'rg',
  inputs: {
    name: { tier: 'basic', fill: 'name' },
    location: { tier: 'basic', fill: 'location' },
    tags: { tier: 'advanced' },
    enable_telemetry: { tier: 'hidden', default: false as never },
  },
  refs: [],
  outputs: ['name', 'resource_id'],
}

export const VNET: CatalogEntry = {
  schemaVersion: 1,
  module: 'avm-res-network-virtualnetwork',
  version: '0.22.3',
  title: 'Virtual network',
  category: 'foundation',
  cafAbbreviation: 'vnet',
  inputs: {
    name: { tier: 'basic', fill: 'name' },
    location: { tier: 'basic', fill: 'location' },
    parent_id: { tier: 'basic' },
    address_space: { tier: 'basic', default: ['10.0.0.0/16'] as never },
    subnets: { tier: 'advanced' },
    enable_telemetry: { tier: 'hidden', default: false as never },
  },
  refs: [{ input: 'parent_id', from: 'avm-res-resources-resourcegroup', output: 'resource_id' }],
  outputs: ['name', 'resource_id'],
}

export const CATALOG = [RG, VNET]

export function project(): Project {
  return {
    schemaVersion: 1,
    meta: { name: 'demo', created: '2026-10-16T00:00:00Z', lowdevopsVersion: '0.1.0' },
    subscription: { id: '', tenantId: 't-1', location: 'westeurope' },
    naming: {
      workload: 'app',
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
