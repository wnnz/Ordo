<script setup lang="ts">
import { ref } from 'vue'
import { Folder, Pencil, Trash2 } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import ActionCard from '@/volt/ActionCard.vue'
import IconButton from '@/volt/IconButton.vue'

export type WorkflowFolderSummary = {
  id: string
  name: string
  workflow_count: number
  created_at: string
  updated_at: string
}

defineProps<{ folder: WorkflowFolderSummary; canEdit?: boolean }>()
const emit = defineEmits<{
  select: []
  rename: []
  remove: []
  dropWorkflow: [workflowId: string]
}>()
const { t } = useI18n()
const dragOver = ref(false)

function leaveDropTarget(event: DragEvent) {
  const next = event.relatedTarget as Node | null
  if (next && (event.currentTarget as HTMLElement).contains(next)) return
  dragOver.value = false
}

function dropWorkflow(event: DragEvent) {
  dragOver.value = false
  const workflowId = event.dataTransfer?.getData('application/x-ordo-workflow')
    || event.dataTransfer?.getData('text/plain')
  if (workflowId) emit('dropWorkflow', workflowId)
}
</script>

<template>
  <div
    class="relative rounded-xl transition"
    :class="dragOver && 'ring-2 ring-[var(--primary)] ring-offset-2 ring-offset-[var(--background)]'"
    @dragenter.prevent="canEdit && (dragOver = true)"
    @dragover.prevent
    @dragleave="leaveDropTarget"
    @drop.prevent="canEdit && dropWorkflow($event)"
  >
    <ActionCard class="min-h-32 w-full p-4" @click="emit('select')">
      <div class="flex items-center gap-3 pr-20">
        <span class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-amber-100 text-amber-600 dark:bg-amber-950/40 dark:text-amber-300"><Folder :size="23" /></span>
        <div class="min-w-0">
          <h2 class="truncate font-semibold">{{ folder.name }}</h2>
          <p class="muted mt-1 text-sm">{{ t('studio.folderItemCount', { count: folder.workflow_count }) }}</p>
        </div>
      </div>
      <p class="muted mt-5 border-t border-[var(--border)] pt-3 text-xs">{{ t('studio.dropHere') }}</p>
    </ActionCard>
    <div v-if="canEdit" class="absolute right-4 top-3 z-10 flex gap-1">
      <IconButton :label="t('studio.renameFolder', { name: folder.name })" surface @click="emit('rename')"><Pencil :size="14" /></IconButton>
      <IconButton
        :label="folder.workflow_count ? t('studio.nonEmptyFolder') : t('studio.deleteFolder', { name: folder.name })"
        :disabled="folder.workflow_count > 0"
        tone="danger"
        surface
        @click="emit('remove')"
      ><Trash2 :size="14" /></IconButton>
    </div>
  </div>
</template>
