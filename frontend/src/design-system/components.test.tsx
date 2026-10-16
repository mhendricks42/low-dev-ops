import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { expect, test, vi } from 'vitest'
import { Checkbox, Dialog, JsonField, Select, Tabs, TextField } from './components'

test('text field is labelled and its error describes it', () => {
  render(<TextField label="Name" value="" error="Required" hint="Lowercase" onChange={() => {}} />)
  const input = screen.getByLabelText('Name')
  expect(input).toHaveAccessibleDescription('Lowercase Required')
  expect(input).toHaveAttribute('aria-invalid', 'true')
})

test('checkbox and select are labelled', () => {
  const onChange = vi.fn()
  render(
    <>
      <Checkbox label="Telemetry" checked={false} onChange={onChange} />
      <Select
        label="Type"
        value=""
        placeholder="Choose…"
        options={[{ value: 'a', label: 'A' }]}
        onChange={onChange}
      />
    </>,
  )
  fireEvent.click(screen.getByLabelText('Telemetry'))
  expect(onChange).toHaveBeenCalledWith(true)
  fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'a' } })
  expect(onChange).toHaveBeenCalledWith('a')
})

test('JSON field only passes on valid JSON and explains invalid input', () => {
  const onChange = vi.fn()
  render(<JsonField label="Address space" value={['10.0.0.0/16']} onChange={onChange} />)
  const box = screen.getByLabelText('Address space')
  fireEvent.change(box, { target: { value: '["10.1.0.0/16"' } })
  expect(onChange).not.toHaveBeenCalled()
  expect(box).toHaveAttribute('aria-invalid', 'true')
  expect(box).toHaveAccessibleDescription('') // not announced on every keystroke
  fireEvent.blur(box)
  expect(box).toHaveAccessibleDescription(
    'Address space: not valid JSON yet; the last valid value is kept.',
  )
  fireEvent.change(box, { target: { value: '["10.1.0.0/16"]' } })
  expect(onChange).toHaveBeenCalledWith(['10.1.0.0/16'])
  fireEvent.change(box, { target: { value: '' } })
  expect(onChange).toHaveBeenLastCalledWith(undefined)
})

test('tabs move with arrow keys and show only the active panel', () => {
  render(
    <Tabs
      label="Views"
      tabs={[
        { id: 'a', label: 'Alpha', panel: <p>first</p> },
        { id: 'b', label: 'Beta', panel: <p>second</p> },
      ]}
    />,
  )
  const alpha = screen.getByRole('tab', { name: 'Alpha' })
  expect(alpha).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByRole('tabpanel', { name: 'Alpha' })).toHaveTextContent('first')
  fireEvent.keyDown(alpha, { key: 'ArrowRight' })
  const beta = screen.getByRole('tab', { name: 'Beta' })
  expect(beta).toHaveAttribute('aria-selected', 'true')
  expect(beta).toHaveFocus()
  expect(screen.getByRole('tabpanel', { name: 'Beta' })).toBeVisible()
  expect(screen.getByText('first')).not.toBeVisible()
})

test('a panel mounts on first view and stays mounted after', () => {
  render(
    <Tabs
      label="Views"
      tabs={[
        { id: 'a', label: 'Alpha', panel: <p>first</p> },
        { id: 'b', label: 'Beta', panel: <p>second</p> },
      ]}
    />,
  )
  expect(screen.queryByText('second')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('tab', { name: 'Beta' }))
  fireEvent.click(screen.getByRole('tab', { name: 'Alpha' }))
  expect(screen.getByText('second')).toBeInTheDocument()
})

test('select groups options under their group label', () => {
  render(
    <Select
      label="Type"
      value=""
      onChange={() => {}}
      options={[
        { value: 'rg', label: 'Resource group', group: 'foundation' },
        { value: 'aks', label: 'AKS', group: 'compute' },
      ]}
    />,
  )
  expect(screen.getByRole('group', { name: 'foundation' })).toContainElement(
    screen.getByRole('option', { name: 'Resource group' }),
  )
})

test('a dialog returns focus to its opener, or to the fallback when the opener is gone', () => {
  function Harness({ removeOpener }: { removeOpener: boolean }) {
    const [open, setOpen] = useState(false)
    const [gone, setGone] = useState(false)
    return (
      <>
        {!gone && <button onClick={() => setOpen(true)}>Open</button>}
        <h2 tabIndex={-1} id="fallback">
          Fallback
        </h2>
        {open && (
          <Dialog
            title="Pick"
            open
            onClose={() => setOpen(false)}
            returnFocus={() => document.getElementById('fallback')?.focus()}
          >
            <button
              onClick={() => {
                if (removeOpener) setGone(true)
                setOpen(false)
              }}
            >
              Done
            </button>
          </Dialog>
        )}
      </>
    )
  }
  const { unmount } = render(<Harness removeOpener={false} />)
  const opener = screen.getByRole('button', { name: 'Open' })
  opener.focus()
  fireEvent.click(opener)
  fireEvent.click(screen.getByRole('button', { name: 'Done' }))
  expect(opener).toHaveFocus()
  unmount()

  render(<Harness removeOpener />)
  screen.getByRole('button', { name: 'Open' }).focus()
  fireEvent.click(screen.getByRole('button', { name: 'Open' }))
  fireEvent.click(screen.getByRole('button', { name: 'Done' }))
  expect(screen.getByRole('heading', { name: 'Fallback' })).toHaveFocus()
})
