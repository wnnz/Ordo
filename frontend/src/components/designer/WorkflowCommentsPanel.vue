<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowLeft, CheckCircle2, ListFilter, MessageSquarePlus, RotateCcw, Send, Trash2, X } from 'lucide-vue-next'
import type { WorkflowCommentThread } from '@/types/workflowComments'
import MarkdownComposer from '@/components/ui/MarkdownComposer.vue'
import SafeMarkdown from '@/components/ui/SafeMarkdown.vue'
import Button from '@/volt/Button.vue'

const props = defineProps<{ comments: WorkflowCommentThread[]; selectedId: string | null; placementActive?: boolean }>()
const emit = defineEmits<{
  close: []
  select: [id: string | null]
  place: []
  submit: [payload: { threadId: string; content: string }]
  toggleResolved: [id: string]
  delete: [id: string]
}>()
const showResolved = ref(false)
const content = ref('')
const selected = computed(() => props.comments.find(item => item.id === props.selectedId) || null)
const visible = computed(() => props.comments.filter(item => showResolved.value || !item.resolved).filter(item => item.messages.length))
watch(() => props.selectedId, () => { content.value = '' })
function submit() {
  const value = content.value.trim()
  if (!selected.value || !value) return
  emit('submit', { threadId: selected.value.id, content: value })
  content.value = ''
}
function preview(thread: WorkflowCommentThread) { return thread.messages.at(-1)?.content || '' }
</script>

<template>
  <aside class="inspector relative z-30 flex w-[400px] max-w-[38vw] shrink-0 flex-col border-l border-[var(--border)] bg-[var(--panel)]" aria-label="工作流评论">
    <header class="flex h-16 shrink-0 items-center gap-2 border-b border-[var(--border)] px-4">
      <button v-if="selected" type="button" class="icon-button" :aria-label="$t('designer.backToComments')" @click="emit('select', null)"><ArrowLeft :size="16" /></button>
      <div class="min-w-0 flex-1"><h2 class="text-sm font-semibold">{{ selected ? $t('designer.commentThread') : $t('designer.comments') }}</h2><p class="muted mt-0.5 text-[10px]">{{ placementActive ? $t('designer.commentPlacementHint') : $t('designer.commentsHint') }}</p></div>
      <button v-if="!selected" type="button" class="icon-button" :class="{ 'text-[var(--primary)]': showResolved }" :aria-label="$t('designer.filterComments')" @click="showResolved = !showResolved"><ListFilter :size="15" /></button>
      <button type="button" class="icon-button" :aria-label="$t('common.close')" @click="emit('close')"><X :size="16" /></button>
    </header>

    <template v-if="selected">
      <div class="min-h-0 flex-1 overflow-y-auto p-4">
        <div v-if="selected.resolved" class="mb-3 flex items-center gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-[11px] text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300"><CheckCircle2 :size="14" />{{ $t('designer.commentResolved') }}</div>
        <div v-for="message in selected.messages" :key="message.id" class="mb-4 flex gap-2.5">
          <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--primary-soft)] text-[10px] font-bold text-[var(--primary)]">{{ message.author_name.slice(0, 1).toUpperCase() }}</span>
          <div class="min-w-0 flex-1"><div class="flex items-center gap-2"><span class="text-[11px] font-semibold">{{ message.author_name }}</span><span class="muted text-[9px]">{{ new Date(message.created_at).toLocaleString() }}</span></div><SafeMarkdown class="mt-1 text-xs leading-5" :content="message.content" /></div>
        </div>
        <div v-if="!selected.messages.length" class="muted py-10 text-center text-xs">{{ $t('designer.writeFirstComment') }}</div>
      </div>
      <div class="shrink-0 border-t border-[var(--border)] p-3">
        <MarkdownComposer v-model="content" :placeholder="$t('designer.commentPlaceholder')" :rows="3" @submit="submit" />
        <div class="mt-2 flex items-center gap-2">
          <button type="button" class="icon-button text-red-600" :aria-label="$t('designer.deleteCommentThread')" @click="emit('delete', selected.id)"><Trash2 :size="14" /></button>
          <button v-if="selected.messages.length" type="button" class="flex h-8 items-center gap-1.5 rounded-md px-2 text-[11px] text-[var(--muted)] hover:bg-[var(--panel-subtle)]" @click="emit('toggleResolved', selected.id)"><RotateCcw v-if="selected.resolved" :size="13" /><CheckCircle2 v-else :size="13" />{{ selected.resolved ? $t('designer.reopenComment') : $t('designer.resolveComment') }}</button>
          <Button class="ml-auto !h-8 !text-xs" :disabled="!content.trim()" @click="submit"><Send :size="13" />{{ selected.messages.length ? $t('designer.reply') : $t('designer.comment') }}</Button>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="border-b border-[var(--border)] p-3"><Button class="w-full" variant="secondary" @click="emit('place')"><MessageSquarePlus :size="15" />{{ placementActive ? $t('designer.cancelCommentPlacement') : $t('designer.addCanvasComment') }}</Button></div>
      <div class="min-h-0 flex-1 overflow-y-auto p-3">
        <button v-for="(thread, index) in visible" :key="thread.id" type="button" class="card-hover mb-2 w-full rounded-lg border border-[var(--border)] p-3 text-left" @click="emit('select', thread.id)">
          <div class="flex items-center gap-2"><span class="flex h-5 min-w-5 items-center justify-center rounded-full bg-[var(--primary)] px-1 text-[9px] font-bold text-white">{{ index + 1 }}</span><span class="truncate text-[11px] font-semibold">{{ thread.messages[0]?.author_name }}</span><CheckCircle2 v-if="thread.resolved" :size="13" class="ml-auto text-emerald-600" /></div>
          <p class="mt-2 line-clamp-2 text-xs leading-5">{{ preview(thread) }}</p><span class="muted mt-1.5 block text-[9px]">{{ new Date(thread.updated_at).toLocaleString() }} · {{ thread.messages.length }} {{ $t('designer.commentMessages') }}</span>
        </button>
        <div v-if="!visible.length" class="muted flex h-full min-h-48 flex-col items-center justify-center text-center"><MessageSquarePlus :size="28" class="mb-3 opacity-40" /><p class="text-xs">{{ showResolved ? $t('designer.noResolvedComments') : $t('designer.noComments') }}</p></div>
      </div>
    </template>
  </aside>
</template>
