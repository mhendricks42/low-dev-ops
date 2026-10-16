import type { CheckReport } from './types'

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

export function statusText(report: CheckReport): string {
  const blocking = report.findings.filter((f) => !f.waivable).length
  if (report.blocked) return `Apply blocked: ${plural(blocking, 'high or critical finding')}`
  const open = report.findings.length
  const review = open ? `, with ${plural(open, 'finding')} to review` : ''
  if (!report.plan_scanned)
    return `No blocking findings${review}. Apply also needs a scanned plan, which comes with planning.`
  return `Apply allowed${review}`
}
