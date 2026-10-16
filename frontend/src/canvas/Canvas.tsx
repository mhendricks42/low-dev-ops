import {
  applyNodeChanges,
  Background,
  Controls,
  ReactFlow,
  type Connection,
  type Node,
  type NodeChange,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useMemo, useState } from 'react'
import { useStore } from '../model/store'
import { connectAction, connectionOptions, finishedMoves, toFlow, type NodeData } from './flow'
import { ListView } from './ListView'
import { ReferenceDialog, type Choice } from './ReferenceDialog'

const focusNode = (id: string) =>
  document.querySelector<HTMLElement>(`.react-flow__node[data-id="${CSS.escape(id)}"]`)?.focus()

export function Canvas() {
  const { project, catalog, dispatch, announce } = useStore()
  const flow = useMemo(() => toFlow(project, catalog), [project, catalog])
  const [nodes, setNodes] = useState<Node<NodeData>[]>(flow.nodes)
  const [shownFlow, setShownFlow] = useState(flow)
  const [pending, setPending] = useState<{ choices: Choice[]; node: string } | null>(null)

  // The model is the source of truth; local node state only exists to animate dragging, and
  // is reset (during render, React's pattern for derived state) whenever the model changes.
  if (shownFlow !== flow) {
    setShownFlow(flow)
    setNodes(flow.nodes)
  }

  function onNodesChange(changes: NodeChange<Node<NodeData>>[]) {
    setNodes((current) => applyNodeChanges(changes, current))
    for (const move of finishedMoves(changes)) dispatch({ type: 'moveNode', ...move })
  }

  function onConnect(c: Connection) {
    const action = connectAction(connectionOptions(project, catalog, c.source, c.target))
    if (action.kind === 'set') {
      dispatch({ type: 'setRef', id: action.choice.id, ref: action.choice.ref })
      announce(
        `Reference ${action.choice.ref.input} on ${action.choice.id} set to ${action.choice.ref.to}.`,
      )
    } else if (action.kind === 'choose') setPending({ choices: action.choices, node: c.target })
  }

  return (
    <div className="canvas-layout">
      <section className="canvas" aria-label="Diagram of resources">
        <ReactFlow
          nodes={nodes}
          edges={flow.edges}
          onNodesChange={onNodesChange}
          // Removing is done in the list view; a canvas-only delete would not reach the model.
          deleteKeyCode={null}
          isValidConnection={(c) =>
            connectionOptions(project, catalog, c.source, c.target).length > 0
          }
          onConnect={onConnect}
          fitView
        >
          <Background />
          <Controls />
        </ReactFlow>
      </section>
      <ListView />
      {pending && (
        <ReferenceDialog
          title="Which reference does this connection set?"
          choices={pending.choices}
          onClose={() => setPending(null)}
          returnFocus={() => focusNode(pending.node)}
        />
      )}
    </div>
  )
}
