// Accessible building blocks: native elements, visible labels, errors tied to their field.
import {
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type KeyboardEvent,
  type ReactNode,
} from 'react'

export function Button({
  variant = 'secondary',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'danger' }) {
  return <button type="button" className="ds-button" data-variant={variant} {...props} />
}

interface FieldProps {
  label: string
  hint?: string | null
  error?: string | null
}

function describedBy(hintId: string, errorId: string, p: FieldProps): string | undefined {
  return [p.hint ? hintId : '', p.error ? errorId : ''].filter(Boolean).join(' ') || undefined
}

function Messages({
  hintId,
  errorId,
  hint,
  error,
}: FieldProps & { hintId: string; errorId: string }) {
  return (
    <>
      {hint && (
        <span id={hintId} className="ds-hint">
          {hint}
        </span>
      )}
      {error && (
        <span id={errorId} className="ds-error">
          {error}
        </span>
      )}
    </>
  )
}

export function TextField(
  p: FieldProps & { value: string; onChange: (value: string) => void; required?: boolean },
) {
  const id = useId()
  return (
    <div className="ds-field">
      <label htmlFor={id}>{p.label}</label>
      <input
        id={id}
        value={p.value}
        required={p.required}
        aria-invalid={p.error ? true : undefined}
        aria-describedby={describedBy(`${id}-hint`, `${id}-error`, p)}
        onChange={(e) => p.onChange(e.target.value)}
      />
      <Messages {...p} hintId={`${id}-hint`} errorId={`${id}-error`} />
    </div>
  )
}

export function NumberField(p: FieldProps & { value: number; onChange: (value: number) => void }) {
  const id = useId()
  return (
    <div className="ds-field">
      <label htmlFor={id}>{p.label}</label>
      <input
        id={id}
        type="number"
        value={Number.isFinite(p.value) ? p.value : ''}
        aria-describedby={describedBy(`${id}-hint`, `${id}-error`, p)}
        onChange={(e) => e.target.value !== '' && p.onChange(Number(e.target.value))}
      />
      <Messages {...p} hintId={`${id}-hint`} errorId={`${id}-error`} />
    </div>
  )
}

export function Checkbox(
  p: FieldProps & { checked: boolean; onChange: (checked: boolean) => void },
) {
  const id = useId()
  return (
    <div className="ds-check">
      <input
        id={id}
        type="checkbox"
        checked={p.checked}
        aria-describedby={p.hint ? `${id}-hint` : undefined}
        onChange={(e) => p.onChange(e.target.checked)}
      />
      <label htmlFor={id}>{p.label}</label>
      {p.hint && (
        <span id={`${id}-hint`} className="ds-hint">
          {p.hint}
        </span>
      )}
    </div>
  )
}

export interface Option {
  value: string
  label: string
}

export function Select(
  p: FieldProps & {
    value: string
    options: Option[]
    onChange: (value: string) => void
    placeholder?: string
  },
) {
  const id = useId()
  return (
    <div className="ds-field">
      <label htmlFor={id}>{p.label}</label>
      <select
        id={id}
        value={p.value}
        aria-invalid={p.error ? true : undefined}
        aria-describedby={describedBy(`${id}-hint`, `${id}-error`, p)}
        onChange={(e) => p.onChange(e.target.value)}
      >
        {p.placeholder !== undefined && <option value="">{p.placeholder}</option>}
        {p.options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <Messages {...p} hintId={`${id}-hint`} errorId={`${id}-error`} />
    </div>
  )
}

// A JSON value edited as text. Only valid JSON reaches onChange; empty text means "unset".
export function JsonField(
  p: Omit<FieldProps, 'error'> & { value: unknown; onChange: (value: unknown) => void },
) {
  const id = useId()
  const format = (v: unknown) => (v === undefined ? '' : JSON.stringify(v, null, 2))
  const [text, setText] = useState(() => format(p.value))
  const [error, setError] = useState<string | null>(null)
  const last = useRef(p.value)

  // An outside change (e.g. an HCL save) replaces the text unless it is what we just sent.
  useEffect(() => {
    if (JSON.stringify(p.value) !== JSON.stringify(last.current)) {
      last.current = p.value
      setText(format(p.value))
      setError(null)
    }
  }, [p.value])

  function change(next: string) {
    setText(next)
    if (next.trim() === '') {
      setError(null)
      last.current = undefined
      p.onChange(undefined)
      return
    }
    try {
      const value: unknown = JSON.parse(next)
      setError(null)
      last.current = value
      p.onChange(value)
    } catch {
      setError('Not valid JSON yet; the last valid value is kept.')
    }
  }

  return (
    <div className="ds-field">
      <label htmlFor={id}>{p.label}</label>
      <textarea
        id={id}
        value={text}
        spellCheck={false}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(`${id}-hint`, `${id}-error`, { ...p, error })}
        onChange={(e) => change(e.target.value)}
      />
      <Messages
        hint={p.hint}
        error={error}
        label={p.label}
        hintId={`${id}-hint`}
        errorId={`${id}-error`}
      />
    </div>
  )
}

export interface Tab {
  id: string
  label: string
  panel: ReactNode
}

// ARIA tabs with arrow/Home/End keys. A panel mounts the first time it is shown (so canvases
// measure a real size), then stays mounted while hidden so editors keep their state.
export function Tabs({ label, tabs }: { label: string; tabs: Tab[] }) {
  const [active, setActive] = useState(tabs[0]?.id ?? '')
  const [visited, setVisited] = useState(() => new Set([active]))
  if (!visited.has(active)) setVisited(new Set(visited).add(active))
  const refs = useRef<Record<string, HTMLButtonElement | null>>({})

  function onKeyDown(e: KeyboardEvent) {
    const index = tabs.findIndex((t) => t.id === active)
    const next = {
      ArrowRight: (index + 1) % tabs.length,
      ArrowLeft: (index - 1 + tabs.length) % tabs.length,
      Home: 0,
      End: tabs.length - 1,
    }[e.key]
    if (next === undefined) return
    e.preventDefault()
    const id = tabs[next]?.id
    if (id) {
      setActive(id)
      refs.current[id]?.focus()
    }
  }

  return (
    <>
      <div role="tablist" aria-label={label} className="ds-tablist" onKeyDown={onKeyDown}>
        {tabs.map((t) => (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[t.id] = el
            }}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            className="ds-tab"
            aria-selected={t.id === active}
            aria-controls={`panel-${t.id}`}
            tabIndex={t.id === active ? 0 : -1}
            onClick={() => setActive(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tabs.map((t) => (
        <section
          key={t.id}
          role="tabpanel"
          id={`panel-${t.id}`}
          aria-labelledby={`tab-${t.id}`}
          hidden={t.id !== active}
          tabIndex={0}
        >
          {visited.has(t.id) && t.panel}
        </section>
      ))}
    </>
  )
}

// Native modal <dialog>: focus trap, Escape and inert background come from the browser.
export function Dialog({
  title,
  open,
  onClose,
  children,
}: {
  title: string
  open: boolean
  onClose: () => void
  children: ReactNode
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal?.()
    if (!open && dialog.open) dialog.close?.()
  }, [open])
  return (
    <dialog ref={ref} className="ds-dialog" aria-labelledby={titleId} onClose={onClose}>
      {open && (
        <>
          <h2 id={titleId}>{title}</h2>
          {children}
        </>
      )}
    </dialog>
  )
}

export function Status({ children }: { children: ReactNode }) {
  return (
    <p role="status" className="ds-status">
      {children}
    </p>
  )
}

export function Alert({ children }: { children: ReactNode }) {
  return (
    <div role="alert" className="ds-alert">
      {children}
    </div>
  )
}
