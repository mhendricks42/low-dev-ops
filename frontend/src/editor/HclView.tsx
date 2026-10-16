import { lazy, Suspense, useState, type ComponentType } from 'react'
import { api, ApiError } from '../api'
import { Alert, Button, Status } from '../design-system/components'
import { useStore } from '../model/store'

export interface EditorProps {
  value: string
  onChange: (value: string) => void
  onSave: () => void
  error: { message: string; line: number | null } | null
}

// Loaded on demand: Monaco is large and needs browser APIs jsdom lacks.
const MonacoHcl = lazy(() => import('./MonacoHcl'))

export function HclView({ Editor = MonacoHcl }: { Editor?: ComponentType<EditorProps> }) {
  const { project, hcl, dispatch } = useStore()
  // Unsaved edits win over regenerated HCL until they are saved or discarded (M3 spec).
  const [draft, setDraft] = useState<string | null>(null)
  const [error, setError] = useState<EditorProps['error']>(null)
  const [saved, setSaved] = useState(false)

  async function save() {
    if (draft === null) return
    try {
      const next = await api.parse(draft, project)
      dispatch({ type: 'replace', project: next })
      setDraft(null)
      setError(null)
      setSaved(true)
    } catch (e) {
      const known = e instanceof ApiError && e.status === 422
      setError({
        message: known ? e.message : 'Could not reach the API; nothing was saved.',
        line: known ? e.line : null,
      })
      setSaved(false)
    }
  }

  function discard() {
    setDraft(null)
    setError(null)
  }

  return (
    <div className="hcl-view">
      <h2>HCL</h2>
      <p className="ds-hint">
        Edits are parsed when you save (Ctrl+S in the editor). Tab moves focus out of the editor;
        press Ctrl+M to type tab characters instead.
      </p>
      <div className="toolbar">
        {/* aria-disabled, not disabled: the buttons keep focus after saving or discarding. */}
        <Button variant="primary" onClick={() => void save()} aria-disabled={draft === null}>
          Save HCL
        </Button>
        <Button onClick={discard} aria-disabled={draft === null}>
          Discard edits
        </Button>
      </div>
      <Status>
        {draft !== null
          ? 'Unsaved HCL edits. Changes made elsewhere are not shown until you save or discard.'
          : saved
            ? 'HCL saved and in sync with the model.'
            : 'In sync with the model.'}
      </Status>
      {error && (
        <Alert>
          HCL not saved{error.line ? ` (line ${error.line})` : ''}: {error.message}
        </Alert>
      )}
      <Suspense fallback={<p role="status">Loading editor…</p>}>
        <Editor
          value={draft ?? hcl}
          onChange={(v) => {
            setDraft(v)
            setSaved(false)
          }}
          onSave={() => void save()}
          error={error}
        />
      </Suspense>
    </div>
  )
}
