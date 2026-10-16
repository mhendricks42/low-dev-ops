import { useState } from 'react'
import { flushSync } from 'react-dom'
import { Button } from '../design-system/components'
import { entryFor, refOptions } from '../model/catalog'
import { useStore } from '../model/store'
import { ReferenceDialog } from './ReferenceDialog'

// Every canvas action, without a pointer (PRD accessibility row).
const focusById = (id: string) => document.getElementById(id)?.focus()

export function ListView() {
  const { project, catalog, dispatch, announce } = useStore()
  const [adding, setAdding] = useState<string | null>(null)
  const resources = project.resources ?? []
  const target = resources.find((r) => r.id === adding)

  return (
    <section aria-labelledby="list-heading">
      <h2 id="list-heading" tabIndex={-1}>
        Resources and references
      </h2>
      {resources.length === 0 ? (
        <p>No resources yet. Add them in the Wizard.</p>
      ) : (
        <table className="list-view">
          <caption className="ds-sr-only">Resources, their parent and references</caption>
          <thead>
            <tr>
              <th scope="col">Resource</th>
              <th scope="col">Type</th>
              <th scope="col">Inside</th>
              <th scope="col">References</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {resources.map((r) => {
              const options = refOptions(project, catalog, r)
              return (
                <tr key={r.id}>
                  <th scope="row" id={`row-${r.id}`} tabIndex={-1}>
                    {r.id}
                  </th>
                  <td>{entryFor(catalog, r)?.title ?? r.catalogRef}</td>
                  <td>{r.parent ?? '—'}</td>
                  <td>
                    <ul>
                      {(r.refs ?? []).map((ref) => (
                        <li key={ref.input}>
                          {ref.input} ← {ref.to}.{ref.output}{' '}
                          <Button
                            variant="danger"
                            onClick={() => {
                              flushSync(() =>
                                dispatch({ type: 'removeRef', id: r.id, input: ref.input }),
                              )
                              announce(`Removed reference ${ref.input} from ${r.id}.`)
                              focusById(`add-ref-${r.id}`)
                            }}
                          >
                            Remove {ref.input} from {r.id}
                          </Button>
                        </li>
                      ))}
                    </ul>
                  </td>
                  <td>
                    <div className="toolbar">
                      <Button
                        id={`add-ref-${r.id}`}
                        disabled={options.length === 0}
                        onClick={() => setAdding(r.id)}
                      >
                        Add reference to {r.id}
                      </Button>
                      <Button
                        variant="danger"
                        onClick={() => {
                          flushSync(() => dispatch({ type: 'removeResource', id: r.id }))
                          announce(`Removed ${r.id}.`)
                          focusById('list-heading') // the row and its buttons are gone
                        }}
                      >
                        Remove {r.id}
                      </Button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      {target && (
        <ReferenceDialog
          title={`Add a reference to ${target.id}`}
          choices={refOptions(project, catalog, target).map((ref) => ({ id: target.id, ref }))}
          onClose={() => setAdding(null)}
          returnFocus={() => focusById(`row-${target.id}`)}
        />
      )}
    </section>
  )
}
