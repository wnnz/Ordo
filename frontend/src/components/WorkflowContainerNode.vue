<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { Handle, Position, useVueFlow, type NodeProps } from '@vue-flow/core'
import { Play, Plus, RefreshCw, Repeat2, Trash2 } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import NodeValidationBadge from '@/components/designer/NodeValidationBadge.vue'
import { containerEntryPoints } from '@/utils/workflowGraph'

const props = defineProps<NodeProps>()
const { t } = useI18n()
const { getEdges, getNodes } = useVueFlow()
const menuOpen = ref(false)
const containerElement = ref<HTMLElement | null>(null)
const startElement = ref<HTMLElement | null>(null)
const startAnchor = ref({ x: 108, y: 125 })
const nodeType = computed(() => String(props.data?.nodeType || props.type))
const isLoop = computed(() => nodeType.value === 'loop')
const icon = computed(() => isLoop.value ? RefreshCw : Repeat2)
const containerClass = computed(() => isLoop.value ? 'is-loop' : 'is-iteration')
const containerHint = computed(() => isLoop.value ? t('designer.loopContainerHint') : t('designer.iterationContainerHint'))
const startLabel = computed(() => isLoop.value ? t('designer.loopStart') : t('designer.iterationStart'))
const validationMessages = computed<string[]>(() => Array.isArray(props.data?.validationMessages) ? props.data.validationMessages : [])
const entryPaths = computed(() => containerEntryPoints(getNodes.value as any[], getEdges.value as any[], props.id).map(point => {
  const distance = Math.max(36, (point.x - startAnchor.value.x) * 0.45)
  return {
    ...point,
    path: `M ${startAnchor.value.x} ${startAnchor.value.y} C ${startAnchor.value.x + distance} ${startAnchor.value.y}, ${point.x - distance} ${point.y}, ${point.x} ${point.y}`,
  }
}))
function focusValidation() { window.dispatchEvent(new CustomEvent('workflow-node-validation', { detail: { nodeId: props.id } })) }
onMounted(() => nextTick(() => {
  if (!containerElement.value || !startElement.value) return
  startAnchor.value = {
    x: startElement.value.offsetLeft + startElement.value.offsetWidth,
    y: 52 + startElement.value.offsetTop + startElement.value.offsetHeight / 2,
  }
}))

function addInside(event?: MouseEvent) {
  window.dispatchEvent(new CustomEvent('workflow-container-add', { detail: { parentId: props.id, clientX: event?.clientX, clientY: event?.clientY } }))
}
function quickAdd(event?: MouseEvent) {
  window.dispatchEvent(new CustomEvent('workflow-quick-add', { detail: { sourceId: props.id, clientX: event?.clientX, clientY: event?.clientY } }))
}
function removeContainer() {
  window.dispatchEvent(new CustomEvent('workflow-container-delete', { detail: { parentId: props.id } }))
}
</script>

<template>
  <section ref="containerElement" class="workflow-container" :class="[{ selected }, containerClass]">
    <NodeValidationBadge :messages="validationMessages" @focus="focusValidation" />
    <Handle type="target" :position="Position.Left" />
    <header class="container-header">
      <span class="container-icon"><component :is="icon" :size="15" /></span>
      <div class="min-w-0 flex-1">
        <div class="truncate text-xs font-semibold">{{ data?.label }}</div>
        <div class="muted mt-0.5 text-[9px]">{{ containerHint }}</div>
      </div>
      <div class="relative">
        <button class="node-menu" type="button" :aria-label="t('designer.more')" @click.stop="menuOpen = !menuOpen">...</button>
        <div v-if="menuOpen" class="surface absolute right-0 top-6 z-30 w-28 rounded-md p-1 shadow-xl">
          <button class="flex w-full items-center gap-2 rounded px-2 py-1.5 text-xs text-red-600 hover:bg-red-50" @click.stop="removeContainer"><Trash2 :size="13" />{{ t('common.delete') }}</button>
        </div>
      </div>
    </header>
    <svg v-if="entryPaths.length" class="container-entry-lines" aria-hidden="true">
      <g v-for="entry in entryPaths" :key="entry.nodeId">
        <path :d="entry.path" />
        <circle :cx="entry.x" :cy="entry.y" r="3" />
      </g>
    </svg>
    <div class="container-body">
      <div ref="startElement" class="container-start-row">
        <div class="container-start"><span><Play :size="12" fill="currentColor" /></span>{{ startLabel }}</div>
        <button class="container-add nodrag" type="button" :aria-label="t('designer.addInnerNode')" :title="t('designer.addInnerNode')" @click.stop="addInside($event)"><Plus :size="12" :stroke-width="2.4" /></button>
      </div>
    </div>
    <Handle type="source" :position="Position.Right" class="quick-add-handle">
      <button type="button" :aria-label="t('workflow.addNode')" @click.stop="quickAdd($event)"><Plus :size="12" :stroke-width="2.4" /></button>
    </Handle>
  </section>
</template>

<style scoped>
.workflow-container { position: relative; width: 100%; height: 100%; min-width: 500px; min-height: 250px; overflow: visible; border: 1px solid var(--border); border-radius: 8px; background: color-mix(in srgb, var(--panel), transparent 8%); color: var(--text); box-shadow: 0 3px 14px rgb(16 24 40 / 5%); transition: border-color .15s ease; }
.workflow-container:hover { border-color: var(--primary); }
.workflow-container.selected { border-color: var(--container-color); box-shadow: 0 0 0 2px color-mix(in srgb, var(--container-color), transparent 82%), 0 5px 18px rgb(16 24 40 / 7%); }
.container-header { display: flex; height: 52px; align-items: center; gap: 9px; border-bottom: 1px solid var(--border); padding: 0 12px; background: color-mix(in srgb, var(--container-color), transparent 94%); }
.container-icon { display: flex; width: 27px; height: 27px; align-items: center; justify-content: center; border-radius: 6px; background: color-mix(in srgb, var(--container-color), transparent 86%); color: var(--container-color); }
.container-body { position: absolute; inset: 52px 0 0; background-image: radial-gradient(circle, var(--border) 1px, transparent 1px); background-size: 18px 18px; }
.container-entry-lines { position: absolute; inset: 0; z-index: 5; width: 100%; height: 100%; overflow: visible; pointer-events: none; }.container-entry-lines path { fill: none; stroke: color-mix(in srgb, var(--container-color), #98a2b3 55%); stroke-width: 1.5; }.container-entry-lines circle { fill: var(--container-color); stroke: var(--panel); stroke-width: 1.5; }
.container-start-row { position: absolute; left: 20px; top: 56px; z-index: 6; height: 34px; }
.container-start { box-sizing: border-box; display: flex; width: 156px; height: 34px; align-items: center; gap: 7px; border: 1px solid var(--border); border-radius: 7px; background: var(--panel); padding: 0 24px 0 10px; color: var(--muted); font-size: 10px; font-weight: 600; white-space: nowrap; box-shadow: 0 2px 7px rgb(16 24 40 / 6%); }
.container-start span { display: flex; width: 20px; height: 20px; align-items: center; justify-content: center; border-radius: 5px; background: color-mix(in srgb, var(--container-color), transparent 88%); color: var(--container-color); }
.container-add { position: absolute; right: -10px; top: 50%; display: flex; width: 20px; height: 20px; padding: 0; transform: translateY(-50%); align-items: center; justify-content: center; border: 1px solid var(--primary); border-radius: 50%; background: var(--panel); color: var(--primary); line-height: 0; box-shadow: 0 1px 3px rgb(16 24 40 / 12%); }
.container-add:hover { background: var(--primary); color: white; }
.node-menu { width: 20px; height: 20px; border-radius: 5px; color: var(--muted); font-size: 13px; line-height: 12px; }.node-menu:hover { background: var(--panel-subtle); }
.quick-add-handle button { display: flex; width: 20px; height: 20px; padding: 0; align-items: center; justify-content: center; border: 1px solid var(--primary); border-radius: 50%; background: var(--panel); color: var(--primary); line-height: 0; box-shadow: 0 1px 3px rgb(16 24 40 / 12%); }.quick-add-handle button:hover { background: var(--primary); color: white; }
.is-iteration { --container-color: #155eef; }.is-loop { --container-color: #7f56d9; }
</style>
