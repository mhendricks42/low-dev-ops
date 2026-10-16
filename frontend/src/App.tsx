import { Status, Tabs } from './design-system/components'
import { ProjectProvider, useStore } from './model/store'
import { Canvas } from './canvas/Canvas'
import { HclView } from './editor/HclView'
import { Wizard } from './wizard/Wizard'

const NAME = /^[a-z][a-z0-9-]{0,62}$/

export function projectName(search: string): string {
  const name = new URLSearchParams(search).get('project') ?? 'default'
  return NAME.test(name) ? name : 'default'
}

function Shell() {
  const { project, saveStatus } = useStore()
  return (
    <>
      <header className="app-header">
        <h1>LowDevOps: {project.meta.name}</h1>
        <Status>{saveStatus}</Status>
      </header>
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
