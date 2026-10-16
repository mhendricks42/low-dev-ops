import { expect, test } from 'vitest'
import cases from '../../../backend/tests/fixtures/naming-cases.json'
import type { CatalogEntry } from './catalog-entry'
import type { Naming } from './project'
import { cafName } from './naming'

// The backend's tests/guardrails/test_naming.py runs the same vectors (M4 EC4).
test.each(cases)('$id', ({ entry, naming, expected, ...rest }) => {
  const kind = 'kind' in rest ? (rest.kind as string) : undefined
  expect(cafName(entry as unknown as CatalogEntry, naming as Naming, kind)).toBe(expected)
})
