import { useState } from 'react'
import { Button, Dialog, Select } from '../design-system/components'
import type { Ref } from '../model/project'
import { useStore } from '../model/store'

export interface Choice {
  id: string
  ref: Ref
}

// Pick one allowed reference and set it. Used by the list view and by canvas connections.
export function ReferenceDialog({
  title,
  choices,
  onClose,
}: {
  title: string
  choices: Choice[]
  onClose: () => void
}) {
  const { dispatch } = useStore()
  const key = (c: Choice) => `${c.id}.${c.ref.input}=${c.ref.to}.${c.ref.output}`
  const [selected, setSelected] = useState(choices[0] ? key(choices[0]) : '')

  function add() {
    const choice = choices.find((c) => key(c) === selected)
    if (choice) dispatch({ type: 'setRef', id: choice.id, ref: choice.ref })
    onClose()
  }

  return (
    <Dialog title={title} open onClose={onClose}>
      <form method="dialog" onSubmit={(e) => (e.preventDefault(), add())}>
        <Select
          label="Reference"
          value={selected}
          options={choices.map((c) => ({
            value: key(c),
            label: `${c.id}.${c.ref.input} ← ${c.ref.to}.${c.ref.output}`,
          }))}
          onChange={setSelected}
        />
        <div className="toolbar">
          <Button type="submit" variant="primary">
            Add reference
          </Button>
          <Button onClick={onClose}>Cancel</Button>
        </div>
      </form>
    </Dialog>
  )
}
