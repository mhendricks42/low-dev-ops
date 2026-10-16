// Monaco is bundled, never loaded from a CDN: the app runs on localhost, possibly offline.
import { loader } from '@monaco-editor/react'
import * as monaco from 'monaco-editor/editor'
import 'monaco-editor/languages/definitions/hcl/register'
import EditorWorker from 'monaco-editor/editor/editor.worker?worker'

self.MonacoEnvironment = { getWorker: () => new EditorWorker() }
loader.config({ monaco })

export { monaco }
