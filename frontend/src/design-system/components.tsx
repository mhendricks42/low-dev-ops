// Accessible building blocks: native elements, visible labels, errors tied to their field.
import {
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type KeyboardEvent,
  type ReactNode,
  type Ref,
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

export function TextField({
  inputRef,
  ...p
}: FieldProps & {
  value: string
  onChange: (value: string) => void
  required?: boolean
  inputRef?: Ref<HTMLInputElement>
}) {
  const id = useId()
  return (
    <div className="ds-field">
      <label htmlFor={id}>{p.label}</label>
      <input
        ref={inputRef}
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
  group?: string
}

function OptionList({ options }: { options: Option[] }) {
  const groups = [...new Set(options.map((o) => o.group))]
  const render = (o: Option) => (
    <option key={o.value} value={o.value}>
      {o.label}
    </option>
  )
  if (groups.every((g) => g === undefined)) return <>{options.map(render)}</>
  return (
    <>
      {groups.map((g) => (
        <optgroup key={g ?? ''} label={g ?? 'Other'}>
          {options.filter((o) => o.group === g).map(render)}
        </optgroup>
      ))}
    </>
  )
}

export function Select({
  inputRef,
  ...p
}: FieldProps & {
  value: string
  options: Option[]
  onChange: (value: string) => void
  placeholder?: string
  inputRef?: Ref<HTMLSelectElement>
}) {
  const id = useId()
  return (
    <div className="ds-field">
      <label htmlFor={id}>{p.label}</label>
      <select
        ref={inputRef}
        id={id}
        value={p.value}
        aria-invalid={p.error ? true : undefined}
        aria-describedby={describedBy(`${id}-hint`, `${id}-error`, p)}
        onChange={(e) => p.onChange(e.target.value)}
      >
        {p.placeholder !== undefined && <option value="">{p.placeholder}</option>}
        <OptionList options={p.options} />
      </select>
      <Messages {...p} hintId={`${id}-hint`} errorId={`${id}-error`} />
    </div>
  )
}

// A JSON value edited as text. Only valid JSON reaches onChange; empty text means "unset".
// The error is announced (polite live region) when the user leaves the field, not per keystroke.
export function JsonField(
  p: Omit<FieldProps, 'error'> & { value: unknown; onChange: (value: unknown) => void },
) {
  const id = useId()
  const format = (v: unknown) => (v === undefined ? '' : JSON.stringify(v, null, 2))
  const [text, setText] = useState(() => format(p.value))
  const [invalid, setInvalid] = useState(false)
  const [shown, setShown] = useState<string | null>(null)
  const last = useRef(p.value)
  const message = `${p.label}: not valid JSON yet; the last valid value is kept.`

  // An outside change (e.g. an HCL save) replaces the text unless it is what we just sent.
  useEffect(() => {
    if (JSON.stringify(p.value) !== JSON.stringify(last.current)) {
      last.current = p.value
      setText(format(p.value))
      setInvalid(false)
      setShown(null)
    }
  }, [p.value])

  function change(next: string) {
    setText(next)
    let value: unknown
    if (next.trim() !== '') {
      try {
        value = JSON.parse(next)
      } catch {
        setInvalid(true)
        return
      }
    }
    setInvalid(false)
    setShown(null)
    last.current = value
    p.onChange(value)
  }

  return (
    <div className="ds-field">
      <label htmlFor={id}>{p.label}</label>
      <textarea
        id={id}
        value={text}
        spellCheck={false}
        aria-invalid={invalid ? true : undefined}
        aria-describedby={describedBy(`${id}-hint`, `${id}-error`, { ...p, error: shown })}
        onChange={(e) => change(e.target.value)}
        onBlur={() => setShown(invalid ? message : null)}
      />
      {p.hint && (
        <span id={`${id}-hint`} className="ds-hint">
          {p.hint}
        </span>
      )}
      <span id={`${id}-error`} className="ds-error" aria-live="polite">
        {shown}
      </span>
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
// Unmounting an open modal skips the browser's focus restore, so it is done here: back to the
// element that opened it, or `returnFocus` when that element is gone or disabled.
export function Dialog({
  title,
  open,
  onClose,
  returnFocus,
  children,
}: {
  title: string
  open: boolean
  onClose: () => void
  returnFocus?: () => void
  children: ReactNode
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  const fallback = useRef(returnFocus)
  useEffect(() => {
    fallback.current = returnFocus
  }, [returnFocus])
  // Declared first so it records the opener before showModal moves focus into the dialog.
  // It must not call close(): that fires the native close event, i.e. onClose.
  const opener = useRef<HTMLElement | null>(null)
  useEffect(() => {
    if (!open) return
    const active = document.activeElement
    // Ignore focus already inside the dialog (React StrictMode re-runs this effect).
    if (active instanceof HTMLElement && active !== document.body && !ref.current?.contains(active))
      opener.current = active
    return () => {
      const target = opener.current
      if (target?.isConnected && !target.matches(':disabled')) target.focus()
      else fallback.current?.()
    }
  }, [open])
  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
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

export function Status({ children, busy }: { children: ReactNode; busy?: boolean }) {
  return (
    <p role="status" className="ds-status" aria-busy={busy}>
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
