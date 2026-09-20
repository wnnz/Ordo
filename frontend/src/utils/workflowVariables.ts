import type { WorkflowEdgeLike, WorkflowNodeLike } from './workflowGraph'
import { nodeReferenceName } from './workflowNodeNames'
import { workflowTypeForScriptSchema } from './scriptSchema'

export type WorkflowVariable = {
  path: string
  label: string
  type: string
}

export type WorkflowVariableGroup = {
  nodeId: string
  label: string
  variables: WorkflowVariable[]
}

function filenameStem(filename: string) {
  const name = filename.replace(/\\/g, '/').split('/').pop() || ''
  const suffix = name.lastIndexOf('.')
  return suffix > 0 ? name.slice(0, suffix) : name
}

function nodeType(node: WorkflowNodeLike) {
  return String(node.data?.nodeType || node.type || '')
}

export function getNodeOutputVariables(node: WorkflowNodeLike): WorkflowVariable[] {
  const type = nodeType(node)
  const config = node.data?.config || {}
  const prefix = nodeReferenceName(node) || node.id
  const fixed: Record<string, Array<[string, string]>> = {
    llm: [['text', 'String']],
    image: [['images', 'Array[File]'], ['count', 'Number'], ['size', 'String'], ['model', 'String']],
    agent: [['text', 'String'], ['tool_calls', 'Array']],
    classifier: [['class_id', 'String'], ['class_name', 'String'], ['confidence', 'Number'], ['fallback', 'Boolean']],
    template: [['text', 'String']],
    json: [['value', 'Object']],
    list: [['items', 'Array'], ['item', 'Any']],
    http: [['status_code', 'Number'], ['body', 'Object'], ['headers', 'Object'], ['url', 'String'], ['elapsed_ms', 'Number'], ['ok', 'Boolean']],
    condition: [['result', 'Boolean'], ['branch', 'String'], ['clauses', 'Array[Boolean]']],
    human: [['approved', 'Boolean'], ['comment', 'String']],
    iteration: [['results', 'Array']],
    loop: [['result', 'Object']],
    wait: [['completed', 'Boolean'], ['mode', 'String']],
    delay: [['completed_at', 'String']],
    subworkflow: [['output', 'Object']],
    answer_filler: [['file', 'File'], ['inserted_count', 'Number'], ['requested_count', 'Number'], ['insertions', 'Array[Object]']],
    rdp_disconnect: [['ok', 'Boolean'], ['disconnected_count', 'Number'], ['sessions', 'Array[Object]'], ['failed', 'Array[Object]'], ['message', 'String'], ['source', 'String']],
  }

  const withErrorVariables = (variables: WorkflowVariable[]) => {
    if (config.error_strategy === 'error_branch') variables.push(
      { path: `${prefix}.error_type`, label: 'error_type', type: 'String' },
      { path: `${prefix}.error_message`, label: 'error_message', type: 'String' },
    )
    return variables
  }

  if (type === 'document') {
    const outputs: Record<string, Array<[string, string]>> = {
      extract: [['content', 'String'], ['tables', 'Array[Object]'], ['images', 'Array[File]']],
    }
    return withErrorVariables((outputs[config.operation || 'extract'] || outputs.extract).map(([label, variableType]) => ({ path: `${prefix}.${label}`, label, type: variableType })))
  }

  if (type === 'llm' && config.response_format === 'json_schema') {
    const properties = config.response_schema?.properties || {}
    return withErrorVariables([
      { path: `${prefix}.text`, label: 'text', type: 'String' },
      ...(config.reasoning?.separate ? [{ path: `${prefix}.reasoning_content`, label: 'reasoning_content', type: 'String' }] : []),
      { path: `${prefix}.structured_output`, label: 'structured_output', type: 'Object' },
      ...Object.entries(properties).map(([name, schema]: [string, any]) => ({ path: `${prefix}.structured_output.${name}`, label: name, type: String(schema?.type || 'Any') })),
    ])
  }

  if (type === 'variable') {
    const assignments = Array.isArray(config.assignments) ? config.assignments : []
    const outputs: Array<[string, string]> = assignments.length
      ? assignments.filter((item: any) => item?.name).map((item: any) => [String(item.name), String(item.type || 'Any')] as [string, string])
      : Object.keys(config.values || {}).map(key => [key, 'Any'] as [string, string])
    return withErrorVariables(outputs.map(([key, valueType]) => ({ path: `${prefix}.${key}`, label: key, type: valueType })))
  }
  if (type === 'code') {
    const outputs = (config.outputs || []).filter((item: any) => item?.name).map((item: any) => ({ path: `${prefix}.${item.name}`, label: item.name, type: item.type || 'Any' }))
    return withErrorVariables([
      ...outputs,
      { path: `${prefix}._logs`, label: '_logs', type: 'Array[String]' },
      { path: `${prefix}._elapsed_ms`, label: '_elapsed_ms', type: 'Number' },
    ])
  }
  if (type === 'script') {
    const properties = config.output_schema?.properties || {}
    return withErrorVariables([
      ...Object.entries(properties).map(([name, schema]) => ({
        path: `${prefix}.${name}`,
        label: name,
        type: workflowTypeForScriptSchema(schema as Record<string, any>),
      })),
      { path: `${prefix}._logs`, label: '_logs', type: 'Array[String]' },
      { path: `${prefix}._elapsed_ms`, label: '_elapsed_ms', type: 'Number' },
    ])
  }
  if (type === 'aggregate') {
    const variables: WorkflowVariable[] = config.group_enabled
      ? (config.groups || []).filter((group: any) => group?.name).map((group: any) => ({ path: `${prefix}.${group.name}`, label: group.name, type: 'Any' }))
      : [{ path: `${prefix}.output`, label: 'output', type: 'Any' }]
    return withErrorVariables(variables)
  }
  if (type === 'extract') {
    return withErrorVariables((config.fields || []).filter((field: any) => field?.name).map((field: any) => ({ path: `${prefix}.${field.name}`, label: field.name, type: field.type || 'String' })))
  }
  const variables = (fixed[type] || []).map(([name, valueType]) => ({ path: `${prefix}.${name}`, label: name, type: valueType }))
  if (type === 'llm' && config.reasoning?.separate) variables.push({ path: `${prefix}.reasoning_content`, label: 'reasoning_content', type: 'String' })
  return withErrorVariables(variables)
}

function variablesForNode(node: WorkflowNodeLike): WorkflowVariable[] {
  const type = nodeType(node)
  if (type === 'start') {
    const prefix = nodeReferenceName(node) || node.id
    return (node.data?.config?.input_fields || []).filter((field: any) => field?.name).flatMap((field: any) => {
      const variable = {
        path: `${prefix}.${field.name}`,
        label: field.label || field.name,
        type: field.type === 'files' ? 'Array[File]' : field.type === 'file' ? 'File' : field.type === 'number' ? 'Number' : 'String',
      }
      if (field.type !== 'file') return [variable]
      return [
        variable,
        { path: `${variable.path}.filename`, label: 'filename', type: 'String' },
        { path: `${variable.path}.stem`, label: 'stem', type: 'String' },
      ]
    })
  }
  return getNodeOutputVariables(node)
}

export function buildAllVariableCatalog(nodes: WorkflowNodeLike[]): WorkflowVariableGroup[] {
  return nodes.filter(node => nodeType(node) !== 'note').map(node => ({
    nodeId: node.id,
    label: String(node.data?.label || nodeType(node)),
    variables: variablesForNode(node),
  })).filter(group => group.variables.length)
}

export function readRuntimeVariable(path: string, nodeResults: Record<string, any>, nodes: WorkflowNodeLike[] = []) {
  const parts = path.split('.').map(part => part.trim())
  let current: any
  if (parts[0] === 'inputs') {
    const startTrace = Object.values(nodeResults).find((trace: any) => trace?.node_type === 'start') as any
    current = startTrace?.output
    parts.shift()
  } else {
    const reference = parts.shift()!
    const node = nodes.find(item => nodeReferenceName(item) === reference)
      || nodes.find(item => nodeReferenceName(item).toLocaleLowerCase() === reference.toLocaleLowerCase())
    current = nodeResults[node?.id || reference]?.output
  }
  for (const part of parts) {
    if (current == null) return undefined
    if (Array.isArray(current) && /^\d+$/.test(part)) current = current[Number(part)]
    else if (typeof current === 'object') {
      current = part === 'stem' && current[part] === undefined && typeof current.filename === 'string'
        ? filenameStem(current.filename)
        : current[part]
    }
    else return undefined
  }
  return current
}

export function buildVariableCatalog(
  nodes: WorkflowNodeLike[],
  edges: WorkflowEdgeLike[],
  targetNodeId: string,
): WorkflowVariableGroup[] {
  const incoming = new Map<string, string[]>()
  for (const edge of edges) incoming.set(edge.target, [...(incoming.get(edge.target) || []), edge.source])

  const ancestors = new Set<string>()
  const pending = [...(incoming.get(targetNodeId) || [])]
  while (pending.length) {
    const id = pending.shift()!
    if (ancestors.has(id)) continue
    ancestors.add(id)
    pending.push(...(incoming.get(id) || []))
  }

  const groups: WorkflowVariableGroup[] = []
  for (const node of nodes) {
    if (!ancestors.has(node.id)) continue
    const type = nodeType(node)
    if (type === 'start') {
      const variables = variablesForNode(node)
      if (variables.length) groups.push({ nodeId: node.id, label: String(node.data?.label || 'Start'), variables })
      continue
    }
    const variables = getNodeOutputVariables(node)
    if (variables.length) groups.push({ nodeId: node.id, label: String(node.data?.label || type), variables })
  }
  return groups
}
