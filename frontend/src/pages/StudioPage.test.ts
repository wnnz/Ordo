// @vitest-environment jsdom

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import api from '@/api/client'
import WorkflowCard from '@/components/studio/WorkflowCard.vue'
import WorkflowFolderCard from '@/components/studio/WorkflowFolderCard.vue'
import StudioPage from './StudioPage.vue'

const { push, route, workspaces } = vi.hoisted(() => ({
  push: vi.fn(),
  route: { query: {} as Record<string, string> },
  workspaces: {
    activeId: 'workspace-1',
    active: { id: 'workspace-1', role: 'owner' },
  },
}))

vi.mock('@/api/client', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
vi.mock('@/components/AppShell.vue', () => ({ default: { template: '<main><slot /></main>' } }))
vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => ({ push }) }))
vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, string>) => params?.name ? `${key}:${params.name}` : key,
  }),
}))
vi.mock('@/stores/workspaces', () => ({ useWorkspacesStore: () => workspaces }))

const workflow = {
  id: 'workflow-1',
  name: 'Disposable workflow',
  description: 'Temporary app',
  app_type: 'workflow',
  draft_version: 2,
  folder_id: null,
  published_version_id: 'version-1',
  updated_at: '2026-08-06T00:00:00Z',
}

const folder = {
  id: 'folder-1',
  name: 'Operations',
  workflow_count: 0,
  created_at: '2026-08-06T00:00:00Z',
  updated_at: '2026-08-06T00:00:00Z',
}

function mountPage() {
  return mount(StudioPage, {
    global: {
      stubs: {
        PageHeader: { template: '<header><slot name="actions" /></header>' },
        FilterDropdown: { template: '<div />' },
        SearchInput: {
          props: ['modelValue'],
          emits: ['update:modelValue'],
          template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
        },
        EmptyState: { template: '<div><slot name="icon" /></div>' },
        FormField: { template: '<label><slot /></label>' },
        InputText: { template: '<input />' },
        Textarea: { template: '<textarea />' },
        AlertBanner: { props: ['message'], template: '<p v-if="message">{{ message }}</p>' },
        Button: {
          props: ['disabled', 'loading'],
          emits: ['click'],
          template: '<button :disabled="disabled || loading" @click="$emit(\'click\')"><slot /></button>',
        },
        IconButton: {
          props: ['label'],
          emits: ['click'],
          template: '<button :aria-label="label" @click="$emit(\'click\')"><slot /></button>',
        },
        ModalShell: {
          props: ['modelValue', 'title'],
          emits: ['update:modelValue', 'submit'],
          template: '<section v-if="modelValue" role="dialog" :aria-label="title"><slot /><footer><slot name="footer" /></footer></section>',
        },
      },
    },
  })
}

describe('StudioPage workflow deletion', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset().mockImplementation(async url => ({
      data: String(url).endsWith('/folders') ? [] : [workflow],
    }))
    vi.mocked(api.patch).mockReset()
    vi.mocked(api.delete).mockReset().mockResolvedValue({ data: { message: 'deleted' } })
    push.mockReset()
    route.query = {}
    workspaces.active.role = 'owner'
  })

  it('confirms deletion without navigating through the workflow card', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('button[aria-label="studio.deleteApp:Disposable workflow"]').trigger('click')
    expect(push).not.toHaveBeenCalled()
    expect(wrapper.get('[role="dialog"]').attributes('aria-label')).toBe('studio.deleteTitle')

    const confirm = wrapper.findAll('button').find(button => button.text() === 'common.delete')
    expect(confirm).toBeTruthy()
    await confirm!.trigger('click')
    await flushPromises()

    expect(api.delete).toHaveBeenCalledWith('/workspaces/workspace-1/workflows/workflow-1')
    expect(wrapper.text()).not.toContain('Disposable workflow')
  })

  it('does not expose create or delete actions to viewers', async () => {
    workspaces.active.role = 'viewer'
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.find('button[aria-label="studio.deleteApp:Disposable workflow"]').exists()).toBe(false)
    expect(wrapper.findAll('button').some(button => button.text() === 'studio.newApp')).toBe(false)
  })
})

describe('StudioPage app type selection', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset().mockResolvedValue({ data: [] })
    push.mockReset()
    route.query = {}
    workspaces.active.role = 'owner'
  })

  it('shows the selected app type and updates it when clicked', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const createButton = wrapper.findAll('button').find(button => button.text() === 'studio.newApp')
    expect(createButton).toBeTruthy()
    await createButton!.trigger('click')

    const workflow = wrapper.get('button[aria-pressed="true"]')
    expect(workflow.text()).toContain('studio.workflow')
    expect(workflow.find('svg').exists()).toBe(true)
    expect(wrapper.get('button[aria-pressed="false"]').text()).toContain('studio.chat')

    await wrapper.get('button[aria-pressed="false"]').trigger('click')

    expect(wrapper.get('button[aria-pressed="true"]').text()).toContain('studio.chat')
    expect(wrapper.get('button[aria-pressed="false"]').text()).toContain('studio.workflow')
  })
})

describe('StudioPage workflow folders', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset().mockImplementation(async url => ({
      data: String(url).endsWith('/folders') ? [folder] : [workflow],
    }))
    vi.mocked(api.patch).mockReset().mockResolvedValue({
      data: { ...workflow, folder_id: folder.id },
    })
    push.mockReset()
    route.query = {}
    workspaces.active.role = 'owner'
  })

  it('opens a folder through the route query and moves a workflow dropped on it', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const folderCard = wrapper.getComponent(WorkflowFolderCard)
    folderCard.vm.$emit('select')
    expect(push).toHaveBeenCalledWith({ query: { folder: folder.id } })

    folderCard.vm.$emit('dropWorkflow', workflow.id)
    await flushPromises()
    expect(api.patch).toHaveBeenCalledWith(
      '/workspaces/workspace-1/workflows/workflow-1/folder',
      { folder_id: folder.id },
    )
  })

  it('shows all matching workflows during search and identifies their folder', async () => {
    vi.mocked(api.get).mockImplementation(async url => ({
      data: String(url).endsWith('/folders') ? [folder] : [{ ...workflow, folder_id: folder.id }],
    }))
    const wrapper = mountPage()
    await flushPromises()

    const searchInput = wrapper.get('input')
    await searchInput.setValue('Disposable')
    expect(wrapper.getComponent(WorkflowCard).props('folderName')).toBe('Operations')
  })

  it('does not enable folder management or dragging for viewers', async () => {
    workspaces.active.role = 'viewer'
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.getComponent(WorkflowFolderCard).props('canEdit')).toBe(false)
    expect(wrapper.getComponent(WorkflowCard).props('canEdit')).toBe(false)
    expect(wrapper.findAll('button').some(button => button.text() === 'studio.newFolder')).toBe(false)
  })
})
