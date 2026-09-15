// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import WorkflowCard from './WorkflowCard.vue'
import WorkflowFolderCard from './WorkflowFolderCard.vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, string | number>) => (
      params?.name ? `${key}:${params.name}` : params?.count !== undefined ? `${key}:${params.count}` : key
    ),
  }),
}))

const workflow = {
  id: 'workflow-1',
  name: 'Workflow one',
  app_type: 'workflow',
  draft_version: 1,
  updated_at: '2026-09-14T00:00:00Z',
}
const folder = {
  id: 'folder-1',
  name: 'Operations',
  workflow_count: 0,
  created_at: '2026-09-14T00:00:00Z',
  updated_at: '2026-09-14T00:00:00Z',
}

describe('workflow folder drag and drop', () => {
  it('writes the workflow id when an editor starts dragging a card', async () => {
    const setData = vi.fn()
    const wrapper = mount(WorkflowCard, { props: { workflow, canEdit: true } })

    await wrapper.trigger('dragstart', { dataTransfer: { setData, effectAllowed: '' } })

    expect(wrapper.attributes('draggable')).toBe('true')
    expect(setData).toHaveBeenCalledWith('application/x-ordo-workflow', workflow.id)
  })

  it('emits the dropped workflow id and blocks deletion while non-empty', async () => {
    const wrapper = mount(WorkflowFolderCard, { props: { folder, canEdit: true } })
    await wrapper.trigger('drop', {
      dataTransfer: { getData: (type: string) => type === 'application/x-ordo-workflow' ? workflow.id : '' },
    })
    expect(wrapper.emitted('dropWorkflow')).toEqual([[workflow.id]])

    await wrapper.setProps({ folder: { ...folder, workflow_count: 1 } })
    expect(wrapper.get('button[aria-label="studio.nonEmptyFolder"]').attributes('disabled')).toBeDefined()
  })
})
