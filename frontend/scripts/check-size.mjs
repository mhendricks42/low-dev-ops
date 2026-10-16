// Fails when a built chunk grows past its gzipped budget (M3.1, #11). Run after `vite build`.
// The Monaco chunk is almost all of Monaco's core (the editor already imports the API-only
// entry), so the budget stops silent growth rather than forcing a cut. Raise a limit only in
// a reviewed change, with the reason in the commit.
import { readdirSync, readFileSync } from 'node:fs'
import { gzipSync } from 'node:zlib'

const KB = 1000
const BUDGETS = [
  { name: 'Monaco HCL editor', pattern: /^MonacoHcl-.*\.js$/, limit: 750 * KB }, // 692 KB at M3.1
  { name: 'app entry', pattern: /^index-.*\.js$/, limit: 145 * KB }, // 133 KB at M3.1
]

const dir = new URL('../dist/assets/', import.meta.url)
const files = readdirSync(dir)
let failed = false
for (const { name, pattern, limit } of BUDGETS) {
  const matches = files.filter((f) => pattern.test(f))
  if (matches.length !== 1) {
    console.error(`${name}: expected one chunk matching ${pattern}, found ${matches.length}`)
    failed = true
    continue
  }
  const size = gzipSync(readFileSync(new URL(matches[0], dir))).length
  const ok = size <= limit
  failed ||= !ok
  console.log(
    `${ok ? 'ok ' : 'OVER'} ${name}: ${(size / KB).toFixed(0)} KB gzipped (budget ${limit / KB} KB)`,
  )
}
process.exit(failed ? 1 : 0)
