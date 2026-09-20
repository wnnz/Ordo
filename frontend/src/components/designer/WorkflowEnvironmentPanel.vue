<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { Braces, Copy, EyeOff, Pencil, Plus, ShieldCheck, Trash2, X } from 'lucide-vue-next'
import AlertBanner from '@/components/ui/AlertBanner.vue'
import ChoiceCard from '@/components/ui/ChoiceCard.vue'
import ModalShell from '@/components/ui/ModalShell.vue'
import Button from '@/volt/Button.vue'
import InputText from '@/volt/InputText.vue'
import Textarea from '@/volt/Textarea.vue'

export interface WorkflowEnvironmentVariable {
  id: string
  name: string
  value_type: 'string' | 'number' | 'secret'
  value: string
  has_value: boolean
  description: string
}
const props = defineProps<{ variables: WorkflowEnvironmentVariable[]; saving?: boolean; error?: string }>()
const emit = defineEmits<{
  close: []
  create: [payload: { name: string; value_type: string; value: string; description: string }]
  update: [payload: { id: string; name: string; value_type: string; value?: string; description: string }]
  delete: [id: string]
}>()
const editorOpen = ref(false)
const editingId = ref<string | null>(null)
const copiedName = ref('')
const form = reactive({ name: '', value_type: 'secret' as 'string' | 'number' | 'secret', value: '', description: '' })
const editing = computed(() => props.variables.find(item => item.id === editingId.value) || null)
function openCreate() { editingId.value = null; Object.assign(form, { name: '', value_type: 'secret', value: '', description: '' }); editorOpen.value = true }
function openEdit(variable: WorkflowEnvironmentVariable) { editingId.value = variable.id; Object.assign(form, { name: variable.name, value_type: variable.value_type, value: '', description: variable.description }); editorOpen.value = true }
function submit() {
  if (!form.name.trim()) return
  if (editingId.value) emit('update', { id: editingId.value, name: form.name.trim(), value_type: form.value_type, ...(form.value ? { value: form.value } : {}), description: form.description.trim() })
  else emit('create', { name: form.name.trim(), value_type: form.value_type, value: form.value, description: form.description.trim() })
}
function closeEditor() { editorOpen.value = false }
function markSaved() { editorOpen.value = false }
async function copyReference(name: string) { await navigator.clipboard.writeText(`{{env.${name}}}`); copiedName.value = name; setTimeout(() => { if (copiedName.value === name) copiedName.value = '' }, 1200) }
defineExpose({ markSaved })
</script>

<template>
  <div class="surface absolute right-0 top-10 z-50 w-[390px] overflow-hidden rounded-xl shadow-2xl" role="dialog" :aria-label="$t('designer.environmentVariables')">
    <header class="flex items-start gap-3 border-b border-[var(--border)] px-4 py-3.5"><span class="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--primary-soft)] font-mono text-[10px] font-bold text-[var(--primary)]">ENV</span><div class="min-w-0 flex-1"><h2 class="text-sm font-semibold">{{ $t('designer.environmentVariables') }}</h2><p class="muted mt-1 text-[10px] leading-4">{{ $t('designer.environmentVariablesHint') }}</p></div><button type="button" class="icon-button" :aria-label="$t('common.close')" @click="emit('close')"><X :size="15" /></button></header>
    <div class="max-h-[420px] overflow-y-auto p-3">
      <div v-for="variable in variables" :key="variable.id" class="mb-2 rounded-lg border border-[var(--border)] p-3 last:mb-0">
        <div class="flex items-center gap-2"><span class="flex h-6 w-6 items-center justify-center rounded-md bg-[var(--panel-subtle)]"><EyeOff v-if="variable.value_type === 'secret'" :size="13" /><Braces v-else :size="13" /></span><code class="min-w-0 flex-1 truncate text-xs font-semibold">env.{{ variable.name }}</code><span class="rounded bg-[var(--panel-subtle)] px-1.5 py-0.5 text-[9px] uppercase text-[var(--muted)]">{{ variable.value_type }}</span><button type="button" class="icon-button !h-7 !w-7" :aria-label="$t('designer.copyEnvironmentReference')" @click="copyReference(variable.name)"><ShieldCheck v-if="copiedName === variable.name" :size="13" class="text-emerald-600" /><Copy v-else :size="13" /></button><button type="button" class="icon-button !h-7 !w-7" :aria-label="$t('common.edit')" @click="openEdit(variable)"><Pencil :size="13" /></button><button type="button" class="icon-button !h-7 !w-7 text-red-600" :aria-label="$t('common.delete')" @click="emit('delete', variable.id)"><Trash2 :size="13" /></button></div>
        <p v-if="variable.description" class="muted mt-2 text-[10px]">{{ variable.description }}</p><div class="mt-2 truncate rounded bg-[var(--panel-subtle)] px-2 py-1.5 font-mono text-[10px]">{{ variable.value_type === 'secret' ? (variable.has_value ? '••••••••' : '') : variable.value }}</div>
      </div>
      <div v-if="!variables.length" class="muted py-9 text-center"><ShieldCheck :size="28" class="mx-auto mb-3 opacity-35" /><p class="text-xs">{{ $t('designer.noEnvironmentVariables') }}</p></div>
    </div>
    <div class="border-t border-[var(--border)] p-3"><Button class="w-full" variant="secondary" @click="openCreate"><Plus :size="14" />{{ $t('designer.addEnvironmentVariable') }}</Button></div>
    <AlertBanner v-if="error && !editorOpen" class="m-3 mt-0" :message="error" tone="error" />
  </div>

  <ModalShell v-model="editorOpen" :title="editing ? $t('designer.editEnvironmentVariable') : $t('designer.addEnvironmentVariable')" :description="$t('designer.environmentVariableEditorHint')" form @submit="submit">
    <div class="grid grid-cols-3 gap-2" role="radiogroup" :aria-label="$t('designer.variableType')"><ChoiceCard v-for="type in ['string','number','secret']" :key="type" role="radio" :aria-checked="form.value_type === type" :selected="form.value_type === type" class="px-3 py-2 text-xs" @click="form.value_type = type as any">{{ $t(`designer.environmentTypes.${type}`) }}</ChoiceCard></div>
    <label class="field-label mt-4">{{ $t('designer.variableName') }}<InputText v-model="form.name" class="mt-1.5 font-mono" placeholder="API_KEY" /></label>
    <label class="field-label mt-4">{{ $t('designer.variableValue') }}<InputText v-model="form.value" class="mt-1.5 font-mono" :type="form.value_type === 'secret' ? 'password' : form.value_type === 'number' ? 'number' : 'text'" :placeholder="editing && form.value_type === 'secret' ? $t('designer.keepSecretValue') : ''" /></label>
    <label class="field-label mt-4">{{ $t('designer.description') }}<Textarea v-model="form.description" class="mt-1.5 h-20 !text-xs" /></label>
    <AlertBanner v-if="error" class="mt-4" :message="error" tone="error" />
    <template #footer><Button variant="secondary" @click="closeEditor">{{ $t('common.cancel') }}</Button><Button type="submit" :loading="saving" :disabled="!form.name.trim()">{{ $t('common.save') }}</Button></template>
  </ModalShell>
</template>
