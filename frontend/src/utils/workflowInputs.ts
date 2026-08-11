export type WorkflowInputField = {
  name: string
  type?: 'text' | 'textarea' | 'number' | 'month' | 'select' | 'file' | 'files'
  default_value?: unknown
}

export function createWorkflowInputValues(fields: WorkflowInputField[]) {
  return Object.fromEntries(fields.map(field => {
    if (field.type === 'files') return [field.name, []]
    if (field.type === 'file') return [field.name, null]
    return [field.name, field.default_value ?? '']
  }))
}

export function coerceWorkflowInputValues(fields: WorkflowInputField[], values: Record<string, unknown>) {
  const result = { ...values }
  for (const field of fields) {
    if (field.type === 'number' && result[field.name] !== '' && result[field.name] != null) {
      result[field.name] = Number(result[field.name])
    }
  }
  return result
}
