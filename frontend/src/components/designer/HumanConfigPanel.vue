<script setup lang="ts">
import { computed } from 'vue'
import { Link2, Mail, Monitor, Plus, Trash2 } from 'lucide-vue-next'
import VariableField from '@/components/VariableField.vue'
import ChoiceCard from '@/components/ui/ChoiceCard.vue'
import FormField from '@/components/ui/FormField.vue'
import InputText from '@/volt/InputText.vue'
import Select from '@/volt/Select.vue'
import NodeConfigSection from './NodeConfigSection.vue'
import NodeSettingCard from './NodeSettingCard.vue'

const props = defineProps<{ config: Record<string, any>; variableGroups: any[] }>()
const emit = defineEmits<{ connect: [handle: string]; remove: [id: string] }>()
const methods = [
  { id: 'studio', icon: Monitor },
  { id: 'link', icon: Link2 },
  { id: 'email', icon: Mail },
]
const days = computed({
  get: () => String(Math.floor(Number(props.config.timeout_minutes || 0) / 1440)),
  set: value => { props.config.timeout_minutes = Math.max(1, Number(value || 0) * 1440 + Number(hours.value) * 60) },
})
const hours = computed({
  get: () => String(Math.floor((Number(props.config.timeout_minutes || 0) % 1440) / 60)),
  set: value => { props.config.timeout_minutes = Math.max(1, Number(days.value) * 1440 + Number(value || 0) * 60) },
})

function toggleMethod(id: string) {
  const current = Array.isArray(props.config.submission_methods) ? props.config.submission_methods : []
  props.config.submission_methods = current.includes(id) ? current.filter((item: string) => item !== id) : [...current, id]
}
function addAction() {
  const actions = Array.isArray(props.config.actions) ? props.config.actions : []
  const index = actions.length + 1
  props.config.actions = [...actions, { id: `action_${index}`, label: `Action ${index}`, value: `action_${index}`, style: 'secondary' }]
}
</script>

<template>
  <section class="mt-5">
    <NodeConfigSection :title="$t('designer.nodeParameters')" :hint="$t('designer.nodeParametersHint')" kind="parameters">
      <div class="space-y-4">
        <NodeConfigSection :title="$t('designer.submissionMethods')" :hint="$t('designer.submissionMethodsHint')">
          <div class="grid grid-cols-3 gap-2">
            <ChoiceCard v-for="method in methods" :key="method.id" :selected="config.submission_methods?.includes(method.id)" class="flex h-16 flex-col items-center justify-center gap-1.5 text-[10px] font-medium" @click="toggleMethod(method.id)"><component :is="method.icon" :size="16" />{{ $t(`designer.submissionMethod.${method.id}`) }}</ChoiceCard>
          </div>
        </NodeConfigSection>

        <NodeConfigSection class="border-t border-[var(--border)] pt-4" :title="$t('designer.userActions')" :hint="$t('designer.userActionsHint')" :count="config.actions.length">
          <template #actions><button class="icon-button" type="button" :title="$t('designer.addAction')" :aria-label="$t('designer.addAction')" @click="addAction"><Plus :size="14" /></button></template>
          <div class="space-y-3">
            <NodeSettingCard v-for="action in config.actions" :key="action.id">
              <div class="grid grid-cols-[minmax(0,1fr)_84px_30px] gap-2"><InputText v-model="action.label" :placeholder="$t('designer.actionLabel')" /><Select v-model="action.style"><option value="primary">{{ $t('designer.primaryAction') }}</option><option value="secondary">{{ $t('designer.secondaryAction') }}</option><option value="danger">{{ $t('designer.dangerAction') }}</option></Select><button class="icon-button !h-9 !w-9 text-red-600" type="button" :title="$t('common.delete')" @click="emit('remove', action.id)"><Trash2 :size="13" /></button></div>
              <div class="mt-2 grid grid-cols-2 gap-2"><FormField label="ID" compact><InputText v-model="action.id" class="font-mono" /></FormField><FormField :label="$t('designer.actionValue')" compact><InputText v-model="action.value" class="font-mono" /></FormField></div>
              <button type="button" class="mt-3 flex h-9 w-full items-center justify-center gap-2 rounded-md border border-dashed border-[var(--border)] text-[10px] text-[var(--muted)] hover:border-[var(--primary)] hover:text-[var(--primary)]" @click="emit('connect', `action:${action.id}`)"><Plus :size="12" />{{ $t('designer.connectActionBranch') }}</button>
            </NodeSettingCard>
          </div>
        </NodeConfigSection>

        <NodeConfigSection class="border-t border-[var(--border)] pt-4" :title="$t('designer.timeoutSettings')">
          <div class="grid grid-cols-2 gap-3"><FormField :label="$t('designer.days')" compact><InputText v-model="days" type="number" min="0" max="365" /></FormField><FormField :label="$t('designer.hours')" compact><InputText v-model="hours" type="number" min="0" max="23" /></FormField></div>
        </NodeConfigSection>
      </div>
    </NodeConfigSection>

    <NodeConfigSection class="mt-5 border-t border-[var(--border)] pt-5" :title="$t('designer.inputVariables')" :hint="$t('designer.inputVariablesHint')" :count="1" kind="input" collapsible><NodeSettingCard :title="$t('designer.formContent')" :hint="$t('designer.formContentHint')" type="String" required><VariableField v-model="config.form_content" class="font-mono" :groups="variableGroups" multiline :rows="7" :placeholder="$t('designer.formContentPlaceholder')" /></NodeSettingCard></NodeConfigSection>
  </section>
</template>
