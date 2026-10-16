import { useEffect, useState } from 'react'
import { Alert, Status, Tabs } from './design-system/components'
import { ProjectProvider, useStore } from './model/store'
import { Canvas } from './canvas/Canvas'
import { HclView } from './editor/HclView'
import { Wizard } from './wizard/Wizard'

const NAME = /^[a-z][a-z0-9-]{0,62}$/

export function projectName(search: string): string {
  const name = new URLSearchParams(search).get('project') ?? 'default'
  return NAME.test(name) ? name : 'default'
}

function useApiHealth(): string {
  const [health, setHealth] = useState('checking…')
  useEffect(() => {
    fetch('/api/health')
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(res.statusText))))
      .then((body: { status: string }) => setHealth(body.status))
      .catch(() => setHealth('unreachable'))
  }, [])
  return health
}

function Shell() {
  const { project, saveStatus, saving, saveError, announcement, pending } = useStore()
  const health = useApiHealth()
  return (
    <>
      <header className="app-header">
        <h1>LowDevOps: {project.meta.name}</h1>
        <div className="app-status">
          <Status>API: {health}</Status>
          <Status busy={pending}>{saveStatus}</Status>
          {/* Visual only: the live status above announces outcomes, not every save (#12). */}
          {saving && (
            <span className="app-saving" aria-hidden="true">
              Saving…
            </span>
          )}
        </div>
      </header>
      <p role="status" className="ds-sr-only">
        {announcement}
      </p>
      {saveError && <Alert>{saveError}</Alert>}
      <main>
        <Tabs
          label="Project views"
          tabs={[
            { id: 'wizard', label: 'Wizard', panel: <Wizard /> },
            { id: 'canvas', label: 'Canvas', panel: <Canvas /> },
            { id: 'hcl', label: 'HCL', panel: <HclView /> },
          ]}
        />
      </main>
    </>
  )
}

export default function App() {
  return (
    <ProjectProvider name={projectName(window.location.search)}>
      <Shell />
    </ProjectProvider>
  )
}
