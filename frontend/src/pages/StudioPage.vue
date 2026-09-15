<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { Bot, Check, ChevronRight, CircleAlert, Clock3, FolderInput, FolderPlus, Plus, Tags, Trash2, Workflow as WorkflowIcon } from 'lucide-vue-next'
import api from '@/api/client'
import AppShell from '@/components/AppShell.vue'
import WorkflowCard, { type WorkflowSummary } from '@/components/studio/WorkflowCard.vue'
import WorkflowFolderCard, { type WorkflowFolderSummary } from '@/components/studio/WorkflowFolderCard.vue'
import AlertBanner from '@/components/ui/AlertBanner.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import FilterDropdown from '@/components/ui/FilterDropdown.vue'
import FormField from '@/components/ui/FormField.vue'
import ModalShell from '@/components/ui/ModalShell.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import SearchInput from '@/components/ui/SearchInput.vue'
import { useToast } from '@/composables/useToast'
import { useWorkspacesStore } from '@/stores/workspaces'
import ActionCard from '@/volt/ActionCard.vue'
import Button from '@/volt/Button.vue'
import InputText from '@/volt/InputText.vue'
import Textarea from '@/volt/Textarea.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const toast = useToast()
const workspaces = useWorkspacesStore()
const items = ref<WorkflowSummary[]>([])
const folders = ref<WorkflowFolderSummary[]>([])
const search = ref('')
const type = ref('all')
const status = ref('all')
const newestFirst = ref(true)
const showCreate = ref(false)
const creating = ref(false)
const createError = ref('')
const pendingDelete = ref<WorkflowSummary | null>(null)
const deleting = ref(false)
const deleteError = ref('')
const movingItem = ref<WorkflowSummary | null>(null)
const folderEditor = ref<WorkflowFolderSummary | 'new' | null>(null)
const folderName = ref('')
const folderSaving = ref(false)
const folderError = ref('')
const pendingFolderDelete = ref<WorkflowFolderSummary | null>(null)
const folderDeleting = ref(false)
const rootDragOver = ref(false)
const form = ref({ name: '', description: '', app_type: 'workflow', template_id: undefined as string | undefined })

const canEdit = computed(() => ['owner', 'admin', 'editor'].includes(workspaces.active?.role || ''))
const currentFolderId = computed(() => typeof route.query.folder === 'string' ? route.query.folder : null)
const currentFolder = computed(() => folders.value.find(folder => folder.id === currentFolderId.value) || null)
const isSearching = computed(() => Boolean(search.value.trim()))
const folderNames = computed<Record<string, string>>(() => Object.fromEntries(folders.value.map(folder => [folder.id, folder.name])))
const visibleFolders = computed(() => currentFolderId.value || isSearching.value ? [] : folders.value)
const filtered = computed(() => {
  const needle = search.value.trim().toLocaleLowerCase()
  return items.value.filter(item => {
    const inLocation = isSearching.value || (currentFolderId.value ? item.folder_id === currentFolderId.value : !item.folder_id)
    const matchesSearch = !needle || item.name.toLocaleLowerCase().includes(needle) || String(item.description || '').toLocaleLowerCase().includes(needle)
    return inLocation && matchesSearch
      && (type.value === 'all' || item.app_type === type.value)
      && (status.value === 'all' || (status.value === 'published') === Boolean(item.published_version_id))
  }).sort((a, b) => (
    new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
  ) * (newestFirst.value ? 1 : -1))
})
const typeOptions = computed(() => ['all', 'workflow', 'chat'].map(value => ({ value, label: value === 'all' ? t('studio.all') : t(`studio.${value}`) })))
const statusOptions = computed(() => ['all', 'published', 'draft'].map(value => ({ value, label: value === 'all' ? t('studio.allStatuses') : t(`studio.${value}`) })))

async function load() {
  if (!workspaces.activeId) {
    items.value = []
    folders.value = []
    return
  }
  const base = `/workspaces/${workspaces.activeId}/workflows`
  const [workflowResponse, folderResponse] = await Promise.all([api.get(base), api.get(`${base}/folders`)])
  items.value = workflowResponse.data
  folders.value = folderResponse.data
  if (currentFolderId.value && !folders.value.some(folder => folder.id === currentFolderId.value)) await goToRoot()
}

async function create() {
  creating.value = true
  createError.value = ''
  try {
    const { data } = await api.post(`/workspaces/${workspaces.activeId}/workflows`, form.value)
    showCreate.value = false
    await router.push(`/w/${workspaces.activeId}/workflows/${data.id}`)
  } catch (cause: any) {
    createError.value = cause.response?.data?.detail || String(cause)
  } finally {
    creating.value = false
  }
}

function requestDelete(item: WorkflowSummary) {
  pendingDelete.value = item
  deleteError.value = ''
}
function closeDelete() {
  if (!deleting.value) pendingDelete.value = null
}
async function confirmDelete() {
  if (!pendingDelete.value || deleting.value) return
  deleting.value = true
  deleteError.value = ''
  try {
    await api.delete(`/workspaces/${workspaces.activeId}/workflows/${pendingDelete.value.id}`)
    const deletedId = pendingDelete.value.id
    pendingDelete.value = null
    items.value = items.value.filter(item => item.id !== deletedId)
    syncFolderCounts()
  } catch (cause: any) {
    deleteError.value = cause.response?.data?.detail || String(cause)
  } finally {
    deleting.value = false
  }
}

function openFolder(folder: WorkflowFolderSummary) {
  void router.push({ query: { ...route.query, folder: folder.id } })
}
function goToRoot() {
  const query = { ...route.query }
  delete query.folder
  return router.push({ query })
}
function openFolderEditor(folder: WorkflowFolderSummary | 'new') {
  folderEditor.value = folder
  folderName.value = folder === 'new' ? '' : folder.name
  folderError.value = ''
}
function closeFolderEditor() {
  if (!folderSaving.value) folderEditor.value = null
}
async function saveFolder() {
  if (!folderEditor.value || folderSaving.value) return
  folderSaving.value = true
  folderError.value = ''
  const base = `/workspaces/${workspaces.activeId}/workflows/folders`
  try {
    if (folderEditor.value === 'new') {
      const { data } = await api.post(base, { name: folderName.value })
      folders.value = [...folders.value, data]
      toast.success(t('studio.folderCreated'))
    } else {
      const { data } = await api.patch(`${base}/${folderEditor.value.id}`, { name: folderName.value })
      folders.value = folders.value.map(folder => folder.id === data.id ? data : folder)
      toast.success(t('studio.folderRenamed'))
    }
    folders.value.sort((a, b) => a.name.localeCompare(b.name))
    folderEditor.value = null
  } catch (cause: any) {
    folderError.value = cause.response?.data?.detail || String(cause)
  } finally {
    folderSaving.value = false
  }
}
function requestFolderDelete(folder: WorkflowFolderSummary) {
  if (folder.workflow_count) return
  pendingFolderDelete.value = folder
  folderError.value = ''
}
async function confirmFolderDelete() {
  if (!pendingFolderDelete.value || folderDeleting.value) return
  folderDeleting.value = true
  folderError.value = ''
  try {
    const deletedId = pendingFolderDelete.value.id
    await api.delete(`/workspaces/${workspaces.activeId}/workflows/folders/${deletedId}`)
    folders.value = folders.value.filter(folder => folder.id !== deletedId)
    pendingFolderDelete.value = null
    toast.success(t('studio.folderDeleted'))
  } catch (cause: any) {
    folderError.value = cause.response?.data?.detail || String(cause)
  } finally {
    folderDeleting.value = false
  }
}

function syncFolderCounts() {
  const counts = new Map<string, number>()
  for (const item of items.value) if (item.folder_id) counts.set(item.folder_id, (counts.get(item.folder_id) || 0) + 1)
  folders.value = folders.value.map(folder => ({ ...folder, workflow_count: counts.get(folder.id) || 0 }))
}
async function moveWorkflow(workflowId: string, folderId: string | null) {
  if (!canEdit.value) return
  const index = items.value.findIndex(item => item.id === workflowId)
  if (index < 0 || items.value[index].folder_id === folderId) {
    movingItem.value = null
    return
  }
  const previous = items.value[index]
  items.value[index] = { ...previous, folder_id: folderId }
  syncFolderCounts()
  try {
    const { data } = await api.patch(`/workspaces/${workspaces.activeId}/workflows/${workflowId}/folder`, { folder_id: folderId })
    items.value[index] = data
    syncFolderCounts()
    toast.success(folderId ? t('studio.movedToFolder') : t('studio.movedToRoot'))
    movingItem.value = null
  } catch (cause: any) {
    items.value[index] = previous
    syncFolderCounts()
    toast.error(cause.response?.data?.detail || String(cause))
  }
}
function dropOnRoot(event: DragEvent) {
  rootDragOver.value = false
  const workflowId = event.dataTransfer?.getData('application/x-ordo-workflow') || event.dataTransfer?.getData('text/plain')
  if (workflowId) void moveWorkflow(workflowId, null)
}

onMounted(load)
watch(() => workspaces.activeId, load)
</script>

<template>
  <AppShell>
    <div class="px-7 py-5">
      <PageHeader :title="t('studio.title')" :subtitle="t('studio.subtitle')">
        <template #actions>
          <Button v-if="canEdit" variant="secondary" @click="openFolderEditor('new')"><FolderPlus :size="16" />{{ t('studio.newFolder') }}</Button>
          <Button v-if="canEdit" @click="showCreate = true"><Plus :size="16" />{{ t('studio.newApp') }}</Button>
        </template>
      </PageHeader>

      <nav v-if="currentFolder" class="mt-5 flex items-center gap-1 text-sm" :aria-label="t('studio.folderBreadcrumb')">
        <button type="button" class="focus-ring rounded-md px-2 py-1.5 text-[var(--muted)] hover:bg-[var(--panel-subtle)] hover:text-[var(--text)]" :class="rootDragOver && 'bg-[var(--primary-soft)] !text-[var(--primary)] ring-2 ring-[var(--primary)]'" @click="goToRoot" @dragenter.prevent="canEdit && (rootDragOver = true)" @dragover.prevent @dragleave="rootDragOver = false" @drop.prevent="canEdit && dropOnRoot($event)">{{ t('studio.allApps') }}</button>
        <ChevronRight :size="14" class="muted" /><span class="font-medium">{{ currentFolder.name }}</span>
      </nav>

      <div class="mt-5 flex flex-wrap items-center gap-2">
        <FilterDropdown v-model="type" :options="typeOptions" />
        <FilterDropdown v-model="status" :options="statusOptions"><template #icon><Tags :size="14" /></template></FilterDropdown>
        <Button variant="secondary" @click="newestFirst = !newestFirst"><Clock3 :size="14" />{{ newestFirst ? t('studio.recent') : t('studio.oldest') }}</Button>
        <SearchInput v-model="search" class="ml-1 w-64" :placeholder="t('common.search')" />
      </div>

      <section v-if="visibleFolders.length" class="mt-5" :aria-label="t('studio.folders')">
        <h2 class="mb-2 text-sm font-semibold">{{ t('studio.folders') }}</h2>
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          <WorkflowFolderCard v-for="folder in visibleFolders" :key="folder.id" :folder="folder" :can-edit="canEdit" @select="openFolder(folder)" @rename="openFolderEditor(folder)" @remove="requestFolderDelete(folder)" @drop-workflow="moveWorkflow($event, folder.id)" />
        </div>
      </section>

      <section v-if="filtered.length" class="mt-5" :aria-label="t('studio.apps')">
        <h2 v-if="visibleFolders.length" class="mb-2 text-sm font-semibold">{{ t('studio.apps') }}</h2>
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          <WorkflowCard v-for="item in filtered" :key="item.id" :workflow="item" :can-edit="canEdit" :folder-name="isSearching && item.folder_id ? folderNames[item.folder_id] : undefined" @select="router.push(`/w/${workspaces.activeId}/workflows/${item.id}`)" @move="movingItem = item" @remove="requestDelete(item)" />
        </div>
      </section>
      <EmptyState v-if="!visibleFolders.length && !filtered.length" class="mt-16" :title="currentFolder && !isSearching ? t('studio.emptyFolder') : t('studio.noResults')"><template #icon><WorkflowIcon :size="42" /></template></EmptyState>

      <ModalShell v-model="showCreate" :title="t('studio.newApp')" form @submit="create">
        <AlertBanner :message="createError" tone="error" />
        <div class="grid grid-cols-2 gap-2">
          <ActionCard class="relative p-3 pr-10" :active="form.app_type === 'workflow'" :aria-pressed="form.app_type === 'workflow'" @click="form.app_type = 'workflow'"><WorkflowIcon :size="18" /><div class="mt-2 text-sm font-medium">{{ t('studio.workflow') }}</div><span v-if="form.app_type === 'workflow'" aria-hidden="true" class="absolute right-2 top-2 flex h-5 w-5 items-center justify-center rounded-full bg-[var(--primary)] text-white"><Check :size="12" :stroke-width="3" /></span></ActionCard>
          <ActionCard class="relative p-3 pr-10" :active="form.app_type === 'chat'" :aria-pressed="form.app_type === 'chat'" @click="form.app_type = 'chat'"><Bot :size="18" /><div class="mt-2 text-sm font-medium">{{ t('studio.chat') }}</div><span v-if="form.app_type === 'chat'" aria-hidden="true" class="absolute right-2 top-2 flex h-5 w-5 items-center justify-center rounded-full bg-[var(--primary)] text-white"><Check :size="12" :stroke-width="3" /></span></ActionCard>
        </div>
        <FormField class="mt-4" :label="t('common.name')" required><InputText v-model="form.name" required /></FormField>
        <FormField class="mt-4" :label="t('common.description')"><Textarea v-model="form.description" class="h-20" /></FormField>
        <template #footer><Button type="button" variant="secondary" @click="showCreate = false">{{ t('common.cancel') }}</Button><Button type="submit" :loading="creating">{{ t('common.create') }}</Button></template>
      </ModalShell>

      <ModalShell :model-value="Boolean(pendingDelete)" :title="t('studio.deleteTitle')" @update:model-value="closeDelete">
        <AlertBanner :message="deleteError" tone="error" />
        <div class="flex items-start gap-3 rounded-lg bg-red-50 p-4 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300"><CircleAlert class="mt-0.5 shrink-0" :size="18" /><div><p class="font-semibold">{{ t('studio.confirmDelete', { name: pendingDelete?.name || '' }) }}</p><p class="mt-1 text-xs leading-5">{{ t('studio.deleteWarning') }}</p></div></div>
        <template #footer><Button type="button" variant="secondary" :disabled="deleting" @click="closeDelete">{{ t('common.cancel') }}</Button><Button type="button" variant="danger" :loading="deleting" @click="confirmDelete"><Trash2 :size="15" />{{ t('common.delete') }}</Button></template>
      </ModalShell>

      <ModalShell :model-value="Boolean(folderEditor)" :title="folderEditor === 'new' ? t('studio.newFolder') : t('studio.editFolder')" form @update:model-value="closeFolderEditor" @submit="saveFolder">
        <AlertBanner :message="folderError" tone="error" />
        <FormField :label="t('studio.folderName')" required><InputText v-model="folderName" required maxlength="120" autofocus /></FormField>
        <template #footer><Button type="button" variant="secondary" :disabled="folderSaving" @click="closeFolderEditor">{{ t('common.cancel') }}</Button><Button type="submit" :loading="folderSaving">{{ t('common.save') }}</Button></template>
      </ModalShell>

      <ModalShell :model-value="Boolean(pendingFolderDelete)" :title="t('studio.deleteFolderTitle')" @update:model-value="!folderDeleting && (pendingFolderDelete = null)">
        <AlertBanner :message="folderError" tone="error" /><p>{{ t('studio.confirmFolderDelete', { name: pendingFolderDelete?.name || '' }) }}</p>
        <template #footer><Button type="button" variant="secondary" :disabled="folderDeleting" @click="pendingFolderDelete = null">{{ t('common.cancel') }}</Button><Button type="button" variant="danger" :loading="folderDeleting" @click="confirmFolderDelete"><Trash2 :size="15" />{{ t('common.delete') }}</Button></template>
      </ModalShell>

      <ModalShell :model-value="Boolean(movingItem)" :title="t('studio.moveAppTitle', { name: movingItem?.name || '' })" @update:model-value="movingItem = null">
        <div class="grid gap-2 sm:grid-cols-2">
          <ActionCard class="p-3" :active="!movingItem?.folder_id" @click="movingItem && moveWorkflow(movingItem.id, null)"><FolderInput :size="18" /><div class="mt-2 text-sm font-medium">{{ t('studio.allApps') }}</div></ActionCard>
          <ActionCard v-for="folder in folders" :key="folder.id" class="p-3" :active="movingItem?.folder_id === folder.id" @click="movingItem && moveWorkflow(movingItem.id, folder.id)"><FolderInput :size="18" /><div class="mt-2 truncate text-sm font-medium">{{ folder.name }}</div></ActionCard>
        </div>
        <template #footer><Button type="button" variant="secondary" @click="movingItem = null">{{ t('common.cancel') }}</Button></template>
      </ModalShell>
    </div>
  </AppShell>
</template>
