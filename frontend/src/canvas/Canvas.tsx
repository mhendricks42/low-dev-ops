import {
  Background,
  Controls,
  ReactFlow,
  useNodesState,
  type Connection,
  type Node,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useEffect, useMemo, useState } from 'react'
import { useStore } from '../model/store'
import { connectionOptions, toFlow, type NodeData } from './flow'
import { ListView } from './ListView'
import { ReferenceDialog, type Choice } from './ReferenceDialog'

export function Canvas() {
  const { project, catalog, dispatch } = useStore()
  const flow = useMemo(() => toFlow(project, catalog), [project, catalog])
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<NodeData>>(flow.nodes)
  const [choices, setChoices] = useState<Choice[] | null>(null)

  // The model is the source of truth; local node state only exists to animate dragging.
  useEffect(() => setNodes(flow.nodes), [flow.nodes, setNodes])

  const options = (c: Connection | { source: string; target: string }) =>
    connectionOptions(project, catalog, c.source, c.target)

  function onConnect(c: Connection) {
    const found = options(c)
    if (found.length === 1 && found[0])
      dispatch({ type: 'setRef', id: found[0].id, ref: found[0].ref })
    else if (found.length > 1) setChoices(found)
  }

  return (
    <div className="canvas-layout">
      <div className="canvas" aria-label="Diagram of resources" role="region">
        <ReactFlow
          nodes={nodes}
          edges={flow.edges}
          onNodesChange={onNodesChange}
          onNodeDragStop={(_, node) =>
            !node.id.startsWith('custom:') &&
            dispatch({ type: 'moveNode', id: node.id, x: node.position.x, y: node.position.y })
          }
          isValidConnection={(c) => options(c).length > 0}
          onConnect={onConnect}
          fitView
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>
      <ListView />
      {choices && (
        <ReferenceDialog
          title="Which reference does this connection set?"
          choices={choices}
          onClose={() => setChoices(null)}
        />
      )}
    </div>
  )
}
