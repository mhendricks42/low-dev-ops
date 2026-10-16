import { useState } from 'react'
import {
  Button,
  Checkbox,
  JsonField,
  NumberField,
  Select,
  TextField,
} from '../design-system/components'
import { controlFor, defaultOf, entryFor, newResource, nextId, refOptions } from '../model/catalog'
import type { CatalogEntry, InputSpec } from '../model/catalog-entry'
import type { Resource } from '../model/project'
import { useStore } from '../model/store'

const ID_PATTERN = /^[a-z][a-z0-9_]{0,62}$/

function AddResource({ onAdded }: { onAdded: (id: string) => void }) {
  const { project, catalog, dispatch } = useStore()
  const [module, setModule] = useState('')
  const [id, setId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const entry = catalog.find((e) => e.module === module)

  function chooseType(next: string) {
    setModule(next)
    const e = catalog.find((c) => c.module === next)
    setId(e ? nextId(project, e.cafAbbreviation) : '')
    setError(null)
  }

  function add() {
    if (!entry) return setError('Choose a resource type first.')
    if (!ID_PATTERN.test(id))
      return setError('Use lowercase letters, digits and _; start with a letter.')
    if ((project.resources ?? []).some((r) => r.id === id))
      return setError(`"${id}" is already used.`)
    dispatch({ type: 'addResource', resource: newResource(entry, project, id) })
    onAdded(id)
    setModule('')
    setId('')
    setError(null)
  }

  return (
    <section aria-labelledby="add-heading">
      <h2 id="add-heading">Add a resource</h2>
      <Select
        label="Resource type"
        value={module}
        placeholder="Choose a type…"
        options={catalog.map((e) => ({ value: e.module, label: `${e.title} (${e.category})` }))}
        onChange={chooseType}
      />
      <TextField label="Resource id" value={id} error={error} onChange={setId} />
      <Button variant="primary" onClick={add}>
        Add resource
      </Button>
    </section>
  )
}

function InputControl({
  resource,
  name,
  spec,
}: {
  resource: Resource
  name: string
  spec: InputSpec
}) {
  const { dispatch } = useStore()
  const value = resource.inputs?.[name]
  const set = (v: unknown) => dispatch({ type: 'setInput', id: resource.id, input: name, value: v })
  const hint = spec.description ?? null
  switch (controlFor(spec)) {
    case 'text':
      return (
        <TextField
          label={name}
          hint={hint}
          value={typeof value === 'string' ? value : ''}
          onChange={(v) => set(v === '' ? undefined : v)}
        />
      )
    case 'checkbox':
      return (
        <Checkbox
          label={name}
          hint={hint}
          checked={Boolean(value ?? defaultOf(spec))}
          onChange={set}
        />
      )
    case 'number':
      return (
        <NumberField
          label={name}
          hint={hint}
          value={Number(value ?? defaultOf(spec))}
          onChange={set}
        />
      )
    case 'json':
      return (
        <JsonField
          key={`${resource.id}.${name}`}
          label={name}
          hint={hint}
          value={value}
          onChange={set}
        />
      )
  }
}

function RefControl({
  resource,
  name,
  spec,
}: {
  resource: Resource
  name: string
  spec: InputSpec
}) {
  const { project, catalog, dispatch } = useStore()
  const options = refOptions(project, catalog, resource).filter((o) => o.input === name)
  const current = (resource.refs ?? []).find((r) => r.input === name)
  return (
    <Select
      label={name}
      hint={spec.description ?? null}
      value={current?.to ?? ''}
      placeholder="Not set"
      options={options.map((o) => ({ value: o.to, label: `${o.to} (${o.output})` }))}
      onChange={(to) => {
        const ref = options.find((o) => o.to === to)
        dispatch(
          ref
            ? { type: 'setRef', id: resource.id, ref }
            : { type: 'removeRef', id: resource.id, input: name },
        )
      }}
    />
  )
}

function Inputs({
  resource,
  entry,
  tier,
}: {
  resource: Resource
  entry: CatalogEntry
  tier: 'basic' | 'advanced'
}) {
  const refInputs = new Set((entry.refs ?? []).map((r) => r.input))
  return (
    <>
      {Object.entries(entry.inputs)
        .filter(([, spec]) => spec.tier === tier)
        .map(([name, spec]) =>
          refInputs.has(name) ? (
            <RefControl key={name} resource={resource} name={name} spec={spec} />
          ) : (
            <InputControl key={name} resource={resource} name={name} spec={spec} />
          ),
        )}
    </>
  )
}

function ResourceForm({ resource }: { resource: Resource }) {
  const { catalog, dispatch } = useStore()
  const entry = entryFor(catalog, resource)
  return (
    <form aria-labelledby={`form-${resource.id}`} onSubmit={(e) => e.preventDefault()}>
      <h3 id={`form-${resource.id}`}>
        {resource.id} {entry ? `(${entry.title})` : ''}
      </h3>
      {entry ? (
        <>
          <Inputs resource={resource} entry={entry} tier="basic" />
          <details>
            <summary>More options</summary>
            <Inputs resource={resource} entry={entry} tier="advanced" />
          </details>
        </>
      ) : (
        <p>{resource.catalogRef} is not in the catalog, so its inputs can only be edited as HCL.</p>
      )}
      <Button
        variant="danger"
        onClick={() => dispatch({ type: 'removeResource', id: resource.id })}
      >
        Remove {resource.id}
      </Button>
    </form>
  )
}

export function Wizard() {
  const { project } = useStore()
  const resources = project.resources ?? []
  const [selected, setSelected] = useState('')
  const resource = resources.find((r) => r.id === selected) ?? resources[0]

  return (
    <div className="wizard">
      <AddResource onAdded={setSelected} />
      <section aria-labelledby="edit-heading">
        <h2 id="edit-heading">Edit resources</h2>
        {resource ? (
          <>
            <Select
              label="Resource to edit"
              value={resource.id}
              options={resources.map((r) => ({ value: r.id, label: r.id }))}
              onChange={setSelected}
            />
            <ResourceForm key={resource.id} resource={resource} />
          </>
        ) : (
          <p>No resources yet. Add one above.</p>
        )}
      </section>
      {(project.customHcl ?? []).length > 0 && (
        <section aria-labelledby="custom-heading">
          <h2 id="custom-heading">Custom HCL (view only)</h2>
          <p>Edit these blocks in the HCL view.</p>
          {(project.customHcl ?? []).map((c) => (
            <pre key={c.id} aria-label={`Custom HCL ${c.id}`} tabIndex={0}>
              {c.hcl}
            </pre>
          ))}
        </section>
      )}
    </div>
  )
}
