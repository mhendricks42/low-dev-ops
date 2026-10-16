import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useReducer,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { api, ApiError } from '../api'
import { emptyProject } from './catalog'
import type { CatalogEntry } from './catalog-entry'
import type { Project } from './project'
import { reducer, type Action } from './reducer'

interface Store {
  project: Project
  dispatch: (action: Action) => void
  catalog: CatalogEntry[]
  hcl: string
  // Live (role=status) text: changes only when the outcome does, so typing is not announced.
  saveStatus: string
  // True while a save request is in flight; shown visually only (#12).
  saving: boolean
  saveError: string | null
  // True from a change until the save of that change succeeds (header status aria-busy).
  pending: boolean
  // Short message for screen readers, e.g. "Added vnet1" (WCAG 4.1.3).
  announcement: string
  announce: (message: string) => void
}

const StoreContext = createContext<Store | null>(null)

export function useStore(): Store {
  const store = useContext(StoreContext)
  if (!store) throw new Error('useStore must be used inside <ProjectProvider>')
  return store
}

const DEBOUNCE_MS = 300

function Loaded({
  initial,
  catalog,
  children,
}: {
  initial: Project
  catalog: CatalogEntry[]
  children: ReactNode
}) {
  const [project, rawDispatch] = useReducer(reducer, initial)
  const revisionRef = useRef(0)
  const [revision, setRevision] = useState(0)
  const [savedRevision, setSavedRevision] = useState(-1)
  const dispatch = useCallback((action: Action) => {
    revisionRef.current += 1
    setRevision(revisionRef.current)
    rawDispatch(action)
  }, [])
  const [hcl, setHcl] = useState('')
  const [saveStatus, setSaveStatus] = useState('Loaded')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [announcement, announce] = useState('')

  // Every model change is saved and regenerates the HCL (PRD sync rules).
  useEffect(() => {
    let cancelled = false
    const rev = revisionRef.current // the change this save covers
    const timer = setTimeout(() => {
      setSaving(true)
      api
        .generate(project)
        .then((text) => !cancelled && setHcl(text))
        .catch(() => undefined)
      api
        .saveProject(project)
        .then(() => {
          if (cancelled) return
          setSaving(false)
          setSaveStatus('All changes saved')
          setSaveError(null)
          setSavedRevision(rev)
        })
        .catch((e: unknown) => {
          if (cancelled) return
          setSaving(false)
          setSaveStatus('Not saved')
          setSaveError(`Your changes were not saved: ${(e as Error).message}`)
        })
    }, DEBOUNCE_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [project])

  return (
    <StoreContext.Provider
      value={{
        project,
        dispatch,
        catalog,
        hcl,
        saveStatus,
        saving,
        saveError,
        pending: revision !== savedRevision,
        announcement,
        announce,
      }}
    >
      {children}
    </StoreContext.Provider>
  )
}

export function ProjectProvider({ name, children }: { name: string; children: ReactNode }) {
  const [loaded, setLoaded] = useState<{ project: Project; catalog: CatalogEntry[] } | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const project = api
      .getProject(name)
      .catch((e: unknown) =>
        e instanceof ApiError && e.status === 404 ? emptyProject(name) : Promise.reject(e),
      )
    Promise.all([project, api.catalog()])
      .then(([p, c]) => setLoaded({ project: p, catalog: c }))
      .catch((e: unknown) => setError((e as Error).message))
  }, [name])

  if (error) return <p role="alert">Could not load project: {error}</p>
  if (!loaded) return <p role="status">Loading project…</p>
  return (
    <Loaded initial={loaded.project} catalog={loaded.catalog}>
      {children}
    </Loaded>
  )
}
