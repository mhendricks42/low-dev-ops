import Editor from '@monaco-editor/react'
import { useEffect, useRef } from 'react'
import type { EditorProps } from './HclView'
import { monaco } from './monaco'

type Instance = Parameters<NonNullable<React.ComponentProps<typeof Editor>['onMount']>>[0]

export default function MonacoHcl({ value, onChange, onSave, error }: EditorProps) {
  const editorRef = useRef<Instance | null>(null)
  const saveRef = useRef(onSave)
  useEffect(() => {
    saveRef.current = onSave
  }, [onSave])

  // Show a parse error as a marker on its line.
  useEffect(() => {
    const model = editorRef.current?.getModel()
    if (!model) return
    const markers = error
      ? [
          {
            severity: monaco.MarkerSeverity.Error,
            message: error.message,
            startLineNumber: error.line ?? 1,
            endLineNumber: error.line ?? 1,
            startColumn: 1,
            endColumn: model.getLineMaxColumn(error.line ?? 1),
          },
        ]
      : []
    monaco.editor.setModelMarkers(model, 'lowdevops', markers)
  }, [error])

  return (
    <Editor
      height="60vh"
      language="hcl"
      value={value}
      onChange={(v) => onChange(v ?? '')}
      onMount={(editor) => {
        editorRef.current = editor
        editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => saveRef.current())
      }}
      options={{
        ariaLabel: 'HCL source',
        // Tab moves focus out of the editor (WCAG 2.1.2 no keyboard trap); Ctrl+M toggles it.
        tabFocusMode: true,
        minimap: { enabled: false },
        fontSize: 14,
        scrollBeyondLastLine: false,
      }}
    />
  )
}
