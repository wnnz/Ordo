<script setup lang="ts">
import { computed, defineAsyncComponent, markRaw, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { Background } from '@vue-flow/background'
import { VueFlow, useVueFlow, type Connection, type Edge, type Node, type NodeMouseEvent } from '@vue-flow/core'
import { MiniMap } from '@vue-flow/minimap'
import { Activity, AlertTriangle, ArrowLeft, Bot, Braces, BrainCircuit, Check, ChevronRight, CircleStop, Code2, Combine, Copy, FileText, GitBranch, GitMerge, Globe2, History, Images, ListChecks, ListFilter, ListTree, MousePointer2, Play, Plus, RefreshCw, Repeat2, Save, ScanText, Search, Timer, Trash2, UserCheck, Workflow, X } from 'lucide-vue-next'
import api from '@/api/client'
import { messages } from '@/i18n'
import VariableField from '@/components/VariableField.vue'
import AnnotationPlacementToolbar from '@/components/designer/AnnotationPlacementToolbar.vue'
import DesignerCommandPalette from '@/components/designer/DesignerCommandPalette.vue'
import NextStepPanel from '@/components/designer/NextStepPanel.vue'
import NodeActionMenu, { type NodeAction } from '@/components/designer/NodeActionMenu.vue'
import NodeConfigSection from '@/components/designer/NodeConfigSection.vue'
import NodeOutputPanel from '@/components/designer/NodeOutputPanel.vue'
import NodePalette from '@/components/designer/NodePalette.vue'
import PublishPopover from '@/components/designer/PublishPopover.vue'
import RunDebugPanel from '@/components/designer/RunDebugPanel.vue'
import SelectionToolbar from '@/components/designer/SelectionToolbar.vue'
import WorkflowCommentPin from '@/components/designer/WorkflowCommentPin.vue'
import WorkflowCommentsPanel from '@/components/designer/WorkflowCommentsPanel.vue'
import WorkflowCanvasControls from '@/components/designer/WorkflowCanvasControls.vue'
import WorkflowDesignerSidebar, { type DesignerSection } from '@/components/designer/WorkflowDesignerSidebar.vue'
import WorkflowApiPanel from '@/components/designer/WorkflowApiPanel.vue'
import WorkflowMonitoringPanel from '@/components/designer/WorkflowMonitoringPanel.vue'
import WorkflowNodeInspector, { type InspectorTab } from '@/components/designer/WorkflowNodeInspector.vue'
import WorkflowRunLogsPanel from '@/components/designer/WorkflowRunLogsPanel.vue'
import WorkflowEnvironmentPanel, { type WorkflowEnvironmentVariable } from '@/components/designer/WorkflowEnvironmentPanel.vue'
import WorkflowSystemVariablesPanel from '@/components/designer/WorkflowSystemVariablesPanel.vue'
import WorkflowSaveStatus from '@/components/designer/WorkflowSaveStatus.vue'
import WorkflowSettingsPanel from '@/components/designer/WorkflowSettingsPanel.vue'
import AlertBanner from '@/components/ui/AlertBanner.vue'
import ChoiceCard from '@/components/ui/ChoiceCard.vue'
import MarkdownComposer from '@/components/ui/MarkdownComposer.vue'
import ModalShell from '@/components/ui/ModalShell.vue'
import WorkflowEdge from '@/components/WorkflowEdge.vue'
import WorkflowContainerNode from '@/components/WorkflowContainerNode.vue'
import WorkflowNode from '@/components/WorkflowNode.vue'
import WorkflowNoteNode from '@/components/WorkflowNoteNode.vue'
import { useAuthStore } from '@/stores/auth'
import { usePreferencesStore } from '@/stores/preferences'
import { useWorkspacesStore } from '@/stores/workspaces'
import Button from '@/volt/Button.vue'
import InputText from '@/volt/InputText.vue'
import Select from '@/volt/Select.vue'
import Textarea from '@/volt/Textarea.vue'
import { absoluteNodePosition, clearWorkflowEdgeSelection, containerSizeForChildren, findAvailableNodePosition, insertNodeOnEdge, isConnectionAllowed, layoutContainerChildren, layoutWorkflow, mergeWorkflowEdges, nextContainerChildPosition, removeWorkflowEdgeById, replaceWorkflowNode, validateWorkflowGraph, type WorkflowValidationIssue } from '@/utils/workflowGraph'
import { stripRuntimeData } from '@/utils/workflowRunOverlay'
import { migrateLegacyAnswerFillerNodes } from '@/utils/workflowNodeMigrations'
import { allocateDefaultNodeName, ensureUniqueNodeNames, nextUniqueNodeName, nodeReferenceName, rewriteNodeReferences, validateNodeName, type NodeNameError, type NodeRename } from '@/utils/workflowNodeNames'
import { buildAllVariableCatalog, buildVariableCatalog, readRuntimeVariable } from '@/utils/workflowVariables'
import { normalizeWorkflowComments, type WorkflowCommentThread } from '@/types/workflowComments'
import { SYSTEM_VARIABLES } from '@/types/workflowSystemVariables'
import { executionPolicyNodeTypes, useDesignerNodeConfig } from '@/composables/useDesignerNodeConfig'
import { useWorkflowRuns } from '@/composables/useWorkflowRuns'

const { t } = useI18n()
const { classifierBranchLabel, createClassifierCategory, defaultNodeConfig, normalizeClassifierConfig, normalizeConditionConfig, normalizeEndOutputs, normalizeExecutionPolicy, normalizeHumanConfig, normalizeImageConfig, normalizeLlmConfig, normalizeStartField } = useDesignerNodeConfig(t)
const CodeConfigPanel = defineAsyncComponent(() => import('@/components/designer/CodeConfigPanel.vue'))
const AggregateConfigPanel = defineAsyncComponent(() => import('@/components/designer/AggregateConfigPanel.vue'))
const AgentConfigPanel = defineAsyncComponent(() => import('@/components/designer/AgentConfigPanel.vue'))
const ClassifierConfigPanel = defineAsyncComponent(() => import('@/components/designer/ClassifierConfigPanel.vue'))
const ConditionConfigPanel = defineAsyncComponent(() => import('@/components/designer/ConditionConfigPanel.vue'))
const ExecutionPolicyPanel = defineAsyncComponent(() => import('@/components/designer/ExecutionPolicyPanel.vue'))
const HttpConfigPanel = defineAsyncComponent(() => import('@/components/designer/HttpConfigPanel.vue'))
const HumanConfigPanel = defineAsyncComponent(() => import('@/components/designer/HumanConfigPanel.vue'))
const JsonEditorField = defineAsyncComponent(() => import('@/components/designer/JsonEditorField.vue'))
const ListOperatorConfigPanel = defineAsyncComponent(() => import('@/components/designer/ListOperatorConfigPanel.vue'))
const LoopConfigPanel = defineAsyncComponent(() => import('@/components/designer/LoopConfigPanel.vue'))
const WaitConfigPanel = defineAsyncComponent(() => import('@/components/designer/WaitConfigPanel.vue'))
const LlmConfigPanel = defineAsyncComponent(() => import('@/components/designer/LlmConfigPanel.vue'))
const ImageGenerationConfigPanel = defineAsyncComponent(() => import('@/components/designer/ImageGenerationConfigPanel.vue'))
const ParameterExtractorConfigPanel = defineAsyncComponent(() => import('@/components/designer/ParameterExtractorConfigPanel.vue'))
const ScriptConfigPanel = defineAsyncComponent(() => import('@/components/designer/ScriptConfigPanel.vue'))
const SubworkflowConfigPanel = defineAsyncComponent(() => import('@/components/designer/SubworkflowConfigPanel.vue'))
const TemplateConfigPanel = defineAsyncComponent(() => import('@/components/designer/TemplateConfigPanel.vue'))
const DocumentConfigPanel = defineAsyncComponent(() => import('@/components/designer/DocumentConfigPanel.vue'))
const IterationConfigPanel = defineAsyncComponent(() => import('@/components/designer/IterationConfigPanel.vue'))
const VariableAssignConfigPanel = defineAsyncComponent(() => import('@/components/designer/VariableAssignConfigPanel.vue'))
const route = useRoute(); const router = useRouter()
const auth = useAuthStore(); const preferences = usePreferencesStore(); const workspaces = useWorkspacesStore()
const { addNodes, addSelectedNodes, fitView, getNodes, onConnect, removeSelectedNodes, screenToFlowCoordinate, setCenter, viewport, zoomIn, zoomOut } = useVueFlow()
const workflow = ref<any>(null); const nodes = ref<Node[]>([]); const edges = ref<Edge[]>([])
const selected = ref<Node | null>(null); const saving = ref(false); const publishing = ref(false); const publishSuccess = ref('')
const inspectorTab = ref<InspectorTab>('settings'); const paletteOpen = ref(false)
const paletteSourceId = ref<string | null>(null)
const paletteSourceHandle = ref<string | null>(null)
const paletteEdgeId = ref<string | null>(null)
const paletteParentId = ref<string | null>(null)
const paletteReplaceNodeId = ref<string | null>(null)
const paletteQuery = ref(''); const configText = ref('{}'); const configError = ref('')
const paletteTab = ref<'nodes' | 'tools' | 'snippets'>('nodes')
const palettePosition = ref({ x: 64, y: 80 })
const interactionMode = ref<'pointer' | 'hand'>('pointer')
const middlePanning = ref(false)
const showCommandPalette = ref(false)
const annotationMode = ref(false); const annotationColor = ref('yellow')
const commentMode = ref(false); const showComments = ref(false); const selectedCommentId = ref<string | null>(null)
const comments = ref<WorkflowCommentThread[]>([])
const canvasHost = ref<HTMLElement | null>(null); const nodeContextMenu = ref<{ nodeId: string; x: number; y: number } | null>(null)
const loaded = ref(false); const saveError = ref(''); const saveConflict = ref(false); const lastSavedAt = ref<Date | null>(null)
const dirty = ref(false); const editRevision = ref(0)
const workflowSlugDraft = ref('')
const activeSection = ref<DesignerSection>('orchestration'); const versions = ref<any[]>([]); const showHistory = ref(false); const showHelp = ref(false)
const showApiAccess = ref(false)
const showChecklist = ref(false); const showChangeHistory = ref(false); const pendingRestoreVersion = ref<any>(null); const restoringVersion = ref(false)
const sidebarCollapsed = ref(false)
const expandedStartFieldIndex = ref<number | null>(null)
const showVariableInspector = ref(false); const variableSearch = ref(''); const copiedVariablePath = ref('')
const modelProviders = ref<any[]>([]); const scripts = ref<any[]>([]); const subworkflows = ref<any[]>([])
const environmentVariables = ref<WorkflowEnvironmentVariable[]>([]); const showEnvironment = ref(false); const environmentSaving = ref(false); const environmentError = ref('')
const showSystemVariables = ref(false)
const environmentPanel = ref<{ markSaved: () => void } | null>(null)
const configBuffers = ref({ values: '{}', jsonValue: '{}', httpHeaders: '{}', httpQuery: '{}', httpBody: '', llmSchema: '{}' })
const configFieldErrors = ref<Record<string, string>>({}); const configEditing = ref(false)
const nodeNameError = ref('')
type GraphState = { nodes: any[]; edges: any[]; comments?: WorkflowCommentThread[] }
const graphHistory = ref<GraphState[]>([]); const historyIndex = ref(-1); const copiedGraph = ref<GraphState | null>(null)
const historyTimes = ref<Date[]>([])
const workspaceId = computed(() => String(route.params.workspaceId)); const workflowId = computed(() => String(route.params.workflowId))
const origin = window.location.origin
const selectedType = computed(() => String(selected.value?.data?.nodeType || selected.value?.type || ''))
const environmentVariableGroup = computed(() => ({ nodeId: 'env', label: t('designer.environmentVariables'), variables: environmentVariables.value.map(variable => ({ path: `env.${variable.name}`, label: variable.description || variable.name, type: variable.value_type === 'number' ? 'Number' : 'String' })) }))
const systemVariableGroup = computed(() => ({ nodeId: 'sys', label: t('designer.systemVariables'), variables: SYSTEM_VARIABLES.map(variable => ({ path: `sys.${variable.name}`, label: t(`designer.systemVariableDescriptions.${variable.name}`), type: variable.type })) }))
const globalVariableGroups = computed(() => [systemVariableGroup.value, ...(environmentVariables.value.length ? [environmentVariableGroup.value] : [])])
const variableGroups = computed(() => selected.value ? [...globalVariableGroups.value, ...buildVariableCatalog(nodes.value as any[], currentCanvasEdges() as any[], selected.value.id)] : [])
const allVariableGroups = computed(() => [...globalVariableGroups.value, ...buildAllVariableCatalog(nodes.value as any[])])
const filteredVariableGroups = computed(() => {
  const query = variableSearch.value.trim().toLocaleLowerCase()
  if (!query) return allVariableGroups.value
  return allVariableGroups.value.map(group => ({ ...group, variables: group.variables.filter(variable => `${group.label} ${variable.label} ${variable.path} ${variable.type}`.toLocaleLowerCase().includes(query)) })).filter(group => group.variables.length)
})
const startNode = computed<any>(() => (nodes.value as any[]).find(node => String(node.data?.nodeType || node.type) === 'start'))
const startFields = computed<any[]>(() => startNode.value?.data?.config?.input_fields || [])
const { approvalComment, approvals, cancelingRun, cancelRun, clearRunOverlay, exitReplayMode, loadApprovals, loadLatestRunResults, loadRuns, nodeResults, openApprovals, openRunDialog, pendingApprovals, replayMode, replayRun, respondingApproval, respondApproval, result, retryingRun, retryRun, run, runError, runInputs, running, runNodeLabels, runs, runTargetLabel, runTargetNodeId, runtimeRunId, selectedApproval, selectedResult, selectedRun, showApprovals, showRunDialog, uploadingField, uploadRunFile } = useWorkflowRuns({ workspaceId, workflowId, startFields, nodes, selected, inspectorTab, activeSection, currentEdges: currentCanvasEdges, commitEdges, fitView } as any)
const nextNodes = computed<any[]>(() => {
  if (!selected.value) return []
  const targets = new Set((currentCanvasEdges() as any[]).filter(edge => edge.source === selected.value!.id).map(edge => edge.target))
  return (nodes.value as any[]).filter(node => targets.has(node.id))
})
const canUndo = computed(() => historyIndex.value > 0); const canRedo = computed(() => historyIndex.value < graphHistory.value.length - 1)
const zoomPercent = computed(() => Math.round(viewport.value.zoom * 100))
const paletteStyle = computed(() => ({ left: `${palettePosition.value.x}px`, top: `${palettePosition.value.y}px` }))
const validationIssues = computed(() => validateWorkflowGraph(nodes.value as any[], currentCanvasEdges() as any[]))
const actionableSelectionCount = computed(() => selectedCanvasNodes().length)
const visibleCommentPins = computed(() => comments.value.map((comment, index) => ({ comment, index: index + 1, count: comment.messages.length })))
const contextMenuProtected = computed(() => {
  const node = nodeContextMenu.value ? (nodes.value as any[]).find(item => item.id === nodeContextMenu.value?.nodeId) : null
  return ['start', 'end'].includes(String(node?.data?.nodeType || node?.type || ''))
})
const contextMenuCanChange = computed(() => {
  const node = nodeContextMenu.value ? (nodes.value as any[]).find(item => item.id === nodeContextMenu.value?.nodeId) : null
  return !['iteration', 'loop'].includes(String(node?.data?.nodeType || node?.type || ''))
})
const saveState = computed<'idle' | 'dirty' | 'saving' | 'saved' | 'error' | 'conflict'>(() => {
  if (saving.value) return 'saving'
  if (saveError.value) return saveConflict.value ? 'conflict' : 'error'
  if (dirty.value || workflowSlugDraft.value !== workflow.value?.slug) return 'dirty'
  return lastSavedAt.value ? 'saved' : 'idle'
})
const localHistoryEntries = computed(() => graphHistory.value.map((state, index) => ({ state, index, time: historyTimes.value[index] })).reverse())
const nodeTypes = { ...Object.fromEntries(['start', 'end', 'default', 'llm', 'image', 'agent', 'classifier', 'code', 'script', 'template', 'variable', 'json', 'aggregate', 'extract', 'list', 'http', 'condition', 'human', 'wait', 'delay', 'subworkflow', 'document', 'answer_filler', 'host_info', 'rdp_disconnect'].map(type => [type, markRaw(WorkflowNode)])), iteration: markRaw(WorkflowContainerNode), loop: markRaw(WorkflowContainerNode), note: markRaw(WorkflowNoteNode) }
const edgeTypes = { workflow: markRaw(WorkflowEdge) }
const paletteSections = computed(() => {
  const query = paletteQuery.value.trim().toLocaleLowerCase()
  const sections = [
    { key: 'ai', items: [{ type: 'agent', icon: BrainCircuit }, { type: 'llm', icon: Bot }, { type: 'image', icon: Images }, { type: 'end', icon: CircleStop }, { type: 'classifier', icon: ListFilter }] },
    { key: 'data', items: [{ type: 'document', icon: FileText }, { type: 'template', icon: FileText }, { type: 'variable', icon: ListTree }, { type: 'json', icon: Code2 }, { type: 'aggregate', icon: Combine }, { type: 'extract', icon: ScanText }, { type: 'list', icon: ListFilter }] },
    { key: 'tools', items: [{ type: 'code', icon: Code2 }, { type: 'script', icon: Braces }, { type: 'http', icon: Globe2 }] },
    { key: 'logic', items: [{ type: 'condition', icon: GitBranch }, { type: 'wait', icon: GitMerge }, { type: 'human', icon: UserCheck }, { type: 'iteration', icon: Repeat2 }, { type: 'loop', icon: RefreshCw }, { type: 'subworkflow', icon: Workflow }, { type: 'delay', icon: Timer }] },
  ]
  return sections.map(section => ({ ...section, items: section.items.filter(item => {
    if (paletteParentId.value && ['iteration', 'loop'].includes(item.type)) return false
    return !query || `${t(`workflow.nodes.${item.type}`)} ${t(`designer.nodeDescriptions.${item.type}`)}`.toLocaleLowerCase().includes(query)
  }) })).filter(section => section.items.length)
})
const commandAddItems = computed(() => paletteSections.value.flatMap(section => section.items.map(item => ({ type: item.type, label: t(`workflow.nodes.${item.type}`), description: t(`designer.nodeDescriptions.${item.type}`) }))))
const commandActions = computed(() => [
  { id: 'run', label: t('designer.commandActions.run'), shortcut: 'Alt R' },
  { id: 'save', label: t('designer.commandActions.save'), shortcut: 'Ctrl S' },
  { id: 'publish', label: t('designer.commandActions.publish') },
  { id: 'layout', label: t('designer.commandActions.layout') },
  { id: 'history', label: t('designer.commandActions.history') },
  { id: 'variables', label: t('designer.commandActions.variables') },
])
let saveTimer: ReturnType<typeof setTimeout> | undefined
let historyTimer: ReturnType<typeof setTimeout> | undefined
let selectionRestoreTimer: ReturnType<typeof setTimeout> | undefined
let activeSave: Promise<boolean> | null = null
let restoringHistory = false
let pendingSourceConnection: { sourceId: string; sourceHandle?: string } | null = null

function syncClassifierEdgeLabels() {
  const nodeById = new Map((nodes.value as any[]).map(node => [node.id, node]))
  commitEdges(currentCanvasEdges().map(edge => {
    const label = classifierBranchLabel(nodeById.get(edge.source), edge.sourceHandle)
    if (!label || edge.data?.branchLabel === label) return edge
    return { ...edge, data: { ...(edge.data || {}), branchLabel: label } }
  }) as Edge[])
}

function renameNodesAndReferences(currentNodes: any[], renames: NodeRename[]) {
  if (!renames.length) return currentNodes
  const references = renames.filter(rename => rename.from && currentNodes.filter(node => nodeReferenceName(node) === rename.from).length === 1)
  return currentNodes.map(node => {
    const rename = renames.find(item => item.id === node.id)
    return {
      ...node,
      data: {
        ...node.data,
        ...(rename ? { label: rename.to } : {}),
        config: rewriteNodeReferences(node.data?.config || {}, references),
      },
    }
  })
}

function replaceReferences(currentNodes: any[], renames: Array<Pick<NodeRename, 'from' | 'to'>>) {
  return currentNodes.map(node => ({
    ...node,
    data: { ...node.data, config: rewriteNodeReferences(node.data?.config || {}, renames) },
  }))
}

function startReferenceName(currentNodes: any[] = nodes.value as any[]) {
  const start = currentNodes.find(node => String(node.data?.nodeType || node.type) === 'start')
  return start ? nodeReferenceName(start) : t('workflow.nodes.start')
}

function withNamedStartReferences<T>(value: T, currentNodes: any[] = nodes.value as any[]): T {
  return rewriteNodeReferences(value, [{ from: 'inputs', to: startReferenceName(currentNodes) }])
}

function nodeNameErrorText(error: NodeNameError) {
  return t(`designer.nodeNameErrors.${error}`)
}

function updateSelectedNodeLabel(value: string) {
  if (!selected.value) return
  const name = value.trim()
  const error = validateNodeName(nodes.value as any[], selected.value.id, name)
  if (error) {
    nodeNameError.value = nodeNameErrorText(error)
    return
  }
  const oldName = nodeReferenceName(selected.value as any)
  nodeNameError.value = ''
  if (oldName === name) return
  const renamed = renameNodesAndReferences(nodes.value as any[], [{ id: selected.value.id, from: oldName, to: name }])
  nodes.value = renamed as Node[]
  selected.value = (renamed.find(node => node.id === selected.value!.id) || null) as Node | null
  syncConfigEditor()
}

function currentCanvasEdges() {
  return edges.value as Edge[]
}

function graphSnapshot() {
  const persisted = {
    nodes: (nodes.value as any[]).map(node => ({
      id: node.id,
      type: node.type,
      position: node.position,
      parentNode: node.parentNode,
      extent: node.extent,
      expandParent: node.expandParent,
      style: node.style,
      data: stripRuntimeData(node.data),
    })),
    edges: currentCanvasEdges().map(edge => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: edge.type,
      sourceHandle: edge.sourceHandle,
      targetHandle: edge.targetHandle,
      data: stripRuntimeData(edge.data),
    })),
    comments: comments.value.filter(comment => comment.messages.length).map(comment => structuredClone(comment)),
  }
  return JSON.parse(JSON.stringify(persisted)) as GraphState
}
function pushHistory() {
  if (!loaded.value || restoringHistory) return
  const snapshot = graphSnapshot(); const serialized = JSON.stringify(snapshot)
  if (JSON.stringify(graphHistory.value[historyIndex.value]) === serialized) return
  graphHistory.value = [...graphHistory.value.slice(0, historyIndex.value + 1), snapshot].slice(-60)
  historyTimes.value = [...historyTimes.value.slice(0, historyIndex.value + 1), new Date()].slice(-60)
  historyIndex.value = graphHistory.value.length - 1
}
function resetHistory() { graphHistory.value = [graphSnapshot()]; historyTimes.value = [new Date()]; historyIndex.value = 0 }
function restoreHistory(index: number) {
  const snapshot = graphHistory.value[index]
  if (!snapshot) return
  restoringHistory = true
  nodes.value = JSON.parse(JSON.stringify(snapshot.nodes)); commitEdges(JSON.parse(JSON.stringify(snapshot.edges))); comments.value = normalizeWorkflowComments(snapshot.comments); historyIndex.value = index; selected.value = null; selectedCommentId.value = null
  setTimeout(() => { restoringHistory = false }, 0)
}
function undo() { clearTimeout(historyTimer); pushHistory(); if (canUndo.value) restoreHistory(historyIndex.value - 1) }
function redo() { clearTimeout(historyTimer); if (canRedo.value) restoreHistory(historyIndex.value + 1) }

async function load() {
  loaded.value = false
  const { data } = await api.get(`/workspaces/${workspaceId.value}/workflows/${workflowId.value}`)
  workflow.value = data
  workflowSlugDraft.value = data.slug
  const removedKnowledgeNodeIds = new Set<string>(
    data.draft_graph.nodes
      .filter((node: any) => String(node.data?.nodeType || node.type) === 'knowledge')
      .map((node: any) => String(node.id)),
  )
  const legacyAnswerFillerMigration = migrateLegacyAnswerFillerNodes(
    data.draft_graph.nodes.filter((node: any) => !removedKnowledgeNodeIds.has(String(node.id))),
    scripts.value.find((script: any) => script.slug === 'english-exam-answer-filler'),
  )
  const draftNodes = legacyAnswerFillerMigration.nodes
  const draftStart = draftNodes.find((node: any) => String(node.data?.nodeType || node.type) === 'start')
  const draftInputFields = draftStart?.data?.config?.input_fields || []
  const localizedRenames: NodeRename[] = []
  let loadedNodes = draftNodes.map(node => {
    const nodeType = String(node.data?.nodeType || node.type)
    const defaults: Record<string, string[]> = { start: ['Start', '开始'], end: ['End', '结束'] }
    const baseConfig = nodeType === 'start' ? {
      triggers: [node.data?.config?.triggers?.[0] || 'form'],
      input_fields: (node.data?.config?.input_fields || [{ name: 'message', label: t('designer.defaultMessage'), type: 'text', required: false, placeholder: '' }]).map(normalizeStartField),
      schedule: { cron: '0 9 * * *', timezone: 'UTC', enabled: false, inputs_json: '{}', ...(node.data?.config?.schedule || {}) },
    } : nodeType === 'end' ? {
      ...defaultNodeConfig(nodeType),
      ...(node.data?.config || {}),
      outputs: normalizeEndOutputs(node.data?.config?.outputs, draftInputFields),
    } : nodeType === 'condition' ? normalizeConditionConfig(node.data?.config) : nodeType === 'classifier' ? normalizeClassifierConfig(node.data?.config) : nodeType === 'llm' ? normalizeLlmConfig(node.data?.config) : nodeType === 'image' ? normalizeImageConfig(node.data?.config) : nodeType === 'human' ? normalizeHumanConfig(node.data?.config) : { ...defaultNodeConfig(nodeType), ...(node.data?.config || {}) }
    const config = normalizeExecutionPolicy(nodeType, baseConfig)
    const label = defaults[nodeType]?.includes(String(node.data?.label)) ? t(`workflow.nodes.${nodeType}`) : node.data?.label
    if (String(node.data?.label || '').trim() && String(node.data?.label).trim() !== String(label || '').trim()) localizedRenames.push({ id: node.id, from: String(node.data?.label).trim(), to: String(label || '').trim() })
    return {
      id: node.id,
      type: node.type,
      position: node.position,
      parentNode: (node as any).parentNode,
      extent: (node as any).extent,
      expandParent: (node as any).expandParent,
      style: (node as any).style,
      data: { ...node.data, config, nodeType, label },
    }
  })
  loadedNodes = replaceReferences(loadedNodes, localizedRenames)
  const uniqueNames = ensureUniqueNodeNames(loadedNodes, (node: any) => t(`workflow.nodes.${String(node.data?.nodeType || node.type || 'default')}`))
  loadedNodes = uniqueNames.nodes
  const beforeReferenceMigration = JSON.stringify(loadedNodes.map((node: any) => node.data?.config || {}))
  loadedNodes = replaceReferences(loadedNodes, [{ from: 'inputs', to: startReferenceName(loadedNodes) }])
  const migrated = Boolean(legacyAnswerFillerMigration.migrated || removedKnowledgeNodeIds.size || localizedRenames.length || uniqueNames.renames.length || beforeReferenceMigration !== JSON.stringify(loadedNodes.map((node: any) => node.data?.config || {})))
  nodes.value = loadedNodes as Node[]
  const loadedEdges = data.draft_graph.edges
    .filter((edge: Edge) => !removedKnowledgeNodeIds.has(String(edge.source)) && !removedKnowledgeNodeIds.has(String(edge.target)))
    .map((edge: Edge) => ({ ...edge, type: 'workflow' }))
  commitEdges(loadedEdges)
  comments.value = normalizeWorkflowComments(data.draft_graph.comments)
  syncClassifierEdgeLabels()
  runtimeRunId.value = ''; nodeResults.value = {}
  resetHistory()
  await nextTick()
  editRevision.value = 0; dirty.value = false; saveError.value = ''; saveConflict.value = false
  loaded.value = true; lastSavedAt.value = new Date()
  if (migrated) { dirty.value = true; scheduleSave() }
  setTimeout(() => fitView({ padding: 0.2 }), 80)
}
async function loadResources() {
  const [modelsResponse, scriptsResponse, workflowsResponse] = await Promise.allSettled([
    api.get(`/workspaces/${workspaceId.value}/models`),
    api.get(`/workspaces/${workspaceId.value}/scripts`),
    api.get(`/workspaces/${workspaceId.value}/workflows`),
  ])
  modelProviders.value = modelsResponse.status === 'fulfilled' ? modelsResponse.value.data : []
  const scriptItems = scriptsResponse.status === 'fulfilled' ? scriptsResponse.value.data : []
  const scriptRuntimeResults = await Promise.allSettled(scriptItems.map((script: any) => api.get(`/workspaces/${workspaceId.value}/scripts/${script.id}/versions/${script.latest_version}`)))
  scripts.value = scriptItems.map((script: any, index: number) => {
    const runtime = scriptRuntimeResults[index]
    return runtime?.status === 'fulfilled'
      ? { ...script, input_schema: runtime.value.data.input_schema, output_schema: runtime.value.data.output_schema }
      : script
  })
  subworkflows.value = workflowsResponse.status === 'fulfilled' ? workflowsResponse.value.data.filter((item: any) => item.id !== workflowId.value) : []
}
async function loadEnvironmentVariables() {
  environmentVariables.value = (await api.get(`/workspaces/${workspaceId.value}/workflows/${workflowId.value}/environment-variables`)).data
}
async function createEnvironmentVariable(payload: { name: string; value_type: string; value: string; description: string }) {
  environmentSaving.value = true; environmentError.value = ''
  try { await api.post(`/workspaces/${workspaceId.value}/workflows/${workflowId.value}/environment-variables`, payload); await loadEnvironmentVariables(); environmentPanel.value?.markSaved() }
  catch (cause: any) { environmentError.value = cause.response?.data?.detail || String(cause) }
  finally { environmentSaving.value = false }
}
async function updateEnvironmentVariable(payload: { id: string; name: string; value_type: string; value?: string; description: string }) {
  environmentSaving.value = true; environmentError.value = ''
  const { id, ...body } = payload
  try { await api.put(`/workspaces/${workspaceId.value}/workflows/${workflowId.value}/environment-variables/${id}`, body); await loadEnvironmentVariables(); environmentPanel.value?.markSaved() }
  catch (cause: any) { environmentError.value = cause.response?.data?.detail || String(cause) }
  finally { environmentSaving.value = false }
}
async function deleteEnvironmentVariable(variableId: string) {
  environmentError.value = ''
  try { await api.delete(`/workspaces/${workspaceId.value}/workflows/${workflowId.value}/environment-variables/${variableId}`); await loadEnvironmentVariables() }
  catch (cause: any) { environmentError.value = cause.response?.data?.detail || String(cause) }
}
async function performSave() {
  const revisionAtStart = editRevision.value
  const snapshot = graphSnapshot()
  saving.value = true; saveError.value = ''; saveConflict.value = false
  try {
    const { data } = await api.put(`/workspaces/${workspaceId.value}/workflows/${workflowId.value}`, {
      name: workflow.value.name,
      description: workflow.value.description,
      slug: workflow.value.slug,
      graph: { schema_version: 1, ...snapshot },
      expected_version: workflow.value.draft_version,
    })
    workflow.value = data; lastSavedAt.value = new Date()
    dirty.value = editRevision.value !== revisionAtStart
    if (dirty.value) scheduleSave()
    return true
  } catch (cause: any) {
    const detail = cause.response?.data?.detail
    saveConflict.value = cause.response?.status === 409 && detail === 'Workflow was updated by another member'
    saveError.value = typeof detail === 'string' ? detail : String(cause)
    dirty.value = true
    return false
  }
  finally { saving.value = false }
}
function renameWorkflow(name: string) {
  if (!workflow.value || !name.trim() || name.trim() === workflow.value.name) return
  workflow.value = { ...workflow.value, name: name.trim() }
  editRevision.value += 1
  dirty.value = true
  saveError.value = ''
  saveConflict.value = false
  scheduleSave()
}
async function save(): Promise<boolean> {
  if (!loaded.value) return false
  while (activeSave) {
    if (!await activeSave) return false
  }
  if (!dirty.value) return true
  const attempt = performSave()
  activeSave = attempt
  try {
    if (!await attempt) return false
  } finally {
    if (activeSave === attempt) activeSave = null
  }
  return dirty.value ? save() : true
}
async function performWorkflowSlugSave() {
  const revisionAtStart = editRevision.value
  const snapshot = graphSnapshot()
  saving.value = true; saveError.value = ''; saveConflict.value = false
  try {
    const { data } = await api.put(`/workspaces/${workspaceId.value}/workflows/${workflowId.value}`, {
      name: workflow.value.name,
      description: workflow.value.description,
      slug: workflowSlugDraft.value.trim(),
      graph: { schema_version: 1, ...snapshot },
      expected_version: workflow.value.draft_version,
    })
    workflow.value = data
    workflowSlugDraft.value = data.slug
    lastSavedAt.value = new Date()
    dirty.value = editRevision.value !== revisionAtStart
    if (dirty.value) scheduleSave()
    return true
  } catch (cause: any) {
    const detail = cause.response?.data?.detail
    saveConflict.value = cause.response?.status === 409 && detail === 'Workflow was updated by another member'
    saveError.value = typeof detail === 'string' ? detail : String(cause)
    return false
  } finally {
    saving.value = false
  }
}
async function saveWorkflowSlug(): Promise<boolean> {
  if (!loaded.value || workflowSlugDraft.value === workflow.value?.slug) return true
  while (activeSave) {
    if (!await activeSave) return false
  }
  const attempt = performWorkflowSlugSave()
  activeSave = attempt
  try {
    return await attempt
  } finally {
    if (activeSave === attempt) activeSave = null
  }
}
async function saveAll(): Promise<boolean> {
  if (!await save()) return false
  return saveWorkflowSlug()
}
function scheduleSave() { clearTimeout(saveTimer); saveTimer = setTimeout(() => { void save() }, 1000) }
async function reloadDraftAfterConflict() {
  if (!window.confirm(t('designer.reloadConflictConfirm'))) return
  clearTimeout(saveTimer)
  await load()
}
function handleBeforeUnload(event: BeforeUnloadEvent) {
  if (!dirty.value && workflowSlugDraft.value === workflow.value?.slug && !saving.value) return
  event.preventDefault()
  event.returnValue = ''
}
async function publish(payload: any = { change_note: 'Published from designer', access: 'public' }) {
  if (validationIssues.value.length) { showChecklist.value = true; return }
  publishing.value = true; publishSuccess.value = ''
  try {
    if (!await saveAll()) return
    const { data } = await api.post(`/workspaces/${workspaceId.value}/workflows/${workflowId.value}/publish`, payload)
    workflow.value.published_version_id = data.id
    workflow.value.published_access = payload.access
    await loadVersions()
    publishSuccess.value = t('designer.publishSucceeded')
  } catch (cause: any) { saveError.value = cause.response?.data?.detail || String(cause) }
  finally { publishing.value = false }
}
async function loadVersions() { versions.value = (await api.get(`/workspaces/${workspaceId.value}/workflows/${workflowId.value}/versions`)).data }
async function openPublish() {
  await loadVersions()
  showChecklist.value = false; showEnvironment.value = false; showSystemVariables.value = false
  activeSection.value = 'api'
}
function toggleEnvironment() { environmentError.value = ''; showChecklist.value = false; showSystemVariables.value = false; showEnvironment.value = !showEnvironment.value }
function toggleSystemVariables() { showChecklist.value = false; showEnvironment.value = false; showSystemVariables.value = !showSystemVariables.value }
function openPublishedApp() { window.open(`${origin}/apps/${workflow.value.slug}`, '_blank', 'noopener,noreferrer') }
function openApiFromPublish() { showApiAccess.value = true }
async function openVersionHistoryFromPublish() { await openHistory() }
async function showSection(section: typeof activeSection.value) { activeSection.value = section; if (section === 'api') await loadVersions(); if (section === 'logs' || section === 'monitoring') await loadRuns() }
async function openHistory() { await loadVersions(); showHistory.value = true }
function openChangeHistory() { pushHistory(); showChangeHistory.value = true }
function restoreLocalSnapshot(index: number) { restoreHistory(index); showChangeHistory.value = false }
function versionDiff(item: any) {
  const current = graphSnapshot(); const version = item.graph || { nodes: [], edges: [] }
  const currentNodes = new Map(current.nodes.map(node => [node.id, node])); const versionNodes = new Map((version.nodes || []).map((node: any) => [node.id, node]))
  const added = [...currentNodes.keys()].filter(id => !versionNodes.has(id)).length
  const removed = [...versionNodes.keys()].filter(id => !currentNodes.has(id)).length
  const changed = [...currentNodes.keys()].filter(id => versionNodes.has(id) && JSON.stringify(currentNodes.get(id)?.data) !== JSON.stringify((versionNodes.get(id) as any)?.data)).length
  return { added, removed, changed, currentEdges: current.edges.length, versionEdges: (version.edges || []).length }
}
async function restorePublishedVersion() {
  if (!pendingRestoreVersion.value) return
  restoringVersion.value = true
  try {
    await api.post(`/workspaces/${workspaceId.value}/workflows/${workflowId.value}/versions/${pendingRestoreVersion.value.id}/restore`)
    pendingRestoreVersion.value = null; showHistory.value = false; selected.value = null
    await load()
  } catch (cause: any) { saveError.value = cause.response?.data?.detail || String(cause) }
  finally { restoringVersion.value = false }
}
function hasStartTrigger(trigger: string) { return selected.value?.data?.config?.triggers?.includes(trigger) }
function toggleStartTrigger(trigger: string) { if (selected.value) selected.value.data.config.triggers = [trigger] }
function addStartInput() {
  if (!selected.value) return
  const fields = selected.value.data.config.input_fields || []
  selected.value.data.config.input_fields = [...fields, normalizeStartField({ name: `field_${fields.length + 1}`, label: t('designer.newField') })]
  expandedStartFieldIndex.value = fields.length
}
function removeStartInput(index: string | number) {
  selected.value?.data?.config?.input_fields.splice(Number(index), 1)
  expandedStartFieldIndex.value = null
}
function toggleStartField(index: string | number) { expandedStartFieldIndex.value = expandedStartFieldIndex.value === Number(index) ? null : Number(index) }
function addStartFieldOption(field: any) { field.options = [...(field.options || []), `${t('designer.option')} ${(field.options || []).length + 1}`] }
function removeStartFieldOption(field: any, index: string | number) { field.options.splice(Number(index), 1) }
function addConditionClause() { selected.value?.data?.config?.conditions.push({ variable: '', operator: 'equals', value: '' }) }
function removeConditionClause(index: string | number) { selected.value?.data?.config?.conditions.splice(Number(index), 1) }
function addEndOutput() { if (selected.value) selected.value.data.config.outputs.push({ name: `output_${selected.value.data.config.outputs.length + 1}`, type: 'String', value: '' }) }
function removeEndOutput(index: string | number) { selected.value?.data?.config?.outputs.splice(Number(index), 1) }
function addClassifierCategory() { if (selected.value) selected.value.data.config.categories = [...(selected.value.data.config.categories || []), createClassifierCategory()] }
function removeClassifierCategory(index: number) {
  const category = selected.value?.data?.config?.categories?.[index]
  if (!selected.value || !category) return
  const handle = `category:${category.id}`
  commitEdges(currentCanvasEdges().filter(edge => !(edge.source === selected.value!.id && edge.sourceHandle === handle)))
  selected.value.data.config.categories.splice(index, 1)
}
function removeHumanAction(actionId: string) {
  if (!selected.value) return
  const handle = `action:${actionId}`
  commitEdges(currentCanvasEdges().filter(edge => !(edge.source === selected.value!.id && edge.sourceHandle === handle)))
  selected.value.data.config.actions = (selected.value.data.config.actions || []).filter((action: any) => action.id !== actionId)
}
function updateClassifierKeywords(category: any, value: string) { category.keywords = value.split(/[,，]/).map(item => item.trim()).filter(Boolean) }
function selectedCanvasNodes() {
  const canvasNodes = getNodes.value as any[]
  const selectedIds = new Set(canvasNodes.filter(node => node.selected).map(node => String(node.id)))
  if (selected.value) selectedIds.add(selected.value.id)
  let expanded = true
  while (expanded) {
    expanded = false
    for (const node of canvasNodes) if (node.parentNode && selectedIds.has(node.parentNode) && !selectedIds.has(node.id)) { selectedIds.add(node.id); expanded = true }
  }
  return canvasNodes.filter(node => selectedIds.has(node.id) && !['start', 'end'].includes(String(node.data?.nodeType || node.type)))
}
function selectedCanvasEdges() { return (currentCanvasEdges() as any[]).filter(edge => edge.selected) }
function clearSelectedCanvasEdges() {
  if (!(currentCanvasEdges() as any[]).some(edge => edge.selected)) return
  commitEdges(clearWorkflowEdgeSelection(currentCanvasEdges()) as Edge[])
}
function copySelection() {
  const selectedNodes = selectedCanvasNodes()
  if (!selectedNodes.length) return
  const ids = new Set(selectedNodes.map(node => node.id))
  const selectedEdges = (currentCanvasEdges() as any[]).filter(edge => ids.has(edge.source) && ids.has(edge.target))
  copiedGraph.value = JSON.parse(JSON.stringify({ nodes: selectedNodes, edges: selectedEdges })) as GraphState
}
function pasteSelection() {
  if (!copiedGraph.value?.nodes.length) return
  const idMap = new Map(copiedGraph.value.nodes.map(node => [node.id, `${String(node.type || 'node')}-${crypto.randomUUID().slice(0, 8)}`]))
  let existingNodes = (nodes.value as any[]).map(node => ({ ...node, selected: false }))
  const pastedNodes: any[] = []
  const referenceRenames: Array<Pick<NodeRename, 'from' | 'to'>> = []
  for (const copied of copiedGraph.value.nodes as any[]) {
    const type = String(copied.data?.nodeType || copied.type || 'default')
    const baseName = t(`workflow.nodes.${type}`)
    const preferred = nodeReferenceName(copied) || baseName
    const reservedNodes = [...existingNodes, ...pastedNodes]
    let name = nextUniqueNodeName(reservedNodes, preferred)
    if (preferred === baseName) {
      const allocation = allocateDefaultNodeName(reservedNodes, type, baseName)
      if (allocation.renames.length) {
        existingNodes = renameNodesAndReferences(existingNodes, allocation.renames)
        const renamedPasted = renameNodesAndReferences(pastedNodes, allocation.renames)
        pastedNodes.splice(0, pastedNodes.length, ...renamedPasted)
      }
      name = allocation.name
    }
    referenceRenames.push({ from: preferred, to: name })
    pastedNodes.push({
      ...copied,
      id: idMap.get(copied.id)!,
      parentNode: copied.parentNode ? (idMap.get(copied.parentNode) || copied.parentNode) : undefined,
      selected: true,
      position: copied.parentNode ? { x: copied.position.x + 24, y: copied.position.y + 24 } : { x: copied.position.x + 42, y: copied.position.y + 42 },
      data: { ...copied.data, label: name },
    })
  }
  const rewrittenPastedNodes = pastedNodes.map(node => ({
    ...node,
    data: { ...node.data, config: rewriteNodeReferences(node.data?.config || {}, referenceRenames) },
  }))
  const nextNodes = [
    ...existingNodes,
    ...rewrittenPastedNodes,
  ]
  nodes.value = nextNodes as Node[]
  commitEdges([...currentCanvasEdges(), ...copiedGraph.value.edges.map(edge => ({ ...edge, id: crypto.randomUUID(), source: idMap.get(edge.source)!, target: idMap.get(edge.target)! }))] as Edge[])
  selected.value = nextNodes.find(node => node.id === idMap.get(copiedGraph.value!.nodes[0].id)) || null
}
function duplicateSelection() { copySelection(); pasteSelection() }
function removeSelection() {
  const ids = new Set(selectedCanvasNodes().map(node => node.id))
  const edgeIds = new Set(selectedCanvasEdges().map(edge => edge.id))
  if (!ids.size && !edgeIds.size) return
  nodes.value = (nodes.value as any[]).filter(node => !ids.has(node.id)) as Node[]
  commitEdges(currentCanvasEdges().filter(edge => !edgeIds.has(edge.id) && !ids.has(edge.source) && !ids.has(edge.target)))
  selected.value = null
}
function clearSelection() {
  const selectedNodes = (getNodes.value as any[]).filter(node => node.selected)
  if (selectedNodes.length) removeSelectedNodes(selectedNodes)
  clearSelectedCanvasEdges()
  selected.value = null
  nodeNameError.value = ''
  nodeContextMenu.value = null
}
function clearNodeSelection() {
  const selectedNodes = (getNodes.value as any[]).filter(node => node.selected)
  if (selectedNodes.length) removeSelectedNodes(selectedNodes)
  selected.value = null
  nodeNameError.value = ''
  nodeContextMenu.value = null
}
function selectAllEditableNodes() {
  const editableNodes = (getNodes.value as any[]).filter(node => !['start', 'end'].includes(String(node.data?.nodeType || node.type)))
  if (!editableNodes.length) return
  addSelectedNodes(editableNodes)
  selected.value = editableNodes[0]
}
function selectOnlyCanvasNode(nodeId: string) {
  const target = (getNodes.value as any[]).find(node => node.id === nodeId) || (nodes.value as any[]).find(node => node.id === nodeId)
  if (!target) return null
  addSelectedNodes([target])
  selected.value = target
  nodeNameError.value = ''
  return target
}
function runNodeAction(nodeId: string, action: NodeAction) {
  const node = selectOnlyCanvasNode(nodeId)
  if (!node) return
  nodeContextMenu.value = null
  if (action === 'run') openRunDialog(nodeId)
  else if (action === 'change') openPaletteForReplacement(nodeId)
  else if (action === 'copy') copySelection()
  else if (action === 'duplicate') duplicateSelection()
  else if (action === 'delete') removeSelection()
}
function handleNodeAction(event: Event) {
  const detail = (event as CustomEvent<{ nodeId?: string; action?: NodeAction }>).detail
  if (detail?.nodeId && detail.action) runNodeAction(detail.nodeId, detail.action)
}
function openNodeContextMenu(payload: { event: MouseEvent | TouchEvent; node: Node }) {
  if (replayMode.value || !canvasHost.value) return
  payload.event.preventDefault()
  if (!('clientX' in payload.event)) return
  const rect = canvasHost.value.getBoundingClientRect()
  nodeContextMenu.value = {
    nodeId: payload.node.id,
    x: Math.max(8, Math.min(payload.event.clientX - rect.left, rect.width - 188)),
    y: Math.max(8, Math.min(payload.event.clientY - rect.top, rect.height - 188)),
  }
  selectOnlyCanvasNode(payload.node.id)
}
function autoLayout() {
  let laidOutNodes = (nodes.value as any[]).map(node => ({ ...node, position: { ...node.position }, style: node.style ? { ...node.style } : undefined }))
  const canvasEdges = currentCanvasEdges() as any[]
  for (const container of laidOutNodes.filter(node => !node.parentNode && ['iteration', 'loop'].includes(String(node.data?.nodeType || node.type)))) {
    const children = laidOutNodes.filter(node => node.parentNode === container.id)
    if (!children.length) continue
    const childIds = new Set(children.map(node => node.id))
    const arrangedChildren = layoutContainerChildren(children, canvasEdges.filter(edge => childIds.has(edge.source) && childIds.has(edge.target)))
    const positions = new Map(arrangedChildren.map(node => [node.id, node.position]))
    laidOutNodes = laidOutNodes.map(node => positions.has(node.id) ? { ...node, position: positions.get(node.id)! } : node)
    const size = containerSizeForChildren(laidOutNodes, container.id)
    laidOutNodes = laidOutNodes.map(node => node.id === container.id ? { ...node, style: { ...(node.style || {}), width: `${size.width}px`, height: `${size.height}px` } } : node)
  }
  const topLevel = laidOutNodes.filter(node => !node.parentNode)
  const topIds = new Set(topLevel.map(node => node.id))
  const laidOut = layoutWorkflow(topLevel, canvasEdges.filter(edge => topIds.has(edge.source) && topIds.has(edge.target)))
  const positions = new Map(laidOut.map(node => [node.id, node.position]))
  nodes.value = laidOutNodes.map(node => node.parentNode ? node : { ...node, position: positions.get(node.id) || node.position }) as Node[]
  setTimeout(() => fitView({ padding: 0.2 }), 50)
}
function validConnection(connection: Connection) { return isConnectionAllowed(nodes.value as any[], currentCanvasEdges() as any[], connection) }
function commitEdges(nextEdges: Edge[]) {
  const committed = mergeWorkflowEdges(nextEdges).map(edge => ({ ...edge, type: edge.type || 'workflow' })) as Edge[]
  edges.value = committed
}
async function appendEdge(edge: Edge) {
  commitEdges([...currentCanvasEdges(), edge])
  editRevision.value += 1
  dirty.value = true
  saveError.value = ''
  saveConflict.value = false
  scheduleSave()
}
function replacementText(current: unknown, oldType: string, newType: string, section: 'nodes' | 'nodeDescriptions') {
  const knownDefaults = Object.values(messages).map(locale => section === 'nodes'
    ? (locale as any).workflow?.nodes?.[oldType]
    : (locale as any).designer?.nodeDescriptions?.[oldType]).filter(Boolean)
  const value = String(current || '').trim()
  const usesDefault = knownDefaults.some(defaultValue => value === defaultValue || (value.startsWith(String(defaultValue)) && /^\d+$/u.test(value.slice(String(defaultValue).length))))
  if (value && !usesDefault) return value
  return t(section === 'nodes' ? `workflow.nodes.${newType}` : `designer.nodeDescriptions.${newType}`)
}
async function add(type: string, configOverride: Record<string, any> = {}) {
  if (paletteReplaceNodeId.value) {
    const oldNode = (nodes.value as any[]).find(node => node.id === paletteReplaceNodeId.value)
    if (!oldNode) return null
    const isContainer = ['iteration', 'loop'].includes(type)
    const oldType = String(oldNode.data?.nodeType || oldNode.type || '')
    const oldName = nodeReferenceName(oldNode)
    const baseName = t(`workflow.nodes.${type}`)
    const requestedName = replacementText(oldNode.data?.label, oldType, type, 'nodes')
    let replacementName = nextUniqueNodeName(nodes.value as any[], requestedName, [oldNode.id])
    if (requestedName === baseName) {
      const allocation = allocateDefaultNodeName((nodes.value as any[]).filter(node => node.id !== oldNode.id), type, baseName)
      if (allocation.renames.length) nodes.value = renameNodesAndReferences(nodes.value as any[], allocation.renames) as Node[]
      replacementName = allocation.name
    }
    const replacement: any = {
      id: oldNode.id,
      type,
      position: oldNode.position,
      ...(oldNode.parentNode ? { parentNode: oldNode.parentNode, extent: oldNode.extent || 'parent', expandParent: oldNode.expandParent ?? true } : {}),
      ...(isContainer ? { style: { width: '520px', height: '260px' } } : {}),
      selected: true,
      data: {
        label: replacementName,
        nodeType: type,
        description: replacementText(oldNode.data?.description, oldType, type, 'nodeDescriptions'),
        config: withNamedStartReferences({ ...defaultNodeConfig(type), ...configOverride }),
      },
    }
    const replaced = replaceWorkflowNode(nodes.value as any[], currentCanvasEdges() as any[], oldNode.id, replacement)
    nodes.value = (oldName && oldName !== replacementName ? replaceReferences(replaced.nodes as any[], [{ from: oldName, to: replacementName }]) : replaced.nodes) as Node[]
    commitEdges(replaced.edges as Edge[])
    selectOnlyCanvasNode(replacement.id)
    paletteOpen.value = false
    paletteReplaceNodeId.value = null
    await nextTick()
    setTimeout(focusSelected, 120)
    return replacement
  }
  const baseName = t(`workflow.nodes.${type}`)
  const allocation = allocateDefaultNodeName(nodes.value as any[], type, baseName)
  if (allocation.renames.length) nodes.value = renameNodesAndReferences(nodes.value as any[], allocation.renames) as Node[]
  const id = `${type}-${crypto.randomUUID().slice(0, 8)}`
  const sourceId = pendingSourceConnection?.sourceId || paletteSourceId.value
  const sourceHandle = pendingSourceConnection?.sourceHandle || paletteSourceHandle.value || undefined
  const source = sourceId ? (nodes.value as any[]).find(node => node.id === sourceId) : null
  const insertionEdge = paletteEdgeId.value ? (currentCanvasEdges() as any[]).find(edge => edge.id === paletteEdgeId.value) : null
  const edgeSource = insertionEdge ? (nodes.value as any[]).find(node => node.id === insertionEdge.source) : null
  const edgeTarget = insertionEdge ? (nodes.value as any[]).find(node => node.id === insertionEdge.target) : null
  const parentId = paletteParentId.value || source?.parentNode || (edgeSource?.parentNode && edgeSource.parentNode === edgeTarget?.parentNode ? edgeSource.parentNode : null)
  const requestedPosition = parentId
    ? nextContainerChildPosition(nodes.value as any[], parentId)
    : insertionEdge && edgeSource && edgeTarget
    ? { x: (edgeSource.position.x + edgeTarget.position.x) / 2, y: (edgeSource.position.y + edgeTarget.position.y) / 2 }
    : source ? { x: source.position.x + (['iteration', 'loop'].includes(String(source.data?.nodeType || source.type)) ? 580 : 270), y: source.position.y } : { x: 300 + Math.random() * 180, y: 140 + Math.random() * 240 }
  const position = insertionEdge
    ? requestedPosition
    : parentId
    ? requestedPosition
    : findAvailableNodePosition(nodes.value as any[], requestedPosition, { parentNode: parentId, ignoreIds: source ? [source.id] : [] })
  const isContainer = ['iteration', 'loop'].includes(type)
  const node = {
    id,
    type,
    position,
    ...(parentId ? { parentNode: parentId, extent: 'parent' as const, expandParent: true } : {}),
    ...(isContainer ? { style: { width: '520px', height: '260px' } } : {}),
    data: { label: allocation.name, nodeType: type, description: t(`designer.nodeDescriptions.${type}`), config: withNamedStartReferences({ ...defaultNodeConfig(type), ...configOverride }) },
  }
  if (insertionEdge) {
    const next = insertNodeOnEdge(nodes.value as any[], currentCanvasEdges() as any[], insertionEdge.id, node)
    nodes.value = next.nodes as Node[]
    addNodes(node as Node)
    await nextTick()
    commitEdges(next.edges as Edge[])
  } else {
    nodes.value = [...(nodes.value as any[]), node] as Node[]
    addNodes(node as Node)
    await nextTick()
    if (source) await appendEdge({ id: crypto.randomUUID(), source: source.id, sourceHandle, target: id, type: 'workflow', data: { branchLabel: classifierBranchLabel(source, sourceHandle) } } as Edge)
  }
  selectOnlyCanvasNode(node.id)
  paletteOpen.value = false
  paletteSourceId.value = null
  paletteSourceHandle.value = null
  paletteEdgeId.value = null
  paletteParentId.value = null
  paletteReplaceNodeId.value = null
  pendingSourceConnection = null
  await nextTick()
  if (parentId) resizeContainerToChildren(parentId)
  setTimeout(() => {
    if (parentId) resizeContainerToChildren(parentId)
    selectOnlyCanvasNode(node.id)
    focusSelected()
  }, 120)
  return node
}
async function addScriptSnippet(script: any) {
  const added = await add('script', { script_id: script.id, script_name: script.name, version: 'latest', input_schema: JSON.parse(JSON.stringify(script.input_schema || { type: 'object', properties: {} })), output_schema: JSON.parse(JSON.stringify(script.output_schema || { type: 'object', properties: {} })) })
  if (!added) return
  updateSelectedNodeLabel(nextUniqueNodeName(nodes.value as any[], script.name, [added.id]))
}
function addNoteAt(position?: { x: number; y: number }) {
  const name = allocateDefaultNodeName(nodes.value as any[], 'note', t('designer.noteTitleDefault'))
  if (name.renames.length) nodes.value = renameNodesAndReferences(nodes.value as any[], name.renames) as Node[]
  const note = { id: `note-${crypto.randomUUID().slice(0, 8)}`, type: 'note', position: position || { x: 260, y: 140 }, data: { label: name.name, description: '', nodeType: 'note', color: annotationColor.value } }
  nodes.value = [...(nodes.value as any[]), note] as Node[]; selectOnlyCanvasNode(note.id); paletteOpen.value = false; paletteEdgeId.value = null
  annotationMode.value = false
}
function toggleAnnotationMode() {
  annotationMode.value = !annotationMode.value
  if (annotationMode.value) { commentMode.value = false; showComments.value = false; interactionMode.value = 'pointer'; paletteOpen.value = false; nodeContextMenu.value = null; selected.value = null }
}
function handlePaneClick(event: MouseEvent) {
  nodeContextMenu.value = null
  const point = screenToFlowCoordinate({ x: event.clientX, y: event.clientY })
  if (annotationMode.value) { addNoteAt({ x: point.x - 110, y: point.y - 63 }); return }
  if (commentMode.value) { createCommentAt(point); return }
  paletteOpen.value = false
  clearSelection()
}
function restoreBoxSelection() {
  const selectedIds = new Set((nodes.value as any[]).filter(node => node.selected).map(node => node.id))
  if (!selectedIds.size) return
  clearTimeout(selectionRestoreTimer)
  selectionRestoreTimer = setTimeout(() => {
    nodes.value = (nodes.value as any[]).map(node => ({ ...node, selected: selectedIds.has(node.id) })) as Node[]
    selected.value = selectedIds.size === 1 ? nodes.value.find(node => selectedIds.has(node.id)) || null : null
  }, 0)
}
function handleCanvasMouseDown(event: MouseEvent) {
  if (event.button !== 1) return
  middlePanning.value = true
  paletteOpen.value = false
  nodeContextMenu.value = null
}
function stopMiddlePanning() { middlePanning.value = false }
function handleCanvasAuxClick(event: MouseEvent) { if (event.button === 1) event.preventDefault() }
function currentCommentAuthor() { return { author_id: auth.user?.id || '', author_name: auth.user?.display_name || auth.user?.email || t('designer.user') } }
function toggleCommentMode() {
  commentMode.value = !commentMode.value
  showComments.value = true
  annotationMode.value = false
  selected.value = null
  selectedCommentId.value = null
  interactionMode.value = 'pointer'
  paletteOpen.value = false; nodeContextMenu.value = null
}
function toggleCommentsPanel() {
  if (showComments.value || commentMode.value) {
    closeComments()
    return
  }
  toggleCommentMode()
}
function createCommentAt(position: { x: number; y: number }) {
  const now = new Date().toISOString()
  const thread: WorkflowCommentThread = { id: `comment-${crypto.randomUUID().slice(0, 12)}`, position, resolved: false, messages: [], created_at: now, updated_at: now }
  comments.value = [...comments.value.filter(item => item.messages.length), thread]
  selectedCommentId.value = thread.id
  showComments.value = true
  commentMode.value = false
}
function submitComment(payload: { threadId: string; content: string }) {
  const thread = comments.value.find(item => item.id === payload.threadId)
  if (!thread || !payload.content.trim()) return
  const now = new Date().toISOString(); const author = currentCommentAuthor()
  thread.messages.push({ id: `message-${crypto.randomUUID().slice(0, 12)}`, ...author, content: payload.content.trim(), created_at: now })
  thread.updated_at = now
}
function toggleCommentResolved(threadId: string) {
  const thread = comments.value.find(item => item.id === threadId)
  if (!thread) return
  thread.resolved = !thread.resolved; thread.updated_at = new Date().toISOString()
}
function deleteCommentThread(threadId: string) {
  comments.value = comments.value.filter(item => item.id !== threadId)
  if (selectedCommentId.value === threadId) selectedCommentId.value = null
}
function selectComment(threadId: string | null) { selectedCommentId.value = threadId; showComments.value = true; selected.value = null }
function closeComments() {
  comments.value = comments.value.filter(item => item.messages.length)
  selectedCommentId.value = null; showComments.value = false; commentMode.value = false
}
function commentPinStyle(comment: WorkflowCommentThread) {
  return { left: `${comment.position.x * viewport.value.zoom + viewport.value.x}px`, top: `${comment.position.y * viewport.value.zoom + viewport.value.y}px` }
}
function clampPalettePosition(x: number, y: number) {
  const host = canvasHost.value
  if (!host) return { x: Math.max(8, x), y: Math.max(8, y) }
  const rect = host.getBoundingClientRect()
  return { x: Math.max(8, Math.min(x, rect.width - 296)), y: Math.max(8, Math.min(y, rect.height - 568)) }
}
function positionPaletteAtClient(clientX?: number, clientY?: number, sourceId?: string) {
  const host = canvasHost.value
  if (!host) return
  const hostRect = host.getBoundingClientRect()
  if (Number.isFinite(clientX) && Number.isFinite(clientY)) {
    const openLeft = Number(clientX) - hostRect.left + 12
    const x = openLeft + 288 > hostRect.width ? Number(clientX) - hostRect.left - 300 : openLeft
    palettePosition.value = clampPalettePosition(x, Number(clientY) - hostRect.top - 36)
    return
  }
  const element = sourceId ? host.querySelector<HTMLElement>(`.vue-flow__node[data-id="${CSS.escape(sourceId)}"]`) : null
  if (element) {
    const rect = element.getBoundingClientRect()
    const openLeft = rect.right - hostRect.left + 12
    const x = openLeft + 288 > hostRect.width ? rect.left - hostRect.left - 300 : openLeft
    palettePosition.value = clampPalettePosition(x, rect.top - hostRect.top)
    return
  }
  palettePosition.value = clampPalettePosition(64, hostRect.height / 2 - 280)
}
function openPalette() {
  pendingSourceConnection = null
  paletteSourceId.value = null; paletteSourceHandle.value = null; paletteEdgeId.value = null; paletteParentId.value = null; paletteReplaceNodeId.value = null; paletteQuery.value = ''; paletteTab.value = 'nodes'
  if (!paletteOpen.value) positionPaletteAtClient()
  paletteOpen.value = !paletteOpen.value
}
function handleQuickAdd(event: Event) {
  const detail = (event as CustomEvent<{ sourceId?: string; sourceHandle?: string; clientX?: number; clientY?: number }>).detail
  const sourceId = detail?.sourceId
  if (!sourceId) return
  openPaletteForSource(sourceId, detail?.sourceHandle, detail.clientX, detail.clientY)
}
function openPaletteForSource(sourceId: string, sourceHandle?: string, clientX?: number, clientY?: number) { pendingSourceConnection = { sourceId, sourceHandle }; paletteSourceId.value = sourceId; paletteSourceHandle.value = sourceHandle || null; paletteEdgeId.value = null; paletteParentId.value = null; paletteReplaceNodeId.value = null; paletteQuery.value = ''; paletteTab.value = 'nodes'; positionPaletteAtClient(clientX, clientY, sourceId); paletteOpen.value = true }
function openPaletteForReplacement(nodeId: string) {
  pendingSourceConnection = null
  paletteSourceId.value = null; paletteSourceHandle.value = null; paletteEdgeId.value = null; paletteParentId.value = null; paletteReplaceNodeId.value = nodeId; paletteQuery.value = ''; paletteTab.value = 'nodes'
  positionPaletteAtClient(undefined, undefined, nodeId)
  paletteOpen.value = true
}
function handleContainerAdd(event: Event) {
  const detail = (event as CustomEvent<{ parentId?: string; clientX?: number; clientY?: number }>).detail
  const parentId = detail?.parentId
  if (!parentId) return
  pendingSourceConnection = null; paletteParentId.value = parentId; paletteSourceId.value = null; paletteSourceHandle.value = null; paletteEdgeId.value = null; paletteReplaceNodeId.value = null; paletteQuery.value = ''; paletteTab.value = 'nodes'; positionPaletteAtClient(detail.clientX, detail.clientY, parentId); paletteOpen.value = true
}
function handleContainerDelete(event: Event) {
  const parentId = (event as CustomEvent<{ parentId?: string }>).detail?.parentId
  if (!parentId) return
  const ids = new Set([parentId, ...(nodes.value as any[]).filter(node => node.parentNode === parentId).map(node => node.id)])
  nodes.value = (nodes.value as any[]).filter(node => !ids.has(node.id)) as Node[]
  commitEdges(currentCanvasEdges().filter(edge => !ids.has(edge.source) && !ids.has(edge.target)))
  selected.value = null
}
function handleEdgeDelete(event: Event) {
  const edgeId = (event as CustomEvent<{ edgeId?: string }>).detail?.edgeId
  if (!edgeId) return
  commitEdges(removeWorkflowEdgeById(currentCanvasEdges(), edgeId))
}
function resizeContainerToChildren(parentId: string) {
  const size = containerSizeForChildren(nodes.value as any[], parentId)
  nodes.value = (nodes.value as any[]).map(node => node.id === parentId
    ? { ...node, style: { ...(node.style || {}), width: `${size.width}px`, height: `${size.height}px` } }
    : node) as Node[]
}
function handleNodeDragStop(payload: { node: Node }) {
  const parentId = String((payload.node as any)?.parentNode || '')
  if (parentId) nextTick(() => resizeContainerToChildren(parentId))
}
function focusSelected() {
  if (!selected.value) return
  const width = Number((selected.value as any).dimensions?.width || 206)
  const height = Number((selected.value as any).dimensions?.height || 90)
  const position = absoluteNodePosition(nodes.value as any[], selected.value.id)
  setCenter(position.x + width / 2, position.y + height / 2, {
    zoom: Math.min(1.1, Math.max(0.8, viewport.value.zoom)),
    duration: 300,
  })
}
function focusCommandNode(nodeId: string) {
  const node = (nodes.value as any[]).find(item => item.id === nodeId)
  if (!node) return
  selectOnlyCanvasNode(nodeId)
  inspectorTab.value = 'settings'
  nextTick(() => setTimeout(focusSelected, 50))
}
function focusTraceNode(nodeId: string) {
  activeSection.value = 'orchestration'
  nextTick(() => focusCommandNode(nodeId))
}
function addCommandNode(type: string) {
  paletteSourceId.value = null; paletteSourceHandle.value = null; paletteEdgeId.value = null; paletteParentId.value = null; paletteReplaceNodeId.value = null
  add(type)
}
function executeCommand(id: string) {
  if (id === 'run') openRunDialog()
  else if (id === 'save') saveAll()
  else if (id === 'publish') openPublish()
  else if (id === 'layout') autoLayout()
  else if (id === 'history') openHistory()
  else if (id === 'variables') { activeSection.value = 'orchestration'; showVariableInspector.value = true }
}
function syncConfigEditor() {
  configError.value = ''
  const config = selected.value?.data?.config || {}
  configText.value = JSON.stringify(config, null, 2)
  configBuffers.value = {
    values: JSON.stringify(config.values || {}, null, 2),
    jsonValue: JSON.stringify(config.value || {}, null, 2),
    httpHeaders: JSON.stringify(config.headers || {}, null, 2),
    httpQuery: JSON.stringify(config.query || {}, null, 2),
    httpBody: config.body == null ? '' : JSON.stringify(config.body, null, 2),
    llmSchema: JSON.stringify(config.response_schema || { type: 'object', properties: {} }, null, 2),
  }
  configFieldErrors.value = {}
}
function updateSelectedConfig() {
  if (!selected.value) return
  try { selected.value.data.config = JSON.parse(configText.value || '{}'); configError.value = '' }
  catch { configError.value = t('designer.invalidJson') }
}
function updateStructuredField(field: string, buffer: keyof typeof configBuffers.value) {
  if (!selected.value) return
  const value = configBuffers.value[buffer]
  try {
    selected.value.data.config[field] = value.trim() ? JSON.parse(value) : (field === 'body' ? null : {})
    const errors = { ...configFieldErrors.value }; delete errors[buffer]; configFieldErrors.value = errors
  } catch { configFieldErrors.value = { ...configFieldErrors.value, [buffer]: t('designer.invalidJson') } }
}
function selectModelProvider() {
  if (!selected.value) return
  const provider = modelProviders.value.find(item => item.id === selected.value!.data.config.provider_id)
  if (provider) { selected.value.data.config.provider_name = provider.name; selected.value.data.config.model = provider.default_model }
}
function selectSubworkflow() {
  if (!selected.value) return
  const target = subworkflows.value.find(item => item.id === selected.value!.data.config.workflow_id)
  if (target) selected.value.data.config.workflow_name = target.name
}
function selectNode(event: NodeMouseEvent) {
  closeComments()
  selectOnlyCanvasNode(event.node.id)
  inspectorTab.value = 'settings'
  nextTick(() => setTimeout(focusSelected, 120))
}
function issueText(issue: WorkflowValidationIssue) { return t(`designer.validation.${issue.code}`, issue.params || {}) }
function syncValidationOverlay() {
  const messages = new Map<string, string[]>()
  for (const issue of validationIssues.value) {
    if (!issue.nodeId) continue
    messages.set(issue.nodeId, [...(messages.get(issue.nodeId) || []), issueText(issue)])
  }
  for (const node of nodes.value as any[]) {
    const next = messages.get(node.id) || []
    const current = Array.isArray(node.data?.validationMessages) ? node.data.validationMessages : []
    if (JSON.stringify(current) === JSON.stringify(next)) continue
    if (next.length) node.data.validationMessages = next
    else delete node.data.validationMessages
  }
}
function jumpToIssue(issue: WorkflowValidationIssue) {
  showChecklist.value = false
  if (!issue.nodeId) return
  const node = selectOnlyCanvasNode(issue.nodeId)
  if (!node) return
  inspectorTab.value = 'settings'
  nextTick(() => setTimeout(focusSelected, 120))
}
function handleNodeValidation(event: Event) {
  const nodeId = (event as CustomEvent<{ nodeId?: string }>).detail?.nodeId
  const issue = validationIssues.value.find(item => item.nodeId === nodeId)
  if (issue) jumpToIssue(issue)
}
function toggleLocale() { preferences.setLocale(preferences.locale === 'zh' ? 'en' : 'zh') }
function toggleTheme() { preferences.setTheme(preferences.isDark ? 'light' : 'dark') }
function toggleSidebar() { sidebarCollapsed.value = !sidebarCollapsed.value }
async function copyVariableReference(path: string) {
  const value = `{{${path}}}`
  try { await navigator.clipboard.writeText(value) }
  catch {
    const input = document.createElement('textarea'); input.value = value; input.style.position = 'fixed'; input.style.opacity = '0'; document.body.appendChild(input); input.select(); document.execCommand('copy'); input.remove()
  }
  copiedVariablePath.value = path
  window.setTimeout(() => { if (copiedVariablePath.value === path) copiedVariablePath.value = '' }, 1600)
}
function runtimeVariableValue(path: string) {
  if (path.startsWith('env.')) return environmentVariables.value.find(variable => variable.name === path.slice(4))?.value
  if (path.startsWith('sys.')) {
    const key = path.slice(4)
    const values: Record<string, any> = { user_id: auth.user?.id, app_id: workflowId.value, workflow_id: workflowId.value, workflow_run_id: runtimeRunId.value || undefined, timestamp: selectedRun.value?.created_at ? Math.floor(new Date(selectedRun.value.created_at).getTime() / 1000) : undefined }
    return values[key]
  }
  return readRuntimeVariable(path, nodeResults.value, nodes.value as any[])
}
function variableReference(path: string) { return `{{${path}}}` }
function formatRuntimeValue(value: any) {
  if (value === undefined) return t('designer.notRunYet')
  if (typeof value === 'string') return value
  try { return JSON.stringify(value, null, 2) } catch { return String(value) }
}
function handleKeydown(event: KeyboardEvent) {
  const command = event.ctrlKey || event.metaKey; const key = event.key?.toLowerCase() ?? ''
  if (command && key === 'k') { event.preventDefault(); showCommandPalette.value = !showCommandPalette.value; return }
  if (event.key === 'Escape' && showCommandPalette.value) { showCommandPalette.value = false; return }
  if (event.key === 'Escape' && paletteOpen.value) { paletteOpen.value = false; paletteReplaceNodeId.value = null; return }
  if (event.key === 'Escape' && (annotationMode.value || commentMode.value)) { annotationMode.value = false; commentMode.value = false; return }
  const target = event.target as HTMLElement | null
  if (target?.matches('input, textarea, select, [contenteditable="true"]')) return
  if (event.altKey && key === 'r') { event.preventDefault(); openRunDialog() }
  else if (command && key === 's') { event.preventDefault(); save() }
  else if (command && key === 'z') { event.preventDefault(); event.shiftKey ? redo() : undo() }
  else if (command && key === 'y') { event.preventDefault(); redo() }
  else if (command && key === 'a') { event.preventDefault(); selectAllEditableNodes() }
  else if (command && key === 'c') { event.preventDefault(); copySelection() }
  else if (command && key === 'v') { event.preventDefault(); pasteSelection() }
  else if (command && key === 'd') { event.preventDefault(); duplicateSelection() }
  else if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); removeSelection() }
}
onConnect(connection => {
  if (!validConnection(connection)) return
  void appendEdge({ ...connection, id: crypto.randomUUID(), type: 'workflow' } as Edge)
})
watch(() => JSON.stringify(graphSnapshot()), () => {
  if (!loaded.value) return
  editRevision.value += 1
  dirty.value = true
  saveError.value = ''
  saveConflict.value = false
  scheduleSave()
  if (!restoringHistory) { clearTimeout(historyTimer); historyTimer = setTimeout(pushHistory, 250) }
}, { deep: true })
watch(() => selected.value?.id, syncConfigEditor)
watch(() => (nodes.value as any[]).map(node => node.id).join(','), () => {
  if (selected.value && !(nodes.value as any[]).some(node => node.id === selected.value!.id)) selected.value = null
})
watch(() => JSON.stringify(selected.value?.data?.config || {}), () => { if (!configEditing.value) syncConfigEditor(); if (selectedType.value === 'classifier') syncClassifierEdgeLabels() })
watch(() => validationIssues.value.map(issue => `${issue.nodeId || ''}|${issue.code}|${issueText(issue)}`).join('\n'), syncValidationOverlay, { immediate: true })
onBeforeRouteLeave(() => (!dirty.value && workflowSlugDraft.value === workflow.value?.slug && !saving.value) || window.confirm(t('designer.unsavedLeaveConfirm')))
onMounted(async () => { window.addEventListener('keydown', handleKeydown); window.addEventListener('mouseup', stopMiddlePanning); window.addEventListener('blur', stopMiddlePanning); window.addEventListener('beforeunload', handleBeforeUnload); window.addEventListener('workflow-quick-add', handleQuickAdd); window.addEventListener('workflow-node-action', handleNodeAction); window.addEventListener('workflow-node-validation', handleNodeValidation); window.addEventListener('workflow-container-add', handleContainerAdd); window.addEventListener('workflow-container-delete', handleContainerDelete); window.addEventListener('workflow-edge-delete', handleEdgeDelete); await workspaces.load(); await loadResources(); await Promise.all([load(), loadApprovals(), loadEnvironmentVariables()]); await loadLatestRunResults() })
onUnmounted(() => { clearTimeout(saveTimer); clearTimeout(historyTimer); clearTimeout(selectionRestoreTimer); window.removeEventListener('keydown', handleKeydown); window.removeEventListener('mouseup', stopMiddlePanning); window.removeEventListener('blur', stopMiddlePanning); window.removeEventListener('beforeunload', handleBeforeUnload); window.removeEventListener('workflow-quick-add', handleQuickAdd); window.removeEventListener('workflow-node-action', handleNodeAction); window.removeEventListener('workflow-node-validation', handleNodeValidation); window.removeEventListener('workflow-container-add', handleContainerAdd); window.removeEventListener('workflow-container-delete', handleContainerDelete); window.removeEventListener('workflow-edge-delete', handleEdgeDelete) })
</script>

<template>
  <div class="flex h-screen overflow-hidden bg-[var(--app-bg)]">
    <WorkflowDesignerSidebar
      class="hidden lg:flex"
      :collapsed="sidebarCollapsed"
      :workflow-name="workflow?.name"
      :user-name="auth.user?.display_name"
      :active-section="activeSection"
      :dark="preferences.isDark"
      @back="router.push(`/w/${workspaceId}/studio`)"
      @toggle-collapsed="toggleSidebar"
      @search="showCommandPalette = true"
      @select-section="showSection"
      @toggle-locale="toggleLocale"
      @toggle-theme="toggleTheme"
      @help="showHelp = true"
      @rename-workflow="renameWorkflow"
    />

    <div class="flex min-w-0 flex-1 flex-col">
      <header class="designer-main-header flex h-12 shrink-0 items-center border-b border-[var(--border)] bg-[var(--panel)] px-4 transition-[padding]" :class="[replayMode && 'pr-[446px]', { 'inspector-open': selected }]">
        <button class="icon-button mr-1 lg:hidden" :title="t('workflow.back')" :aria-label="t('workflow.back')" @click="router.push(`/w/${workspaceId}/studio`)"><ArrowLeft :size="16" /></button>
        <template v-if="replayMode">
          <div class="flex items-center gap-2 text-xs"><Activity :size="14" class="text-[var(--primary)]" /><span class="font-semibold">{{ t(`designer.triggerShort.${selectedRun?.triggered_by || 'studio'}`) }} ({{ selectedRun ? new Date(selectedRun.created_at).toLocaleTimeString() : '' }})</span><span class="muted">·</span><span class="rounded bg-[var(--panel-subtle)] px-2 py-1 text-[10px] font-medium">{{ t('designer.readOnly') }}</span></div>
          <Button class="ml-auto" variant="secondary" @click="exitReplayMode"><ArrowLeft :size="14" />{{ t('designer.returnToEdit') }}</Button>
        </template>
        <template v-else>
          <div class="flex min-w-0 items-center gap-1.5">
            <WorkflowSaveStatus :state="saveState" :saved-at="lastSavedAt" :error="saveError" @retry="save" @reload="reloadDraftAfterConflict" />
            <span v-if="workflow?.published_version_id" class="muted whitespace-nowrap text-xs">· {{ t('studio.published') }}</span>
          </div>
          <button v-if="runtimeRunId" class="ml-3 flex h-7 items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 text-[10px] font-semibold text-emerald-700 hover:bg-emerald-100 dark:bg-emerald-950/40 dark:text-emerald-300" :title="t('designer.clearRunOverlay')" @click="clearRunOverlay"><Activity :size="12" />{{ t('designer.runOverlay') }} · {{ runtimeRunId.slice(0, 8) }}<X :size="11" /></button>
          <div class="designer-header-actions ml-auto flex items-center gap-2">
            <Button variant="secondary" :loading="running && !runTargetNodeId" @click="openRunDialog()"><Play :size="14" />{{ t('workflow.run') }}<kbd class="ml-1 rounded border border-[var(--border)] bg-[var(--panel-subtle)] px-1 py-0.5 text-[9px] font-normal text-[var(--muted)]">Alt R</kbd></Button>
          <button class="icon-button surface relative" :title="t('designer.pendingApprovals')" :aria-label="t('designer.pendingApprovals')" @click="openApprovals()"><UserCheck :size="16" /><span v-if="pendingApprovals.length" class="absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500 px-1 text-[8px] font-bold text-white">{{ pendingApprovals.length }}</span></button>
          <button class="icon-button surface" :title="t('designer.history')" @click="openHistory"><History :size="16" /></button>
          <div class="relative">
            <button class="icon-button surface relative" :class="{ 'text-amber-600': validationIssues.length }" :aria-label="`${t('designer.checklist')} (${validationIssues.length})`" :title="t('designer.checklist')" @click="showEnvironment = false; showSystemVariables = false; showChecklist = !showChecklist">
              <ListChecks :size="16" /><span v-if="validationIssues.length" class="absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500 px-1 text-[9px] font-bold text-white">{{ validationIssues.length }}</span>
            </button>
            <div v-if="showChecklist" class="surface absolute right-0 top-10 z-50 w-80 overflow-hidden rounded-lg shadow-xl">
              <div class="flex items-center gap-2 border-b border-[var(--border)] px-4 py-3"><ListChecks :size="16" /><span class="text-sm font-semibold">{{ t('designer.checklist') }}</span><span class="muted ml-auto text-xs">{{ validationIssues.length ? t('designer.issueCount', { count: validationIssues.length }) : t('designer.readyToPublish') }}</span></div>
              <div v-if="validationIssues.length" class="max-h-80 overflow-y-auto p-2"><button v-for="(issue, index) in validationIssues" :key="`${issue.code}-${issue.nodeId || index}`" class="flex w-full items-start gap-2 rounded-md px-2.5 py-2 text-left text-xs hover:bg-[var(--panel-subtle)]" @click="jumpToIssue(issue)"><AlertTriangle :size="14" class="mt-0.5 shrink-0 text-amber-600" /><span class="leading-5">{{ issueText(issue) }}</span><ChevronRight v-if="issue.nodeId" :size="13" class="muted ml-auto mt-1 shrink-0" /></button></div>
              <div v-else class="px-4 py-8 text-center"><span class="mx-auto flex h-9 w-9 items-center justify-center rounded-full bg-emerald-50 text-emerald-600 dark:bg-emerald-950/40"><Check :size="18" /></span><p class="mt-2 text-sm font-medium">{{ t('designer.readyToPublish') }}</p><p class="muted mt-1 text-xs">{{ t('designer.noValidationIssues') }}</p></div>
            </div>
          </div>
          <div class="relative">
            <button class="header-env-button surface flex items-center justify-center rounded-lg px-2 font-mono text-[9px] font-bold" :class="showEnvironment && 'border-[var(--primary)] text-[var(--primary)]'" :title="t('designer.environmentVariables')" :aria-label="t('designer.environmentVariables')" @click="toggleEnvironment">ENV</button>
            <WorkflowEnvironmentPanel v-if="showEnvironment" ref="environmentPanel" :variables="environmentVariables" :saving="environmentSaving" :error="environmentError" @close="showEnvironment = false" @create="createEnvironmentVariable" @update="updateEnvironmentVariable" @delete="deleteEnvironmentVariable" />
          </div>
          <div class="relative">
            <button class="icon-button surface" :class="showSystemVariables && 'text-[var(--primary)]'" :title="t('designer.systemVariables')" :aria-label="t('designer.systemVariables')" @click="toggleSystemVariables"><Braces :size="15" /></button>
            <WorkflowSystemVariablesPanel v-if="showSystemVariables" @close="showSystemVariables = false" />
          </div>
          <button class="icon-button surface" :title="t('common.save')" @click="saveAll"><Save :size="16" /></button>
          </div>
        </template>
      </header>

      <div v-if="activeSection === 'orchestration'" class="flex min-h-0 flex-1">
        <section ref="canvasHost" class="designer-canvas-host relative min-w-0 flex-1" :class="{ 'inspector-open': selected && !showComments }" @mousedown="handleCanvasMouseDown" @auxclick="handleCanvasAuxClick">
          <VueFlow v-if="loaded" v-model:nodes="nodes" v-model:edges="edges" :node-types="nodeTypes" :edge-types="edgeTypes" :default-edge-options="{ type: 'workflow' }" :is-valid-connection="validConnection" :pan-on-drag="interactionMode === 'hand' || replayMode ? [0, 1] : [1]" :selection-key-code="interactionMode === 'pointer' && !replayMode && !annotationMode && !commentMode ? true : null" :nodes-draggable="interactionMode === 'pointer' && !replayMode && !annotationMode && !commentMode" :nodes-connectable="interactionMode === 'pointer' && !replayMode && !annotationMode && !commentMode" :elements-selectable="interactionMode === 'pointer' && !replayMode && !annotationMode && !commentMode" fit-view-on-init class="workflow-canvas" :class="{ 'replay-mode': replayMode, 'annotation-mode': annotationMode || commentMode, 'middle-panning': middlePanning }" @node-click="event => { nodeContextMenu = null; if (!replayMode && !annotationMode && !commentMode) selectNode(event) }" @node-context-menu="openNodeContextMenu" @node-drag-stop="handleNodeDragStop" @selection-end="restoreBoxSelection" @edge-click="clearNodeSelection" @pane-click="handlePaneClick">
            <Background :gap="18" :size="1" pattern-color="var(--border)" />
            <MiniMap pannable zoomable position="bottom-right" />
          </VueFlow>
          <div v-for="entry in visibleCommentPins" :key="entry.comment.id" class="absolute z-10 -translate-x-1/2 -translate-y-1/2" :style="commentPinStyle(entry.comment)">
            <WorkflowCommentPin :count="entry.count" :selected="selectedCommentId === entry.comment.id" :resolved="entry.comment.resolved" :label="t('designer.commentPinLabel', { index: entry.index })" @select="selectComment(entry.comment.id)" />
          </div>
          <div v-if="nodeContextMenu" class="absolute z-30" :style="{ left: `${nodeContextMenu.x}px`, top: `${nodeContextMenu.y}px` }" @click.stop>
            <NodeActionMenu :protected-node="contextMenuProtected" :can-change="contextMenuCanChange" @action="runNodeAction(nodeContextMenu.nodeId, $event)" />
          </div>
          <AnnotationPlacementToolbar v-if="annotationMode && !replayMode" v-model:color="annotationColor" class="absolute left-1/2 top-3 z-20 -translate-x-1/2" @cancel="annotationMode = false" />
          <SelectionToolbar v-else-if="actionableSelectionCount > 1 && !replayMode" class="absolute left-1/2 top-3 z-20 -translate-x-1/2" :count="actionableSelectionCount" @copy="copySelection" @duplicate="duplicateSelection" @delete="removeSelection" @clear="clearSelection" />
          <button v-else-if="selected && !replayMode" class="surface absolute left-1/2 top-3 z-10 flex h-7 -translate-x-1/2 items-center gap-1.5 rounded-md px-3 text-[11px] shadow-sm hover:bg-[var(--panel-subtle)]" @click="focusSelected"><MousePointer2 :size="12" />{{ t('designer.focusSelected') }}</button>
          <WorkflowCanvasControls
            v-if="!replayMode"
            v-model:interaction-mode="interactionMode"
            :annotation-active="annotationMode"
            :comments-active="commentMode || showComments"
            :can-copy="Boolean(selectedCanvasNodes().length)"
            :can-paste="Boolean(copiedGraph)"
            :can-delete="Boolean(selectedCanvasNodes().length || selectedCanvasEdges().length)"
            :can-undo="canUndo"
            :can-redo="canRedo"
            :zoom-percent="zoomPercent"
            @add-node="openPalette"
            @toggle-annotation="toggleAnnotationMode"
            @fit-view="fitView({ padding: 0.2 })"
            @toggle-comments="toggleCommentsPanel"
            @auto-layout="autoLayout"
            @copy="copySelection"
            @paste="pasteSelection"
            @delete="removeSelection"
            @undo="undo"
            @redo="redo"
            @history="openChangeHistory"
            @zoom-out="zoomOut()"
            @zoom-in="zoomIn()"
          />
          <NodePalette v-if="paletteOpen && !replayMode" v-model:query="paletteQuery" v-model:active-tab="paletteTab" class="absolute z-30" :style="paletteStyle" :sections="paletteSections" :scripts="scripts" :data-source-id="paletteSourceId || ''" :data-source-found="Boolean(paletteSourceId && nodes.some(node => node.id === paletteSourceId))" @add="add" @add-script="addScriptSnippet" @close="paletteOpen = false; paletteReplaceNodeId = null" />
          <div v-if="!replayMode" class="absolute bottom-4 left-1/2 z-20 -translate-x-1/2">
            <button class="surface flex h-8 items-center gap-1.5 rounded-lg px-3 text-[11px] font-semibold shadow-lg hover:bg-[var(--panel-subtle)]" :class="showVariableInspector && 'text-[var(--primary)]'" @click="showVariableInspector = !showVariableInspector"><ListTree :size="13" />{{ t('designer.variableInspector') }}<span class="muted">{{ allVariableGroups.reduce((total, group) => total + group.variables.length, 0) }}</span></button>
            <div v-if="showVariableInspector" class="surface absolute bottom-11 left-1/2 flex max-h-[440px] w-[min(720px,calc(100vw-96px))] -translate-x-1/2 flex-col overflow-hidden rounded-xl shadow-2xl">
              <div class="flex items-center gap-3 border-b border-[var(--border)] px-4 py-3"><span class="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--primary-soft)] text-[var(--primary)]"><ListTree :size="16" /></span><div><h3 class="text-sm font-semibold">{{ t('designer.variableInspector') }}</h3><p class="muted mt-0.5 text-[10px]">{{ t('designer.variableInspectorHint') }}</p></div><button class="icon-button ml-auto" :aria-label="t('common.close')" @click="showVariableInspector = false"><X :size="15" /></button></div>
              <div class="border-b border-[var(--border)] p-3"><label class="flex h-8 items-center gap-2 rounded-md border border-[var(--border)] bg-[var(--input-bg)] px-2"><Search :size="13" class="muted" /><input v-model="variableSearch" class="min-w-0 flex-1 bg-transparent text-xs outline-none" :placeholder="t('designer.searchVariables')" autofocus /></label></div>
              <div class="min-h-0 flex-1 overflow-y-auto p-3"><div v-for="group in filteredVariableGroups" :key="group.nodeId" class="mb-3 overflow-hidden rounded-lg border border-[var(--border)] last:mb-0"><div class="flex items-center gap-2 bg-[var(--panel-subtle)] px-3 py-2"><span class="text-xs font-semibold">{{ group.label }}</span><code class="muted truncate text-[9px]">{{ group.nodeId }}</code><span class="muted ml-auto text-[9px]">{{ group.variables.length }}</span></div><button v-for="variable in group.variables" :key="variable.path" class="grid w-full grid-cols-[minmax(0,1fr)_88px_minmax(120px,0.8fr)_24px] items-center gap-2 border-t border-[var(--border)] px-3 py-2 text-left hover:bg-[var(--panel-subtle)]" :title="t('designer.copyVariable')" @click="copyVariableReference(variable.path)"><span class="min-w-0"><span class="block truncate text-[11px] font-medium">{{ variable.label }}</span><code class="muted mt-0.5 block truncate text-[9px]">{{ variableReference(variable.path) }}</code></span><span class="rounded bg-[var(--primary-soft)] px-1.5 py-1 text-center text-[9px] text-[var(--primary)]">{{ variable.type }}</span><pre class="max-h-14 overflow-hidden whitespace-pre-wrap break-all text-[9px] leading-4" :class="runtimeVariableValue(variable.path) === undefined ? 'text-[var(--muted)]' : 'text-[var(--text)]'">{{ formatRuntimeValue(runtimeVariableValue(variable.path)) }}</pre><Check v-if="copiedVariablePath === variable.path" :size="13" class="text-emerald-600" /><Copy v-else :size="12" class="muted" /></button></div><div v-if="!filteredVariableGroups.length" class="muted py-12 text-center text-xs">{{ t('designer.noVariableResults') }}</div></div>
            </div>
          </div>
        </section>

        <WorkflowCommentsPanel v-if="showComments" :comments="comments" :selected-id="selectedCommentId" :placement-active="commentMode" @close="closeComments" @select="selectComment" @place="toggleCommentMode" @submit="submitComment" @toggle-resolved="toggleCommentResolved" @delete="deleteCommentThread" />

	        <WorkflowNodeInspector v-else-if="selected" v-model:tab="inspectorTab" :node="selected" :node-type="selectedType" :running="running" :result="selectedResult" :name-error="nodeNameError" @update:label="updateSelectedNodeLabel" @update:description="selected.data.description = $event" @run="openRunDialog(selected.id)" @help="showHelp = true" @close="clearNodeSelection">
	          <template #settings>
	              <NodeConfigSection v-if="selectedType === 'note'" class="mt-5" :title="t('designer.nodeParameters')" :hint="t('designer.nodeParametersHint')" kind="parameters">
	                <label class="field-label">{{ t('designer.noteContent') }}<MarkdownComposer v-model="selected.data.description" class="mt-1.5" :placeholder="t('designer.noteEmpty')" :rows="6" /></label>
	                <NodeConfigSection class="mt-4 border-t border-[var(--border)] pt-4" :title="t('designer.noteColor')"><div class="flex gap-2"><button v-for="color in ['yellow','blue','green','rose']" :key="color" class="note-color-swatch" :class="[`swatch-${color}`, { active: selected.data.color === color }]" :aria-label="t(`designer.noteColors.${color}`)" @click="selected.data.color = color"><Check v-if="selected.data.color === color" :size="12" /></button></div></NodeConfigSection>
	              </NodeConfigSection>
	              <template v-else-if="selectedType === 'start'">
	                <NodeConfigSection class="mt-5" :title="t('designer.nodeParameters')" :hint="t('designer.nodeParametersHint')" kind="parameters">
                  <NodeConfigSection :title="t('designer.triggerMethods')" :hint="t('designer.triggerMethodHint')"><div class="grid grid-cols-2 gap-2" role="radiogroup"><ChoiceCard v-for="trigger in ['form','api','webhook','schedule']" :key="trigger" role="radio" :aria-checked="hasStartTrigger(trigger)" :selected="hasStartTrigger(trigger)" class="flex h-10 items-center gap-2 px-3 text-left text-xs" @click="toggleStartTrigger(trigger)"><span class="flex h-4 w-4 items-center justify-center rounded-full border" :class="hasStartTrigger(trigger) ? 'border-[var(--primary)]' : 'border-[var(--border)]'"><span v-if="hasStartTrigger(trigger)" class="h-2 w-2 rounded-full bg-[var(--primary)]"></span></span>{{ t(`designer.triggers.${trigger}`) }}</ChoiceCard></div></NodeConfigSection>
	                  <NodeConfigSection v-if="hasStartTrigger('schedule')" class="mt-4 border-t border-[var(--border)] pt-4" :title="t('designer.schedule')"><template #actions><label class="flex items-center gap-2 text-[10px]"><input v-model="selected.data.config.schedule.enabled" class="accent-[var(--primary)]" type="checkbox">{{ t('designer.enabled') }}</label></template><div class="space-y-3"><label class="field-label">Cron<InputText v-model="selected.data.config.schedule.cron" class="mt-1.5 font-mono" placeholder="0 9 * * *" /></label><label class="field-label">{{ t('settings.timezone') }}<InputText v-model="selected.data.config.schedule.timezone" class="mt-1.5" placeholder="Asia/Singapore" /></label><label class="field-label">{{ t('designer.scheduleInputs') }}<Textarea v-model="selected.data.config.schedule.inputs_json" class="mt-1.5 h-24 font-mono" placeholder='{"message":"Daily report"}' /></label></div></NodeConfigSection>
	                  <div v-if="hasStartTrigger('api') || hasStartTrigger('webhook')" class="mt-4 rounded-lg border border-[var(--border)] bg-[var(--panel-subtle)] p-3 text-[11px]"><div class="font-semibold">{{ t('designer.endpointAfterPublish') }}</div><code v-if="hasStartTrigger('api')" class="muted mt-2 block break-all">POST {{ origin }}/v1/apps/{{ workflow?.slug }}/run</code><code v-if="hasStartTrigger('webhook')" class="muted mt-2 block break-all">POST {{ origin }}/v1/apps/{{ workflow?.slug }}/webhook</code><code class="muted mt-2 block break-all">POST {{ origin }}/v1/apps/{{ workflow?.slug }}/files</code></div>
	                </NodeConfigSection>

	                <NodeConfigSection class="mt-5 border-t border-[var(--border)] pt-5" :title="t('designer.inputVariables')" :hint="t('designer.userInputsHint')" :count="selected.data.config.input_fields.length" kind="input" collapsible>
	                  <template #actions><button class="icon-button" :title="t('designer.addInputField')" :aria-label="t('designer.addInputField')" @click="addStartInput"><Plus :size="14" /></button></template>
	                  <div class="space-y-2">
	                  <div v-for="(field, index) in selected.data.config.input_fields" :key="index" class="overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--panel-subtle)]">
                    <div class="flex items-center gap-1 p-2 transition-colors hover:bg-[var(--primary-soft)]">
                      <button type="button" class="flex min-w-0 flex-1 items-center gap-2 rounded-md px-1 py-1 text-left" @click="toggleStartField(index)">
                        <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-[var(--primary-soft)] text-[10px] font-semibold text-[var(--primary)]">{{ field.type === 'files' ? '[]' : field.type === 'file' ? 'F' : field.type === 'number' ? '#' : field.type === 'month' ? 'M' : field.type === 'select' ? '⌄' : 'T' }}</span>
                        <span class="min-w-0 flex-1"><span class="block truncate font-mono text-xs font-semibold">{{ field.name || t('designer.unnamedField') }}</span><span class="muted mt-0.5 block truncate text-[10px]">{{ field.label || t('designer.fieldLabel') }} · {{ t(`designer.fieldTypes.${field.type}`) }}</span></span>
                        <span v-if="field.required" class="rounded bg-red-50 px-1.5 py-0.5 text-[9px] text-red-600 dark:bg-red-950/30">{{ t('designer.required') }}</span>
                        <ChevronRight :size="14" class="muted transition-transform" :class="expandedStartFieldIndex === Number(index) && 'rotate-90'" />
                      </button>
                      <button class="icon-button text-red-600" :aria-label="t('designer.removeInputField')" @click="removeStartInput(index)"><Trash2 :size="13" /></button>
                    </div>
                    <div v-if="expandedStartFieldIndex === Number(index)" class="border-t border-[var(--border)] bg-[var(--panel)] p-3">
	                      <label class="field-label">{{ t('designer.fieldLabel') }}<InputText v-model="field.label" class="mt-1.5" /></label>
	                      <div class="mt-3 grid grid-cols-[minmax(0,1fr)_125px] gap-2"><label class="field-label">{{ t('designer.variableName') }}<InputText v-model="field.name" class="mt-1.5 font-mono" placeholder="field_name" /></label><label class="field-label">{{ t('designer.fieldType') }}<Select v-model="field.type" class="mt-1.5"><option v-for="kind in ['text','textarea','number','month','select','file','files']" :key="kind" :value="kind">{{ t(`designer.fieldTypes.${kind}`) }}</option></Select></label></div>
	                      <template v-if="['text','textarea','select'].includes(field.type)">
	                        <label class="field-label mt-3">{{ t('designer.placeholder') }}<InputText v-model="field.placeholder" class="mt-1.5" /></label>
	                        <label class="field-label mt-3">{{ t('designer.defaultValue') }}<InputText v-model="field.default_value" class="mt-1.5" /></label>
	                        <label v-if="field.type !== 'select'" class="field-label mt-3">{{ t('designer.maxLength') }}<InputText v-model.number="field.max_length" type="number" min="1" max="100000" class="mt-1.5" /></label>
	                      </template>
	                      <template v-if="field.type === 'number'"><div class="mt-3 grid grid-cols-3 gap-2"><label class="field-label">{{ t('designer.defaultValue') }}<InputText v-model.number="field.default_value" type="number" class="mt-1.5" /></label><label class="field-label">{{ t('designer.minimum') }}<InputText v-model.number="field.min" type="number" class="mt-1.5" /></label><label class="field-label">{{ t('designer.maximum') }}<InputText v-model.number="field.max" type="number" class="mt-1.5" /></label></div></template>
	                      <label v-if="field.type === 'month'" class="field-label mt-3">{{ t('designer.defaultValue') }}<InputText v-model="field.default_value" type="month" class="mt-1.5" /></label>
	                      <div v-if="field.type === 'select'" class="mt-3"><div class="flex items-center"><h4 class="text-[11px] font-semibold">{{ t('designer.options') }}</h4><button class="icon-button ml-auto" :aria-label="t('designer.addOption')" @click="addStartFieldOption(field)"><Plus :size="13" /></button></div><div class="mt-2 space-y-2"><div v-for="(_, optionIndex) in field.options" :key="optionIndex" class="flex gap-2"><InputText v-model="field.options[optionIndex]" /><button class="icon-button text-red-600" :aria-label="t('designer.removeOption')" @click="removeStartFieldOption(field, optionIndex)"><X :size="13" /></button></div><button v-if="!field.options.length" class="w-full rounded-md border border-dashed border-[var(--border)] py-3 text-[11px] text-[var(--muted)] hover:border-[var(--primary)] hover:text-[var(--primary)]" @click="addStartFieldOption(field)"><Plus class="mr-1 inline" :size="12" />{{ t('designer.addOption') }}</button></div></div>
                      <label class="mt-3 flex items-center gap-2 text-xs"><input v-model="field.required" type="checkbox">{{ t('designer.required') }}</label>
                    </div>
                  </div>
	                  </div>
	                </NodeConfigSection>
	              </template>
	              <template v-else-if="selectedType === 'end'">
	                <NodeConfigSection class="mt-5" :title="t('designer.outputFields')" :hint="t('designer.outputFieldsHint')" :count="selected.data.config.outputs.length" kind="output">
	                  <template #actions><button class="icon-button" :title="t('designer.addOutputField')" :aria-label="t('designer.addOutputField')" @click="addEndOutput"><Plus :size="14" /></button></template>
	                  <div class="space-y-3">
	                  <div v-for="(output, index) in selected.data.config.outputs" :key="index" class="rounded-lg border border-[var(--border)] bg-[var(--panel-subtle)] p-3">
	                    <div class="grid grid-cols-[minmax(0,1fr)_105px_30px] gap-2">
	                      <InputText v-model="output.name" class="font-mono" :placeholder="t('designer.outputName')" />
	                      <Select v-model="output.type" class="!w-28">
                        <option v-for="kind in ['String','Number','Boolean','Object','Array','File','Any']" :key="kind" :value="kind">{{ kind }}</option>
                      </Select>
	                      <button class="icon-button !h-9 !w-9 text-red-600" :aria-label="t('designer.removeOutputField')" @click="removeEndOutput(index)"><X :size="14" /></button>
                    </div>
                    <label class="field-label mt-3">{{ t('designer.outputValue') }}<VariableField v-model="output.value" class="mt-1.5 font-mono" :groups="variableGroups" :placeholder="t('designer.selectUpstreamOutput')" /></label>
                  </div>
                  <button v-if="!selected.data.config.outputs.length" class="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-[var(--border)] py-5 text-xs text-[var(--muted)] hover:border-[var(--primary)] hover:text-[var(--primary)]" @click="addEndOutput"><Plus :size="14" />{{ t('designer.addOutputField') }}</button>
	                  </div>
	                </NodeConfigSection>
	              </template>
              <template v-else>
                <LlmConfigPanel v-if="selectedType === 'llm'" :config="selected.data.config" :providers="modelProviders" :variable-groups="variableGroups" :buffers="configBuffers" :errors="configFieldErrors" @structured="updateStructuredField($event.field, $event.buffer as any)" @editing="configEditing = $event" />
                <ImageGenerationConfigPanel v-else-if="selectedType === 'image'" :config="selected.data.config" :providers="modelProviders" :variable-groups="variableGroups" />
                <AgentConfigPanel v-else-if="selectedType === 'agent'" :config="selected.data.config" :providers="modelProviders" :scripts="scripts" :variable-groups="variableGroups" @provider-change="selectModelProvider" />
                <ClassifierConfigPanel v-else-if="selectedType === 'classifier'" :config="selected.data.config" :variable-groups="variableGroups" @add="addClassifierCategory" @remove="removeClassifierCategory" @connect="openPaletteForSource(selected.id, $event)" @update-keywords="updateClassifierKeywords" />
                <CodeConfigPanel v-else-if="selectedType === 'code'" :key="selected.id" :config="selected.data.config" :variable-groups="variableGroups" @editing="configEditing = $event" />
                <ScriptConfigPanel v-else-if="selectedType === 'script'" :config="selected.data.config" :scripts="scripts" :workspace-id="workspaceId" :variable-groups="variableGroups" />
                <HttpConfigPanel v-else-if="selectedType === 'http'" :config="selected.data.config" :variable-groups="variableGroups" :buffers="configBuffers" :errors="configFieldErrors" @structured="updateStructuredField" />
                <TemplateConfigPanel v-else-if="selectedType === 'template'" :config="selected.data.config" :variable-groups="variableGroups" />
                <DocumentConfigPanel v-else-if="selectedType === 'document'" :key="selected.id" :config="selected.data.config" :variable-groups="variableGroups" />
                <VariableAssignConfigPanel v-else-if="selectedType === 'variable'" :key="selected.id" :config="selected.data.config" :variable-groups="variableGroups" />
	                <NodeConfigSection v-else-if="selectedType === 'json'" class="mt-5" :title="t('designer.nodeParameters')" :hint="t('designer.nodeParametersHint')" kind="parameters"><JsonEditorField v-model="configBuffers.jsonValue" :label="t('designer.jsonValue')" :error="configFieldErrors.jsonValue" :groups="variableGroups" height-class="h-52" @input="updateStructuredField('value', 'jsonValue')" /></NodeConfigSection>
                <AggregateConfigPanel v-else-if="selectedType === 'aggregate'" :config="selected.data.config" :variable-groups="variableGroups" />
                <ParameterExtractorConfigPanel v-else-if="selectedType === 'extract'" :key="selected.id" :config="selected.data.config" :providers="modelProviders" :variable-groups="variableGroups" />
                <ListOperatorConfigPanel v-else-if="selectedType === 'list'" :key="selected.id" :config="selected.data.config" :variable-groups="variableGroups" />
                <ConditionConfigPanel v-else-if="selectedType === 'condition'" :config="selected.data.config" :variable-groups="variableGroups" @add="addConditionClause" @remove="removeConditionClause" @connect="openPaletteForSource(selected.id, $event)" />
                <HumanConfigPanel v-else-if="selectedType === 'human'" :config="selected.data.config" :variable-groups="variableGroups" @remove="removeHumanAction" @connect="openPaletteForSource(selected.id, $event)" />
                <IterationConfigPanel v-else-if="selectedType === 'iteration'" :config="selected.data.config" :variable-groups="variableGroups" />
                <LoopConfigPanel v-else-if="selectedType === 'loop'" :config="selected.data.config" :variable-groups="variableGroups" />
                <WaitConfigPanel v-else-if="selectedType === 'wait'" :config="selected.data.config" />
                <SubworkflowConfigPanel v-else-if="selectedType === 'subworkflow'" :config="selected.data.config" :workflows="subworkflows" :variable-groups="variableGroups" @select="selectSubworkflow" />
	                <NodeConfigSection v-else-if="selectedType === 'delay'" class="mt-5" :title="t('designer.nodeParameters')" :hint="t('designer.nodeParametersHint')" kind="parameters"><label class="field-label">{{ t('designer.delaySeconds') }}<InputText v-model.number="selected.data.config.seconds" class="mt-1.5" type="number" min="1" max="86400" /></label></NodeConfigSection>
              </template>
            <NodeOutputPanel v-if="!['note','start','end'].includes(selectedType)" :key="`${selected.id}:output`" :node="selected" :copied-path="copiedVariablePath" @copy="copyVariableReference" />
            <NextStepPanel v-if="!['end','note','condition','classifier','human'].includes(selectedType)" :key="`${selected.id}:next`" :nodes="nextNodes" @add="openPaletteForSource(selected.id)" @parallel="openPaletteForSource(selected.id)" />
            <ExecutionPolicyPanel v-if="executionPolicyNodeTypes.has(selectedType)" :key="`${selected.id}:policy`" :config="selected.data.config" @connect-error="openPaletteForSource(selected.id, 'error')" />
            <NodeConfigSection v-if="!['note','start','end'].includes(selectedType)" :key="`${selected.id}:advanced`" class="mt-5 border-t border-[var(--border)] pt-5" :title="t('designer.advancedConfig')" :hint="t('designer.advancedConfigHint')" kind="advanced" collapsible :default-expanded="false" @toggle="syncConfigEditor">
              <template #icon><Braces :size="15" /></template>
              <JsonEditorField v-model="configText" :label="t('workflow.configuration')" :error="configError" :groups="variableGroups" height-class="h-48" @focus="configEditing = true" @blur="configEditing = false; syncConfigEditor()" @input="updateSelectedConfig" />
            </NodeConfigSection>
          </template>
        </WorkflowNodeInspector>
      </div>
      <div v-else-if="activeSection === 'api'" class="h-full overflow-y-auto bg-[var(--app-bg)] p-6"><div class="mx-auto max-w-5xl"><AlertBanner class="mb-4 !mt-0" :message="publishSuccess" tone="success" /><div class="space-y-4"><WorkflowSettingsPanel v-model="workflowSlugDraft" :saved-slug="workflow?.slug || ''" :origin="origin" :published="Boolean(workflow?.published_version_id)" :saving="saving" :error="saveError" @edit="saveError = ''; saveConflict = false" @save="saveWorkflowSlug" /><PublishPopover :open="true" :workflow="workflow" :versions="versions" :publishing="publishing" @publish="publish" @history="openVersionHistoryFromPublish" @api="openApiFromPublish" @run="openPublishedApp" /></div></div></div>
      <WorkflowRunLogsPanel v-else-if="activeSection === 'logs'" :runs="runs" :detail-open="replayMode" :selected-run-id="selectedRun?.id || ''" @refresh="loadRuns" @replay="replayRun" />
      <WorkflowMonitoringPanel v-else :runs="runs" />
    </div>
    <ModalShell v-model="showApiAccess" :title="t('designer.apiTitle')" :description="t('designer.apiHint')" max-width="max-w-4xl"><WorkflowApiPanel compact :origin="origin" :slug="workflow?.slug" :triggers="startNode?.data?.config?.triggers" :input-fields="startFields" /></ModalShell>
    <ModalShell v-model="showChangeHistory" :title="t('designer.changeHistory')" :description="t('designer.localHistoryHint')" body-class="max-h-[430px] p-2"><button v-for="entry in localHistoryEntries" :key="entry.index" class="flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left hover:bg-[var(--panel-subtle)]" :class="{ 'bg-[var(--primary-soft)]': entry.index === historyIndex }" @click="restoreLocalSnapshot(entry.index)"><span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full" :class="entry.index === historyIndex ? 'bg-[var(--primary)] text-white' : 'bg-[var(--panel-subtle)] text-[var(--muted)]'"><History :size="14" /></span><span class="min-w-0 flex-1"><span class="block text-xs font-semibold">{{ entry.index === historyIndex ? t('designer.currentState') : t('designer.changeSnapshot', { index: entry.index + 1 }) }}</span><span class="muted mt-1 block text-[10px]">{{ t('designer.historyEntry', { nodes: entry.state.nodes.length, edges: entry.state.edges.length }) }}</span></span><span class="muted text-[10px]">{{ entry.time?.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }}</span></button></ModalShell>
    <ModalShell v-model="showHistory" :title="t('designer.history')" :description="t('designer.versionHistoryHint')" max-width="max-w-2xl" body-class="max-h-[520px] space-y-2 p-4"><div v-for="item in versions" :key="item.id" class="rounded-lg border border-[var(--border)] p-4"><div class="flex items-start gap-3"><span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--primary-soft)] text-xs font-bold text-[var(--primary)]">v{{ item.version }}</span><div class="min-w-0 flex-1"><div class="flex items-center gap-2 text-sm font-semibold">{{ item.change_note }}<span v-if="item.id === workflow?.published_version_id" class="rounded bg-emerald-50 px-1.5 py-0.5 text-[9px] text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">{{ t('designer.currentPublished') }}</span></div><div class="muted mt-1 text-[10px]">{{ new Date(item.created_at).toLocaleString() }}</div><div class="mt-2 flex flex-wrap gap-1.5 text-[10px]"><span class="rounded bg-emerald-50 px-2 py-1 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">+{{ versionDiff(item).added }} {{ t('designer.nodesShort') }}</span><span class="rounded bg-red-50 px-2 py-1 text-red-700 dark:bg-red-950/30 dark:text-red-300">-{{ versionDiff(item).removed }} {{ t('designer.nodesShort') }}</span><span class="rounded bg-amber-50 px-2 py-1 text-amber-700 dark:bg-amber-950/30 dark:text-amber-300">~{{ versionDiff(item).changed }} {{ t('designer.nodesShort') }}</span><span class="rounded bg-[var(--panel-subtle)] px-2 py-1 text-[var(--muted)]">{{ versionDiff(item).versionEdges }} → {{ versionDiff(item).currentEdges }} {{ t('designer.edgesShort') }}</span></div></div><Button variant="secondary" @click="pendingRestoreVersion = item">{{ t('designer.restoreDraft') }}</Button></div></div><div v-if="!versions.length" class="muted py-12 text-center text-sm">{{ t('common.empty') }}</div></ModalShell>
    <ModalShell :model-value="Boolean(pendingRestoreVersion)" :title="t('designer.restoreConfirmTitle', { version: pendingRestoreVersion?.version })" max-width="max-w-md" @update:model-value="pendingRestoreVersion = null"><div class="flex h-10 w-10 items-center justify-center rounded-full bg-amber-50 text-amber-600 dark:bg-amber-950/40"><AlertTriangle :size="20" /></div><p class="muted mt-4 text-sm leading-6">{{ t('designer.restoreConfirmText') }}</p><template #footer><Button variant="secondary" :disabled="restoringVersion" @click="pendingRestoreVersion = null">{{ t('common.cancel') }}</Button><Button :loading="restoringVersion" @click="restorePublishedVersion">{{ t('designer.restoreDraft') }}</Button></template></ModalShell>
    <RunDebugPanel :open="showRunDialog" :title="replayMode ? `${t(`designer.triggerShort.${selectedRun?.triggered_by || 'studio'}`)} (${selectedRun ? new Date(selectedRun.created_at).toLocaleTimeString() : ''})` : runTargetNodeId ? t('designer.runNodeTitle', { name: runTargetLabel }) : t('workflow.run')" :fields="startFields" :inputs="runInputs" :uploading-field="uploadingField" :result="result" :error="runError" :running="running" :canceling="cancelingRun" :retrying="retryingRun" :node-run="Boolean(runTargetNodeId)" :readonly="replayMode" :node-labels="runNodeLabels" @close="replayMode ? exitReplayMode() : showRunDialog = false" @run="run" @cancel="cancelRun" @retry="retryRun" @file-change="uploadRunFile" @focus-node="focusTraceNode" />
    <ModalShell v-model="showApprovals" :title="t('designer.pendingApprovals')" :description="t('designer.pendingApprovalsHint')" max-width="max-w-3xl">
      <div class="grid min-h-96 grid-cols-[220px_minmax(0,1fr)] overflow-hidden rounded-lg border border-[var(--border)]">
        <aside class="border-r border-[var(--border)] bg-[var(--panel-subtle)] p-2"><button v-for="item in approvals" :key="item.id" class="mb-1 w-full rounded-md px-3 py-2.5 text-left" :class="selectedApproval?.id === item.id ? 'bg-[var(--primary-soft)] text-[var(--primary)]' : 'hover:bg-[var(--panel)]'" @click="selectedApproval = item; approvalComment = ''"><div class="truncate text-xs font-semibold">{{ item.request?.title || item.node_id }}</div><div class="mt-1 flex items-center gap-2 text-[9px]"><span :class="item.status === 'pending' ? 'text-amber-600' : 'text-emerald-600'">{{ t(`designer.approvalStatus.${item.status}`) }}</span><span class="muted">{{ new Date(item.created_at).toLocaleString() }}</span></div></button><div v-if="!approvals.length" class="muted py-16 text-center text-xs">{{ t('designer.noApprovals') }}</div></aside>
        <section v-if="selectedApproval" class="p-5"><div class="flex items-start gap-3"><span class="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-50 text-amber-600 dark:bg-amber-950/40"><UserCheck :size="18" /></span><div><h3 class="text-sm font-semibold">{{ selectedApproval.request?.title }}</h3><p class="muted mt-1 text-[10px]">{{ t('designer.approvalExpires', { time: selectedApproval.expires_at ? new Date(selectedApproval.expires_at).toLocaleString() : '-' }) }}</p></div></div><pre class="mt-5 max-h-56 overflow-auto whitespace-pre-wrap rounded-lg border border-[var(--border)] bg-[var(--panel-subtle)] p-4 text-xs leading-6">{{ selectedApproval.request?.form_content }}</pre><label v-if="selectedApproval.status === 'pending'" class="field-label mt-5">{{ t('designer.approvalComment') }}<Textarea v-model="approvalComment" class="mt-1.5 h-24" :placeholder="t('designer.approvalCommentPlaceholder')" /></label><div v-if="selectedApproval.status === 'pending'" class="mt-5 flex flex-wrap justify-end gap-2"><Button v-for="action in selectedApproval.request?.actions || []" :key="action.id" :variant="action.style === 'primary' ? 'primary' : action.style === 'danger' ? 'danger' : 'secondary'" :loading="respondingApproval" @click="respondApproval(action)">{{ action.label }}</Button></div><div v-else class="mt-5 rounded-lg bg-[var(--panel-subtle)] p-3 text-xs"><span class="font-semibold">{{ t('designer.approvalResponse') }}</span><pre class="mt-2 whitespace-pre-wrap">{{ JSON.stringify(selectedApproval.response, null, 2) }}</pre></div><AlertBanner class="mt-4" :message="runError" tone="error" /></section>
        <section v-else class="muted flex items-center justify-center text-xs">{{ t('designer.selectApproval') }}</section>
      </div>
    </ModalShell>
    <ModalShell v-model="showHelp" :title="t('designer.help')"><p class="muted text-sm leading-6">{{ t('designer.helpText') }}</p></ModalShell>
    <DesignerCommandPalette :open="showCommandPalette" :nodes="nodes" :add-items="commandAddItems" :actions="commandActions" @close="showCommandPalette = false" @focus="focusCommandNode" @add="addCommandNode" @action="executeCommand" />
  </div>
</template>

<style>
.workflow-canvas .vue-flow__minimap { right: 14px !important; bottom: 58px !important; width: 170px !important; height: 105px !important; }
.workflow-canvas .vue-flow__edges { z-index: 6 !important; }
.workflow-canvas .vue-flow__nodes { z-index: 3 !important; }
.workflow-canvas .vue-flow__edge-labels { z-index: 7 !important; }
.workflow-canvas.replay-mode .vue-flow__node { pointer-events: none; }
.workflow-canvas.annotation-mode .vue-flow__pane { cursor: crosshair; }
.workflow-canvas.middle-panning .vue-flow__pane, .workflow-canvas.middle-panning .vue-flow__node { cursor: grabbing !important; }
.icon-button { display: inline-flex; width: 30px; height: 30px; flex: none; align-items: center; justify-content: center; border-radius: 7px; color: var(--muted); }.icon-button:hover { background: var(--panel-subtle); color: var(--text); }.workflow-canvas { background: var(--app-bg); }.workflow-canvas .vue-flow__node { border: 0; background: transparent; padding: 0; box-shadow: none; }.workflow-canvas .vue-flow__handle { width: 9px; height: 9px; border: 2px solid var(--panel); background: var(--primary); }.workflow-canvas .vue-flow__handle.quick-add-handle { width: 20px; height: 20px; border: 0; background: transparent; }.canvas-mode-button { display: flex; width: 36px; height: 36px; align-items: center; justify-content: center; color: var(--muted); }.canvas-mode-button:hover { background: var(--panel-subtle); color: var(--text); }.canvas-mode-button.active { background: var(--primary-soft); color: var(--primary); }.canvas-action-row { display: flex; width: 100%; height: 32px; align-items: center; gap: 8px; border-radius: 6px; padding: 0 9px; font-size: 12px; }.canvas-action-row:hover:not(:disabled) { background: var(--panel-subtle); }.canvas-action-row:disabled { cursor: not-allowed; opacity: .4; }.inspector-tab { height: 40px; border-bottom: 2px solid transparent; padding: 0 12px; color: var(--muted); font-size: 12px; }.inspector-tab.active { border-color: var(--primary); color: var(--primary); font-weight: 600; }.field-label { display: block; color: var(--text); font-size: 12px; font-weight: 600; }.vue-flow__minimap { overflow: hidden; border: 1px solid var(--border); border-radius: 8px; background: var(--panel); }
.designer-header-actions .icon-button { width: 36px; height: 36px; }.designer-header-actions .header-env-button { height: 36px; }.designer-header-actions button { transition: background-color .15s ease, border-color .15s ease, color .15s ease, filter .15s ease; }.designer-header-actions button.surface:hover:not(:disabled) { border-color: color-mix(in srgb, var(--primary), var(--border) 55%); background: var(--primary-soft); color: var(--primary); box-shadow: none; transform: none; }
.resource-empty { border: 1px dashed var(--border); border-radius: 7px; background: var(--panel-subtle); padding: 10px; color: var(--muted); font-size: 11px; }.field-error { margin-top: 6px; color: #d92d20; font-size: 11px; }
.canvas-history-button { display: flex; width: 34px; height: 34px; align-items: center; justify-content: center; color: var(--muted); }.canvas-history-button:hover:not(:disabled) { background: var(--panel-subtle); color: var(--primary); }.canvas-history-button:disabled { cursor: not-allowed; opacity: .35; }
.run-detail-heading { color: var(--muted); font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }.run-detail-code { margin-top: 8px; max-height: 260px; overflow: auto; white-space: pre-wrap; border: 1px solid var(--border); border-radius: 8px; background: var(--panel-subtle); padding: 12px; font-size: 11px; line-height: 1.6; }
.note-color-swatch { display: flex; width: 30px; height: 30px; align-items: center; justify-content: center; border: 2px solid transparent; border-radius: 7px; color: #344054; }.note-color-swatch.active { border-color: var(--primary); box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary), transparent 82%); }.swatch-yellow { background: #fde68a; }.swatch-blue { background: #bfdbfe; }.swatch-green { background: #bbf7d0; }.swatch-rose { background: #fecdd3; }
@media (max-width: 1023px) {
  .designer-main-header.inspector-open, .designer-canvas-host.inspector-open { display: none; }
  .designer-main-header { padding-inline: 8px; }
  .designer-header-actions { min-width: 0; flex: 1; justify-content: flex-end; overflow-x: auto; scrollbar-width: none; }
  .designer-header-actions::-webkit-scrollbar { display: none; }
}
</style>
