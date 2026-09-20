<script setup lang="ts">
import { FileCode2 } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import ActionCard from '@/volt/ActionCard.vue'

export type ScriptSummary = {
  id: string
  name: string
  description?: string | null
  latest_version: number
  tags?: string[]
}

defineProps<{ script: ScriptSummary }>()
const emit = defineEmits<{ select: [] }>()
const { t } = useI18n()
</script>

<template>
  <ActionCard class="rounded-lg p-4" @click="emit('select')">
    <div class="flex items-start gap-3">
      <span class="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600 dark:bg-emerald-950/40">
        <FileCode2 :size="20" />
      </span>
      <div class="min-w-0">
        <h2 class="truncate font-semibold">{{ script.name }}</h2>
        <p class="muted mt-1 line-clamp-2 text-sm">{{ script.description || 'Python · main(inputs, context)' }}</p>
      </div>
    </div>
    <div class="muted mt-5 flex justify-between border-t border-[var(--border)] pt-3 text-xs">
      <span>{{ t('scripts.version') }} {{ script.latest_version }}</span>
      <span>{{ script.tags?.join(', ') }}</span>
    </div>
  </ActionCard>
</template>
