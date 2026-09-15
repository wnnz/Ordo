<script setup lang="ts">
import { Bot, FolderInput, Trash2, Workflow as WorkflowIcon } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import ActionCard from '@/volt/ActionCard.vue'
import IconButton from '@/volt/IconButton.vue'

export type WorkflowSummary = {
  id: string
  name: string
  description?: string | null
  app_type: string
  draft_version: number
  folder_id?: string | null
  published_version_id?: string | null
  updated_at: string
}

const props = defineProps<{
  workflow: WorkflowSummary
  canEdit?: boolean
  folderName?: string
}>()
const emit = defineEmits<{
  select: []
  remove: []
  move: []
}>()
const { t } = useI18n()

function startDrag(event: DragEvent) {
  if (!props.canEdit || !event.dataTransfer) return
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('application/x-ordo-workflow', props.workflow.id)
  event.dataTransfer.setData('text/plain', props.workflow.id)
}
</script>

<template>
  <div class="relative" :draggable="Boolean(canEdit)" @dragstart="startDrag">
    <ActionCard class="min-h-40 w-full p-4" @click="emit('select')">
      <div class="flex gap-3 pr-20">
        <span class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[var(--primary-soft)] text-violet-600">
          <Bot v-if="workflow.app_type === 'chat'" :size="21" />
          <WorkflowIcon v-else :size="21" />
        </span>
        <div class="min-w-0">
          <h2 class="truncate font-semibold">{{ workflow.name }}</h2>
          <p class="muted mt-1 line-clamp-2 text-sm">{{ workflow.description || t('studio.noApps') }}</p>
          <span v-if="folderName" class="mt-2 inline-flex rounded-md bg-[var(--panel-subtle)] px-2 py-0.5 text-xs text-[var(--muted)]">{{ folderName }}</span>
        </div>
      </div>
      <div class="muted mt-7 flex items-center justify-between border-t border-[var(--border)] pt-3 text-xs">
        <span>v{{ workflow.draft_version }} · {{ new Date(workflow.updated_at).toLocaleDateString() }}</span>
        <span :class="workflow.published_version_id ? 'text-emerald-600' : ''">{{ workflow.published_version_id ? t('studio.published') : t('studio.draft') }}</span>
      </div>
    </ActionCard>
    <div v-if="canEdit" class="absolute right-4 top-3 z-10 flex gap-1">
      <IconButton :label="t('studio.moveApp', { name: workflow.name })" surface @click="emit('move')"><FolderInput :size="15" /></IconButton>
      <IconButton :label="t('studio.deleteApp', { name: workflow.name })" tone="danger" surface @click="emit('remove')"><Trash2 :size="15" /></IconButton>
    </div>
  </div>
</template>
