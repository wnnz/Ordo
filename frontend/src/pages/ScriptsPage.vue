<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { Braces, FileCode2, FilePlus2, Play, Plus, RotateCcw, Square, Trash2, Upload } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import api from '@/api/client'
import { consumeRunEvents } from '@/api/runEvents'
import AppShell from '@/components/AppShell.vue'
import ScriptSchemaEditor from '@/components/scripts/ScriptSchemaEditor.vue'
import WorkflowOutputRenderer from '@/components/WorkflowOutputRenderer.vue'
import AlertBanner from '@/components/ui/AlertBanner.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import ModalShell from '@/components/ui/ModalShell.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import SearchInput from '@/components/ui/SearchInput.vue'
import ActionCard from '@/volt/ActionCard.vue'
import Button from '@/volt/Button.vue'
import IconButton from '@/volt/IconButton.vue'
import InputText from '@/volt/InputText.vue'
import Select from '@/volt/Select.vue'
import Textarea from '@/volt/Textarea.vue'
import ToggleSwitch from '@/volt/ToggleSwitch.vue'
import { useWorkspacesStore } from '@/stores/workspaces'
import { scriptSchemaKind } from '@/utils/scriptSchema'

const CodeEditor = defineAsyncComponent(() => import('@/components/CodeEditor.vue'))
type JsonSchema = Record<string, any>
type ScriptTemplate = { id: string; name: string; description: string; category: string; source_files: Record<string, string>; entrypoint: string; input_schema: JsonSchema; output_schema: JsonSchema; sample_inputs: Record<string, any>; network_enabled?: boolean }
type ScriptVersion = { version: number; entrypoint: string; change_note: string; created_at: string; source_type: string; network_enabled: boolean }
type EditorTab = 'code' | 'inputs' | 'outputs' | 'test' | 'versions'

const { t } = useI18n()
const workspaces = useWorkspacesStore()
const items = ref<any[]>([])
const templates = ref<ScriptTemplate[]>([])
const showEditor = ref(false)
const saving = ref(false)
const testing = ref(false)
const error = ref('')
const search = ref('')
const selected = ref<any>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const activeTab = ref<EditorTab>('code')
const activeFile = ref('main.py')
const newFileName = ref('')
const testValues = ref<Record<string, any>>({})
const testLogs = ref<string[]>([])
const testResult = ref<any>(null)
const testTaskId = ref('')
const uploadingTestField = ref('')
const versions = ref<ScriptVersion[]>([])
const versionTotal = ref(0)
const versionOffset = ref(0)
const versionDiff = ref('')
const form = ref({
  name: '', description: '', tagsText: '', entrypoint: 'main:main', change_note: '',
  network_enabled: false,
  source_files: { 'main.py': 'def main(inputs, context):\n    return {"result": inputs}\n' } as Record<string, string>,
  input_schema: { type: 'object', properties: {} } as JsonSchema,
  output_schema: { type: 'object', properties: { result: {} }, required: ['result'] } as JsonSchema,
})

const filtered = computed(() => items.value.filter(item => item.name.toLowerCase().includes(search.value.toLowerCase()) || item.tags?.some((tag: string) => tag.toLowerCase().includes(search.value.toLowerCase()))))
const files = computed(() => Object.keys(form.value.source_files).sort())
const activeSource = computed({
  get: () => form.value.source_files[activeFile.value] || '',
  set: value => { form.value.source_files[activeFile.value] = value },
})
const inputProperties = computed(() => form.value.input_schema?.properties || {})
const editorTabs = computed(() => [
  { id: 'code', label: t('scripts.code') },
  { id: 'inputs', label: t('scripts.inputs'), count: Object.keys(inputProperties.value).length },
  { id: 'outputs', label: t('scripts.outputs'), count: Object.keys(form.value.output_schema?.properties || {}).length },
  { id: 'test', label: t('scripts.test') },
  ...(selected.value ? [{ id: 'versions', label: t('scripts.versions'), count: versionTotal.value }] : []),
] as Array<{ id: EditorTab; label: string; count?: number }>)

function clone<T>(value: T): T { return JSON.parse(JSON.stringify(value)) as T }
async function load() { if (workspaces.activeId) items.value = (await api.get(`/workspaces/${workspaces.activeId}/scripts`)).data }
async function loadTemplates() { if (workspaces.activeId) templates.value = (await api.get(`/workspaces/${workspaces.activeId}/scripts/templates`)).data }
function applyTemplate(template: ScriptTemplate, useMetadata = false) {
  form.value.source_files = clone(template.source_files)
  form.value.entrypoint = template.entrypoint
  form.value.input_schema = clone(template.input_schema)
  form.value.output_schema = clone(template.output_schema)
  form.value.network_enabled = Boolean(template.network_enabled)
  activeFile.value = Object.keys(template.source_files)[0] || 'main.py'
  testValues.value = clone(template.sample_inputs)
  if (useMetadata && !selected.value) {
    form.value.name = template.name
    form.value.description = template.description
  }
  activeTab.value = 'code'
}
function resetEditor() {
  const template = templates.value.find(item => item.id === 'blank') || templates.value[0]
  form.value = { name: '', description: '', tagsText: '', entrypoint: 'main:main', change_note: '', network_enabled: false, source_files: { 'main.py': '' }, input_schema: { type: 'object', properties: {} }, output_schema: { type: 'object', properties: {} } }
  if (template) applyTemplate(template)
  activeFile.value = Object.keys(form.value.source_files)[0] || 'main.py'
  activeTab.value = 'code'; testResult.value = null; testLogs.value = []; versionDiff.value = ''; testTaskId.value = ''
}
function newScript() { selected.value = null; resetEditor(); showEditor.value = true }
async function loadVersions(offset = 0) {
  if (!selected.value) return
  const { data } = await api.get(`/workspaces/${workspaces.activeId}/scripts/${selected.value.id}/versions`, { params: { limit: 20, offset } })
  versions.value = data.items; versionTotal.value = data.total; versionOffset.value = data.offset
}
async function loadVersion(versionNumber: number) {
  const { data } = await api.get(`/workspaces/${workspaces.activeId}/scripts/${selected.value.id}/versions/${versionNumber}`)
  form.value.source_files = Object.keys(data.source_files || {}).length ? data.source_files : { 'main.py': data.source_code }
  form.value.entrypoint = data.entrypoint
  form.value.input_schema = data.input_schema
  form.value.output_schema = data.output_schema
  form.value.network_enabled = Boolean(data.network_enabled)
  activeFile.value = Object.keys(form.value.source_files)[0]
}
async function edit(item: any) {
  selected.value = item; resetEditor(); selected.value = item
  form.value.name = item.name; form.value.description = item.description || ''; form.value.tagsText = item.tags?.join(', ') || ''
  await Promise.all([loadVersion(item.latest_version), loadVersions()])
  showEditor.value = true
}
function entrySource() {
  const module = form.value.entrypoint.includes(':') ? form.value.entrypoint.split(':', 1)[0].replaceAll('.', '/') + '.py' : 'main.py'
  return form.value.source_files[module] || form.value.source_files[module.replace(/\.py$/, '/__init__.py')] || activeSource.value
}
async function save() {
  saving.value = true; error.value = ''
  const payload = {
    name: form.value.name, description: form.value.description,
    tags: form.value.tagsText.split(',').map(value => value.trim()).filter(Boolean),
    source_code: entrySource(), source_files: form.value.source_files, entrypoint: form.value.entrypoint,
    input_schema: form.value.input_schema, output_schema: form.value.output_schema,
    network_enabled: form.value.network_enabled,
    change_note: form.value.change_note || (selected.value ? 'Updated in script editor' : 'Initial version'),
  }
  try {
    if (selected.value) await api.put(`/workspaces/${workspaces.activeId}/scripts/${selected.value.id}`, { ...payload, expected_version: selected.value.latest_version })
    else await api.post(`/workspaces/${workspaces.activeId}/scripts`, payload)
    showEditor.value = false; await load()
  } catch (cause: any) { error.value = cause.response?.data?.detail || String(cause) }
  finally { saving.value = false }
}
function addFile() {
  const name = newFileName.value.trim().replaceAll('\\', '/')
  if (!/^(?!\/)(?!.*\.\.)(?:[A-Za-z_][\w-]*\/)*[A-Za-z_][\w-]*\.py$/.test(name) || form.value.source_files[name] !== undefined) return
  form.value.source_files[name] = ''; activeFile.value = name; newFileName.value = ''
}
function removeFile(name: string) {
  if (files.value.length <= 1) return
  delete form.value.source_files[name]
  if (activeFile.value === name) activeFile.value = files.value[0]
}
async function upload(event: Event) {
  const input = event.target as HTMLInputElement; const file = input.files?.[0]; if (!file) return
  const name = file.name.replace(/\.(py|zip)$/i, ''); const data = new FormData()
  data.append('file', file); data.append('name', name); data.append('entrypoint', file.name.toLowerCase().endsWith('.zip') ? 'main:main' : 'main')
  saving.value = true; error.value = ''
  try { const response = await api.post(`/workspaces/${workspaces.activeId}/scripts/upload`, data); await load(); await edit(response.data) }
  catch (cause: any) { error.value = cause.response?.data?.detail || String(cause) }
  finally { saving.value = false; input.value = '' }
}
function fieldDefault(schema: JsonSchema) {
  if (schema.default !== undefined) return clone(schema.default)
  if (scriptSchemaKind(schema) === 'file') return null
  if (scriptSchemaKind(schema) === 'files') return []
  if (schema.type === 'boolean') return false
  if (schema.type === 'number' || schema.type === 'integer') return 0
  if (schema.type === 'array') return []
  if (schema.type === 'object') return {}
  return ''
}
async function uploadTestFiles(name: string, schema: JsonSchema, event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  if (!files.length) return
  uploadingTestField.value = name
  error.value = ''
  try {
    const uploaded = []
    for (const file of files) {
      const data = new FormData()
      data.append('file', file)
      uploaded.push((await api.post(`/workspaces/${workspaces.activeId}/scripts/test-files`, data)).data)
    }
    testValues.value[name] = scriptSchemaKind(schema) === 'files' ? uploaded : uploaded[0]
  } catch (cause: any) { error.value = cause.response?.data?.detail || String(cause) }
  finally { uploadingTestField.value = ''; input.value = '' }
}
function testFileNames(value: any) {
  const files = Array.isArray(value) ? value : value ? [value] : []
  return files.map(item => String(item?.filename || '')).filter(Boolean).join(', ')
}
function clearTestFiles(name: string) { testValues.value[name] = scriptSchemaKind(inputProperties.value[name]) === 'files' ? [] : null }
watch(inputProperties, properties => {
  const next: Record<string, any> = {}
  for (const [name, schema] of Object.entries(properties) as Array<[string, JsonSchema]>) next[name] = testValues.value[name] ?? fieldDefault(schema)
  testValues.value = next
}, { deep: true })
function setStructuredTestValue(name: string, text: string) { try { testValues.value[name] = JSON.parse(text) } catch { /* keep the last valid value */ } }
function setScalarTestValue(name: string, schema: JsonSchema, value: string) {
  if (schema.type === 'number' || schema.type === 'integer') {
    testValues.value[name] = value === '' ? null : Number(value)
    return
  }
  testValues.value[name] = value
}
async function test() {
  testing.value = true; error.value = ''; testResult.value = null; testLogs.value = []
  try {
    const payload = { source_code: entrySource(), source_files: form.value.source_files, entrypoint: form.value.entrypoint, input_schema: form.value.input_schema, output_schema: form.value.output_schema, inputs: testValues.value, timeout_seconds: 30, memory_mb: 256, network_enabled: form.value.network_enabled }
    const path = selected.value ? `/workspaces/${workspaces.activeId}/scripts/${selected.value.id}/test` : `/workspaces/${workspaces.activeId}/scripts/test`
    const { data } = await api.post(path, payload)
    testTaskId.value = data.task_id
    await consumeRunEvents(`/api/v1/workspaces/${workspaces.activeId}/scripts/tests/${data.task_id}/events`, event => {
      if (event.type === 'log') testLogs.value.push(String(event.message || ''))
      if (event.type === 'result') { testResult.value = event; testing.value = false }
      if (event.type === 'status' && event.status === 'cancelled') testing.value = false
    })
  } catch (cause: any) { error.value = cause.response?.data?.detail || String(cause); testing.value = false }
}
async function cancelTest() { if (testTaskId.value) await api.post(`/workspaces/${workspaces.activeId}/scripts/tests/${testTaskId.value}/cancel`) }
async function loadDiff(version: number) { const { data } = await api.get(`/workspaces/${workspaces.activeId}/scripts/${selected.value.id}/diff`, { params: { from_version: version, to_version: selected.value.latest_version } }); versionDiff.value = data.diff || t('scripts.noChanges') }
async function restoreVersion(version: number) { await api.post(`/workspaces/${workspaces.activeId}/scripts/${selected.value.id}/restore`, { source_version: version, expected_version: selected.value.latest_version, change_note: `Restored version ${version}` }); await load(); selected.value = items.value.find(item => item.id === selected.value.id); await Promise.all([loadVersion(selected.value.latest_version), loadVersions()]) }
async function remove() { if (!selected.value || !confirm(t('scripts.confirmDelete'))) return; await api.delete(`/workspaces/${workspaces.activeId}/scripts/${selected.value.id}`); showEditor.value = false; await load() }
onMounted(async () => { await workspaces.load(); await Promise.all([load(), loadTemplates()]) })
watch(() => workspaces.activeId, () => Promise.all([load(), loadTemplates()]))
</script>

<template>
  <AppShell><div class="px-4 py-5 sm:px-7">
    <PageHeader :title="t('scripts.title')" :subtitle="t('scripts.subtitle')"><template #actions><input ref="fileInput" type="file" class="hidden" accept=".py,.zip" @change="upload"><Button variant="secondary" :loading="saving" @click="fileInput?.click()"><Upload :size="16" />{{ t('scripts.upload') }}</Button><Button @click="newScript"><Plus :size="16" />{{ t('scripts.newScript') }}</Button></template></PageHeader>
    <AlertBanner :message="error" tone="error" /><SearchInput v-model="search" class="mt-5 w-full sm:w-72" :placeholder="t('common.search')" />
    <div v-if="filtered.length" class="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3"><ActionCard v-for="item in filtered" :key="item.id" class="rounded-lg p-4" @click="edit(item)"><div class="flex items-start gap-3"><span class="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600 dark:bg-emerald-950/40"><FileCode2 :size="20" /></span><div class="min-w-0"><h2 class="truncate font-semibold">{{ item.name }}</h2><p class="muted mt-1 line-clamp-2 text-sm">{{ item.description || 'Python · main(inputs, context)' }}</p></div></div><div class="muted mt-5 flex justify-between border-t border-[var(--border)] pt-3 text-xs"><span>{{ t('scripts.version') }} {{ item.latest_version }}</span><span>{{ item.tags?.join(', ') }}</span></div></ActionCard></div>
    <EmptyState v-else class="mt-16" :title="t('scripts.empty')"><template #icon><Braces :size="42" /></template></EmptyState>

    <ModalShell v-model="showEditor" :title="selected ? t('scripts.edit') : t('scripts.newScript')" max-width="max-w-[1180px]" panel-class="h-[92vh]" body-class="flex min-h-0 flex-col !overflow-hidden p-0" form @submit="save">
      <div class="grid shrink-0 gap-3 border-b border-[var(--border)] p-4 lg:grid-cols-[minmax(0,1fr)_220px_260px]"><InputText v-model="form.name" :placeholder="t('scripts.name')" required /><InputText v-model="form.tagsText" :placeholder="t('scripts.tags')" /><Select :model-value="''" :placeholder="t('scripts.applyTemplate')" :options="templates.map(item => ({ label: item.name, value: item.id }))" @update:model-value="applyTemplate(templates.find(item => item.id === $event)!, true)" /></div>
      <div class="flex shrink-0 overflow-x-auto border-b border-[var(--border)] px-2 sm:px-4"><button v-for="tab in editorTabs" :key="tab.id" type="button" class="h-11 shrink-0 border-b-2 px-3 text-xs sm:px-4" :class="activeTab === tab.id ? 'border-[var(--primary)] font-semibold text-[var(--primary)]' : 'border-transparent text-[var(--muted)] hover:text-[var(--text)]'" @click="activeTab = tab.id"><span>{{ tab.label }}</span><span v-if="tab.count !== undefined" class="ml-1.5 rounded bg-[var(--panel-subtle)] px-1.5 py-0.5 text-[9px]">{{ tab.count }}</span></button></div>
      <div class="min-h-0 flex-1 overflow-y-auto">
        <div v-if="activeTab === 'code'" class="grid min-h-[550px] lg:h-full lg:min-h-0 lg:grid-cols-[190px_minmax(0,1fr)] lg:overflow-hidden">
          <aside class="border-r border-[var(--border)] bg-[var(--panel-subtle)] p-3 lg:min-h-0 lg:overflow-y-auto"><div class="mb-3 flex items-center gap-2"><InputText v-model="newFileName" class="!h-8 font-mono !text-[10px]" placeholder="helpers/text.py" @keydown.enter.prevent="addFile" /><IconButton :label="t('scripts.addFile')" size="sm" @click="addFile"><FilePlus2 :size="14" /></IconButton></div><button v-for="name in files" :key="name" type="button" class="group flex w-full items-center gap-2 rounded-md px-2 py-2 text-left font-mono text-[10px]" :class="activeFile === name ? 'bg-[var(--primary-soft)] text-[var(--primary)]' : 'hover:bg-[var(--panel)]'" @click="activeFile = name"><FileCode2 :size="13" /><span class="min-w-0 flex-1 truncate">{{ name }}</span><Trash2 v-if="files.length > 1" :size="12" class="opacity-0 group-hover:opacity-100" @click.stop="removeFile(name)" /></button></aside>
          <section class="min-w-0 p-4 lg:flex lg:min-h-0 lg:flex-col"><div class="mb-3 grid shrink-0 gap-3 lg:grid-cols-[minmax(0,1fr)_220px_260px]"><InputText v-model="form.description" :placeholder="t('common.description')" /><InputText v-model="form.entrypoint" class="font-mono" :placeholder="t('scripts.entrypoint')" /><div class="flex min-h-10 items-center gap-3 rounded-md border border-[var(--border)] bg-[var(--input-bg)] px-3"><span class="min-w-0 flex-1"><span class="block text-xs font-semibold">{{ t('scripts.networkAccess') }}</span><span class="muted mt-0.5 block truncate text-[10px]">{{ t('scripts.networkAccessHint') }}</span></span><ToggleSwitch v-model="form.network_enabled" :label="t('scripts.networkAccess')" /></div></div><div class="h-[480px] lg:h-auto lg:min-h-0 lg:flex-1"><CodeEditor v-model="activeSource" language="python" height="100%" /></div></section>
        </div>
        <section v-else-if="activeTab === 'inputs'" class="p-5"><ScriptSchemaEditor v-model="form.input_schema" /></section>
        <section v-else-if="activeTab === 'outputs'" class="p-5"><ScriptSchemaEditor v-model="form.output_schema" output /></section>
        <section v-else-if="activeTab === 'test'" class="grid min-h-[550px] divide-y divide-[var(--border)] lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:divide-x lg:divide-y-0"><div class="space-y-3 p-5"><h3 class="text-sm font-semibold">{{ t('scripts.testInputs') }}</h3><label v-for="(schema, name) in inputProperties" :key="name" class="block text-xs font-semibold"><span>{{ name }}<span v-if="form.input_schema.required?.includes(name)" class="ml-1 text-red-500">*</span></span><span v-if="['file','files'].includes(scriptSchemaKind(schema))" class="mt-1.5 flex items-center gap-2"><label class="inline-flex h-9 min-w-0 flex-1 cursor-pointer items-center gap-2 rounded-md border border-[var(--border)] bg-[var(--input-bg)] px-3 font-normal"><Upload :size="14" class="shrink-0 text-[var(--primary)]" /><span class="min-w-0 flex-1 truncate">{{ testFileNames(testValues[name]) || t('scripts.chooseTestFile') }}</span><input class="hidden" type="file" :multiple="scriptSchemaKind(schema) === 'files'" @change="uploadTestFiles(String(name), schema, $event)"></label><IconButton v-if="testFileNames(testValues[name])" :label="t('common.clear')" tone="danger" size="sm" @click="clearTestFiles(String(name))"><Trash2 :size="13" /></IconButton></span><span v-else-if="uploadingTestField === String(name)" class="muted mt-1.5 block text-[10px]">{{ t('common.loading') }}</span><Textarea v-else-if="['object','array'].includes(schema.type)" class="mt-1.5 h-24 font-mono !text-xs" :model-value="JSON.stringify(testValues[name], null, 2)" @update:model-value="setStructuredTestValue(String(name), $event)" /><label v-else-if="schema.type === 'boolean'" class="mt-2 flex items-center gap-2 font-normal"><input v-model="testValues[name]" type="checkbox">{{ schema.description }}</label><InputText v-else :model-value="testValues[name] == null ? '' : String(testValues[name])" class="mt-1.5" :type="['number','integer'].includes(schema.type) ? 'number' : 'text'" :placeholder="schema.description || String(name)" @update:model-value="setScalarTestValue(String(name), schema, $event)" /></label><p v-if="!Object.keys(inputProperties).length" class="muted py-12 text-center text-xs">{{ t('scripts.noInputs') }}</p><div class="flex gap-2"><Button type="button" :loading="testing" @click="test"><Play :size="15" />{{ t('scripts.runDraft') }}</Button><Button v-if="testing" type="button" variant="secondary" @click="cancelTest"><Square :size="14" />{{ t('common.cancel') }}</Button></div></div><div class="min-w-0 p-5"><h3 class="text-sm font-semibold">{{ t('scripts.testOutput') }}</h3><div v-if="testLogs.length" class="mt-3 max-h-48 overflow-auto rounded-lg bg-slate-950 p-3 font-mono text-[11px] text-slate-100"><div v-for="(line, index) in testLogs" :key="index">{{ line }}</div></div><WorkflowOutputRenderer v-if="testResult?.status === 'succeeded'" class="mt-3" :output="testResult.outputs" /><pre v-else-if="testResult" class="mt-3 max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-950 p-3 text-xs text-slate-100">{{ JSON.stringify(testResult, null, 2) }}</pre><p v-else class="muted py-16 text-center text-xs">{{ testing ? t('scripts.testRunning') : t('scripts.noTestResult') }}</p></div></section>
        <section v-else class="grid min-h-[550px] divide-y divide-[var(--border)] lg:grid-cols-[360px_minmax(0,1fr)] lg:divide-x lg:divide-y-0"><div class="p-4"><div v-for="version in versions" :key="version.version" class="mb-2 flex items-center gap-3 rounded-lg border border-[var(--border)] p-3"><div class="min-w-0 flex-1"><div class="text-xs font-semibold">{{ t('scripts.version') }} {{ version.version }}</div><div class="muted mt-1 truncate text-[10px]">{{ version.change_note || version.entrypoint }}</div></div><Button size="sm" variant="ghost" type="button" @click="loadDiff(version.version)">{{ t('scripts.diff') }}</Button><IconButton :label="t('scripts.restore')" size="sm" @click="restoreVersion(version.version)"><RotateCcw :size="13" /></IconButton></div><div class="mt-3 flex justify-between"><Button size="sm" variant="secondary" type="button" :disabled="versionOffset === 0" @click="loadVersions(Math.max(0, versionOffset - 20))">{{ t('common.previous') }}</Button><Button size="sm" variant="secondary" type="button" :disabled="versionOffset + 20 >= versionTotal" @click="loadVersions(versionOffset + 20)">{{ t('common.next') }}</Button></div></div><pre class="min-w-0 overflow-auto whitespace-pre p-4 font-mono text-[11px]">{{ versionDiff || t('scripts.selectVersionDiff') }}</pre></section>
      </div>
      <template #footer><Button v-if="selected" class="mr-auto" type="button" variant="danger" @click="remove"><Trash2 :size="15" />{{ t('common.delete') }}</Button><InputText v-model="form.change_note" class="mr-2 max-w-sm" :placeholder="t('scripts.changeNote')" /><Button type="button" variant="secondary" @click="showEditor = false">{{ t('common.cancel') }}</Button><Button type="submit" :loading="saving">{{ t('common.save') }}</Button></template>
    </ModalShell>
  </div></AppShell>
</template>
