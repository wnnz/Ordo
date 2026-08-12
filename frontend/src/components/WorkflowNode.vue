<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Handle, Position, type NodeProps } from '@vue-flow/core'
import { AlertTriangle, Bot, Braces, BrainCircuit, CheckCircle2, CircleSlash, CircleStop, Code2, Combine, FileCheck2, FileText, GitBranch, GitMerge, Globe2, Images, ListFilter, ListTree, Play, Plus, RefreshCw, Repeat2, ScanText, Timer, UserCheck, Workflow, XCircle } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import NodeActionMenu, { type NodeAction } from '@/components/designer/NodeActionMenu.vue'
import NodeValidationBadge from '@/components/designer/NodeValidationBadge.vue'
import WorkflowNodeSummary from '@/components/designer/WorkflowNodeSummary.vue'

const props = defineProps<NodeProps>()
const { t } = useI18n()
const menuOpen = ref(false)
const card = ref<HTMLElement | null>(null)
const nodeType = computed(() => String(props.data?.nodeType || props.type))
const runtimeStatus = computed(() => String(props.data?.runtimeStatus || ''))
const runtimeDuration = computed(() => {
  const value = Number(props.data?.runtimeDurationMs)
  if (!Number.isFinite(value)) return ''
  return value < 1000 ? `${Math.round(value)}ms` : `${(value / 1000).toFixed(2)}s`
})
function quickAdd(sourceHandle?: string, event?: MouseEvent) {
  window.dispatchEvent(new CustomEvent('workflow-quick-add', { detail: { sourceId: props.id, sourceHandle, clientX: event?.clientX, clientY: event?.clientY } }))
}
function nodeAction(action: NodeAction) {
  menuOpen.value = false
  window.dispatchEvent(new CustomEvent('workflow-node-action', { detail: { nodeId: props.id, action } }))
}
function closeMenuOnOutsidePointer(event: PointerEvent) {
  if (menuOpen.value && !card.value?.contains(event.target as Node)) menuOpen.value = false
}
onMounted(() => document.addEventListener('pointerdown', closeMenuOnOutsidePointer, true))
onUnmounted(() => document.removeEventListener('pointerdown', closeMenuOnOutsidePointer, true))
const classifierCategories = computed(() => Array.isArray(props.data?.config?.categories) ? props.data.config.categories : [])
const humanActions = computed(() => Array.isArray(props.data?.config?.actions) ? props.data.config.actions : [])
const hasErrorBranch = computed(() => props.data?.config?.error_strategy === 'error_branch')
const validationMessages = computed<string[]>(() => Array.isArray(props.data?.validationMessages) ? props.data.validationMessages : [])
function focusValidation() { window.dispatchEvent(new CustomEvent('workflow-node-validation', { detail: { nodeId: props.id } })) }
function classifierHandle(category: any) { return `category:${String(category?.id || '')}` }
function humanHandle(action: any) { return `action:${String(action?.id || '')}` }
const meta = computed(() => ({
  start: { icon: Play, tone: 'blue', detail: (props.data?.config?.triggers || ['form', 'api']).map((item: string) => t(`designer.triggerShort.${item}`)).join(' + ') },
  end: { icon: CircleStop, tone: 'slate', detail: Array.isArray(props.data?.config?.outputs) ? props.data.config.outputs.map((output: any) => output.name).filter(Boolean).join(' · ') || t('designer.nodeDetails.output') : t('designer.nodeDetails.output') },
  llm: { icon: Bot, tone: 'violet', detail: props.data?.config?.model || 'LLM' },
  image: { icon: Images, tone: 'rose', detail: props.data?.config?.model || t('workflow.nodes.image') },
  agent: { icon: BrainCircuit, tone: 'violet', detail: props.data?.config?.model || t('workflow.nodes.agent') },
  classifier: { icon: ListFilter, tone: 'orange', detail: `${classifierCategories.value.length} ${t('designer.categories')}` },
  code: { icon: Code2, tone: 'emerald', detail: 'Python' },
  script: { icon: Braces, tone: 'emerald', detail: props.data?.config?.script_name || 'Python' },
  template: { icon: FileText, tone: 'sky', detail: t('designer.nodeDetails.template') },
  variable: { icon: ListTree, tone: 'indigo', detail: t('designer.nodeDetails.variable') },
  json: { icon: Code2, tone: 'cyan', detail: 'JSON' },
  aggregate: { icon: Combine, tone: 'indigo', detail: t('designer.nodeDetails.aggregation') },
  extract: { icon: ScanText, tone: 'cyan', detail: t('designer.nodeDetails.extraction') },
  list: { icon: ListFilter, tone: 'sky', detail: t('designer.nodeDetails.list') },
  http: { icon: Globe2, tone: 'cyan', detail: 'HTTP' },
  condition: { icon: GitBranch, tone: 'orange', detail: props.data?.config?.conditions?.length ? `${props.data.config.conditions.length} ${t('designer.conditionCount')}` : t('designer.nodeDetails.branch') },
  human: { icon: UserCheck, tone: 'amber', detail: t('designer.nodeDetails.approval') },
  wait: { icon: GitMerge, tone: 'emerald', detail: t('designer.nodeDetails.wait') },
  iteration: { icon: Repeat2, tone: 'blue', detail: t('designer.nodeDetails.iteration') },
  loop: { icon: RefreshCw, tone: 'violet', detail: t('designer.nodeDetails.loop') },
  delay: { icon: Timer, tone: 'slate', detail: t('designer.nodeDetails.delay') },
  subworkflow: { icon: Workflow, tone: 'emerald', detail: props.data?.config?.workflow_name || t('designer.nodeDetails.subworkflow') },
  document: { icon: FileText, tone: 'rose', detail: 'Office / PDF' },
  answer_filler: { icon: FileCheck2, tone: 'rose', detail: t('workflow.nodes.answer_filler') },
}[nodeType.value] || { icon: Workflow, tone: 'blue', detail: nodeType.value }))
</script>

<template>
  <article ref="card" class="workflow-card" :class="[`tone-${meta.tone}`, runtimeStatus && `runtime-${runtimeStatus}`, { selected }]">
    <NodeValidationBadge :messages="validationMessages" @focus="focusValidation" />
    <Handle v-if="nodeType !== 'start'" type="target" :position="Position.Left" />
    <div class="flex items-start gap-2.5">
      <span class="node-icon"><component :is="meta.icon" :size="16" /></span>
      <div class="min-w-0 flex-1">
        <div class="truncate text-[13px] font-semibold">{{ data?.label }}</div>
        <div v-if="data?.description" class="mt-1 line-clamp-2 text-[11px] leading-4 text-[var(--muted)]">{{ data.description }}</div>
      </div>
      <div class="relative"><button class="node-menu" type="button" :aria-label="t('designer.more')" @click.stop="menuOpen = !menuOpen">...</button><div v-if="menuOpen" class="absolute right-0 top-6 z-30" @click.stop><NodeActionMenu :protected-node="['start','end'].includes(nodeType)" :can-change="!['iteration','loop'].includes(nodeType)" @action="nodeAction" /></div></div>
    </div>
    <div v-if="nodeType === 'condition'" class="condition-branches">
      <div class="condition-branch text-emerald-600">
        <span>IF</span>
        <Handle id="true" type="source" :position="Position.Right" class="quick-add-handle condition-handle">
          <button type="button" :aria-label="`${t('workflow.addNode')} IF`" @click.stop="quickAdd('true', $event)"><Plus :size="12" :stroke-width="2.4" /></button>
        </Handle>
      </div>
      <div class="condition-branch text-amber-600">
        <span>ELSE</span>
        <Handle id="false" type="source" :position="Position.Right" class="quick-add-handle condition-handle">
          <button type="button" :aria-label="`${t('workflow.addNode')} ELSE`" @click.stop="quickAdd('false', $event)"><Plus :size="12" :stroke-width="2.4" /></button>
        </Handle>
      </div>
    </div>
    <div v-else-if="nodeType === 'classifier'" class="classifier-branches">
      <div v-for="(category, index) in classifierCategories" :key="category.id || index" class="classifier-branch">
        <span class="classifier-index">{{ Number(index) + 1 }}</span><span class="truncate">{{ category.name || `${t('designer.categoryName')} ${Number(index) + 1}` }}</span>
        <Handle :id="classifierHandle(category)" type="source" :position="Position.Right" class="quick-add-handle classifier-handle">
          <button type="button" :aria-label="`${t('workflow.addNode')} ${category.name || Number(index) + 1}`" @click.stop="quickAdd(classifierHandle(category), $event)"><Plus :size="12" :stroke-width="2.4" /></button>
        </Handle>
      </div>
    </div>
    <div v-else-if="nodeType === 'human'" class="classifier-branches">
      <div v-for="(action, index) in humanActions" :key="action.id || index" class="classifier-branch">
        <span class="classifier-index">{{ Number(index) + 1 }}</span><span class="truncate">{{ action.label || action.id }}</span>
        <Handle :id="humanHandle(action)" type="source" :position="Position.Right" class="quick-add-handle classifier-handle">
          <button type="button" :aria-label="`${t('workflow.addNode')} ${action.label || action.id}`" @click.stop="quickAdd(humanHandle(action), $event)"><Plus :size="12" :stroke-width="2.4" /></button>
        </Handle>
      </div>
    </div>
    <WorkflowNodeSummary v-else :node-type="nodeType" :config="data?.config" :fallback="meta.detail" />
    <Handle v-if="!['end','classifier','human','condition'].includes(nodeType)" type="source" :position="Position.Right" class="quick-add-handle" :style="hasErrorBranch ? { top: '58%' } : undefined">
      <button type="button" :aria-label="t('workflow.addNode')" @click.stop="quickAdd(undefined, $event)"><Plus :size="12" :stroke-width="2.4" /></button>
    </Handle>
    <Handle v-if="hasErrorBranch" id="error" type="source" :position="Position.Right" class="quick-add-handle error-handle" :style="{ top: '82%' }">
      <button type="button" :aria-label="t('designer.connectErrorBranch')" @click.stop="quickAdd('error', $event)"><AlertTriangle :size="9" :stroke-width="2.4" /></button>
    </Handle>
    <span v-if="runtimeStatus" class="runtime-badge" :class="`runtime-badge-${runtimeStatus}`"><CheckCircle2 v-if="runtimeStatus === 'succeeded'" :size="12" /><AlertTriangle v-else-if="runtimeStatus === 'recovered' || runtimeStatus === 'waiting'" :size="12" /><XCircle v-else-if="runtimeStatus === 'failed'" :size="12" /><CircleSlash v-else :size="12" />{{ runtimeStatus === 'skipped' ? t('designer.runSkipped') : runtimeStatus === 'failed' ? t('designer.runFailed') : runtimeStatus === 'recovered' ? t('designer.runRecovered') : runtimeStatus === 'waiting' ? t('designer.runWaiting') : runtimeDuration || t('designer.runSucceeded') }}</span>
  </article>
</template>

<style scoped>
.workflow-card { position: relative; width: 206px; min-height: 82px; border: 1px solid var(--border); border-radius: 8px; background: var(--panel); padding: 10px; color: var(--text); box-shadow: 0 3px 12px rgb(16 24 40 / 6%); transition: border-color .15s ease; }
.workflow-card:hover { border-color: var(--primary); }
.workflow-card.selected { border-color: var(--node-color); box-shadow: 0 0 0 2px color-mix(in srgb, var(--node-color), transparent 80%), 0 5px 18px rgb(16 24 40 / 8%); }
.node-icon { display: flex; width: 28px; height: 28px; flex: none; align-items: center; justify-content: center; border-radius: 7px; background: color-mix(in srgb, var(--node-color), transparent 88%); color: var(--node-color); }
.node-menu { width: 20px; height: 20px; border-radius: 5px; color: var(--muted); font-size: 13px; line-height: 12px; }
.node-menu:hover { background: var(--panel-subtle); }
.condition-branches { margin-top: 9px; display: grid; gap: 5px; font-size: 10px; font-weight: 700; }.condition-branch { position: relative; display: flex; height: 27px; align-items: center; border-radius: 5px; background: var(--panel-subtle); padding: 0 9px; }.condition-handle { top: 50% !important; right: -20px !important; transform: translateY(-50%); }
.classifier-branches { margin-top: 9px; display: grid; gap: 5px; }.classifier-branch { position: relative; display: flex; height: 27px; align-items: center; gap: 6px; border-radius: 5px; background: var(--panel-subtle); padding: 0 8px; color: var(--node-color); font-size: 10px; font-weight: 600; }.classifier-index { display: flex; width: 16px; height: 16px; flex: none; align-items: center; justify-content: center; border-radius: 4px; background: color-mix(in srgb, var(--node-color), transparent 86%); font-size: 9px; }.classifier-handle { top: 50% !important; right: -20px !important; transform: translateY(-50%); }
.quick-add-handle button { display: flex; width: 20px; height: 20px; padding: 0; align-items: center; justify-content: center; border: 1px solid var(--primary); border-radius: 50%; background: var(--panel); color: var(--primary); line-height: 0; box-shadow: 0 1px 3px rgb(16 24 40 / 12%); }
.quick-add-handle button svg { display: block; flex: none; }
.quick-add-handle button:hover { background: var(--primary); color: white; }
.error-handle button { border-color: #f79009; color: #dc6803; }.error-handle button:hover { background: #f79009; }
.workflow-card.runtime-succeeded { border-color: #12b76a; box-shadow: 0 0 0 2px rgb(18 183 106 / 12%), 0 5px 18px rgb(16 24 40 / 8%); }.workflow-card.runtime-recovered, .workflow-card.runtime-waiting { border-color: #f79009; box-shadow: 0 0 0 2px rgb(247 144 9 / 12%), 0 5px 18px rgb(16 24 40 / 8%); }.workflow-card.runtime-failed { border-color: #f04438; box-shadow: 0 0 0 2px rgb(240 68 56 / 12%); }.workflow-card.runtime-skipped { opacity: .48; filter: grayscale(.35); }.runtime-badge { position: absolute; right: 8px; bottom: -11px; z-index: 5; display: flex; height: 22px; align-items: center; gap: 4px; border: 1px solid var(--border); border-radius: 999px; background: var(--panel); padding: 0 7px; font-size: 9px; font-weight: 600; box-shadow: 0 2px 6px rgb(16 24 40 / 10%); }.runtime-badge-succeeded { border-color: rgb(18 183 106 / 35%); color: #079455; }.runtime-badge-recovered, .runtime-badge-waiting { border-color: rgb(247 144 9 / 35%); color: #dc6803; }.runtime-badge-failed { border-color: rgb(240 68 56 / 35%); color: #d92d20; }.runtime-badge-skipped { color: var(--muted); }
.tone-blue { --node-color: #155eef; }.tone-slate { --node-color: #667085; }.tone-violet { --node-color: #7f56d9; }.tone-emerald { --node-color: #079455; }.tone-sky { --node-color: #026aa2; }.tone-indigo { --node-color: #444ce7; }.tone-amber { --node-color: #dc6803; }.tone-cyan { --node-color: #088ab2; }.tone-orange { --node-color: #e04f16; }.tone-rose { --node-color: #e31b54; }
</style>
