<script setup lang="ts">
import { computed, ref } from 'vue'
import { StickyNote } from 'lucide-vue-next'
import { type NodeProps } from '@vue-flow/core'
import { useI18n } from 'vue-i18n'
import NodeActionMenu, { type NodeAction } from '@/components/designer/NodeActionMenu.vue'
import SafeMarkdown from '@/components/ui/SafeMarkdown.vue'

const props = defineProps<NodeProps>()
const { t } = useI18n()
const menuOpen = ref(false)
const tone = computed(() => ['yellow', 'blue', 'green', 'rose'].includes(String(props.data?.color)) ? props.data.color : 'yellow')
function nodeAction(action: NodeAction) { menuOpen.value = false; window.dispatchEvent(new CustomEvent('workflow-node-action', { detail: { nodeId: props.id, action } })) }
</script>

<template>
  <article class="note-card" :class="[`note-${tone}`, { selected }]">
    <div class="flex items-start gap-2">
      <StickyNote :size="15" class="mt-0.5 shrink-0 opacity-70" />
      <div class="min-w-0 flex-1 text-[12px] font-semibold">{{ data?.label || t('designer.noteTitleDefault') }}</div>
      <div class="relative"><button class="note-menu" type="button" :aria-label="t('designer.more')" @click.stop="menuOpen = !menuOpen">...</button><div v-if="menuOpen" class="absolute right-0 top-6 z-30" @click.stop><NodeActionMenu :show-run="false" @action="nodeAction" /></div></div>
    </div>
    <SafeMarkdown class="mt-2 text-[11px] leading-5 opacity-80" :content="data?.description || t('designer.noteEmpty')" />
  </article>
</template>

<style scoped>
.note-card { width: 220px; min-height: 126px; border: 1px solid var(--note-border); border-radius: 7px; background: var(--note-bg); padding: 12px; color: var(--note-text); box-shadow: 0 4px 14px rgb(16 24 40 / 8%); transition: border-color .15s ease; }
.note-card:hover { border-color: var(--primary); }
.note-card.selected { box-shadow: 0 0 0 2px color-mix(in srgb, var(--note-border), transparent 55%), 0 6px 18px rgb(16 24 40 / 10%); }
.note-menu { width: 20px; height: 20px; border-radius: 5px; color: currentColor; font-size: 13px; line-height: 12px; opacity: .65; }
.note-menu:hover { background: rgb(255 255 255 / 45%); opacity: 1; }
.note-yellow { --note-bg: #fff7cc; --note-border: #e8c94b; --note-text: #594700; }
.note-blue { --note-bg: #e8f2ff; --note-border: #84adff; --note-text: #1849a9; }
.note-green { --note-bg: #e8f8ef; --note-border: #75c99a; --note-text: #05603a; }
.note-rose { --note-bg: #fff0f3; --note-border: #f29aae; --note-text: #9f1239; }
:global(.dark) .note-yellow { --note-bg: #443810; --note-border: #8a7120; --note-text: #fde68a; }
:global(.dark) .note-blue { --note-bg: #152b4f; --note-border: #315b9c; --note-text: #bfdbfe; }
:global(.dark) .note-green { --note-bg: #123c2a; --note-border: #277a52; --note-text: #bbf7d0; }
:global(.dark) .note-rose { --note-bg: #4a1927; --note-border: #9f3a59; --note-text: #fecdd3; }
</style>
