<script setup lang="ts">
import { computed, ref } from 'vue'
import { BrainCircuit, Braces, Plus, Trash2, Wrench } from 'lucide-vue-next'
import VariableField from '@/components/VariableField.vue'
import ChoiceCard from '@/components/ui/ChoiceCard.vue'
import FormField from '@/components/ui/FormField.vue'
import InputText from '@/volt/InputText.vue'
import Select from '@/volt/Select.vue'
import ToggleSwitch from '@/volt/ToggleSwitch.vue'
import NodeConfigSection from './NodeConfigSection.vue'
import NodeSettingCard from './NodeSettingCard.vue'

const props = defineProps<{ config: any; providers: any[]; scripts: any[]; variableGroups: any[] }>()
const emit = defineEmits<{ providerChange: [] }>()
const candidate = ref('')

function ensureConfig() {
  props.config.strategy ||= 'tool_calling'
  if (typeof props.config.query !== 'string') props.config.query = ''
  props.config.tools = Array.isArray(props.config.tools) ? props.config.tools : []
  props.config.memory = { enabled: false, window: 10, ...(props.config.memory || {}) }
  if (props.config.return_intermediate_steps == null) props.config.return_intermediate_steps = false
}
ensureConfig()

const candidates = computed(() => [
  ...props.scripts.map(item => ({ key: `script:${item.id}`, type: 'script', id: item.id, name: item.name })),
])

function addTool() {
  const item = candidates.value.find(value => value.key === candidate.value)
  if (!item || props.config.tools.some((tool: any) => tool.type === item.type && tool.reference_id === item.id)) return
  props.config.tools.push({ id: crypto.randomUUID().slice(0, 12), type: item.type, reference_id: item.id, name: item.name, enabled: true, description: '' })
  candidate.value = ''
}
function removeTool(id: string) { props.config.tools = props.config.tools.filter((tool: any) => tool.id !== id) }
function toolIcon(_type?: string) { return Braces }
</script>

<template>
  <section class="mt-5">
    <NodeConfigSection :title="$t('designer.nodeParameters')" :hint="$t('designer.nodeParametersHint')" kind="parameters">
      <div class="space-y-4">
        <NodeConfigSection :title="$t('designer.agentStrategy')">
          <template #icon><BrainCircuit :size="14" /></template>
          <div class="grid grid-cols-2 gap-2">
            <ChoiceCard v-for="strategy in ['tool_calling','react']" :key="strategy" :selected="config.strategy === strategy" class="p-3 text-left" @click="config.strategy = strategy">
              <span class="block text-xs font-semibold" :class="config.strategy === strategy && 'text-[var(--primary)]'">{{ $t(`designer.agentStrategies.${strategy}`) }}</span>
              <span class="muted mt-1 block text-[9px] leading-4">{{ $t(`designer.agentStrategyHints.${strategy}`) }}</span>
            </ChoiceCard>
          </div>
        </NodeConfigSection>

        <FormField :label="$t('designer.modelProvider')" required compact><Select v-model="config.provider_id" @change="emit('providerChange')"><option value="">{{ $t('designer.selectModelProvider') }}</option><option v-for="provider in providers" :key="provider.id" :value="provider.id">{{ provider.name }} · {{ provider.default_model }}</option></Select></FormField>
        <p v-if="!providers.length" class="resource-empty">{{ $t('designer.noModels') }}</p>
        <FormField :label="$t('designer.modelName')" compact><InputText v-model="config.model" placeholder="gpt-4.1-mini" /></FormField>

        <NodeConfigSection class="border-t border-[var(--border)] pt-4" :title="$t('designer.agentTools')" :hint="$t('designer.agentToolsHint')" :count="config.tools.length">
          <template #icon><Wrench :size="14" /></template>
          <div class="flex gap-2"><Select v-model="candidate" class="min-w-0 flex-1"><option value="">{{ $t('designer.selectAgentTool') }}</option><option v-for="item in candidates" :key="item.key" :value="item.key">{{ item.name }} · {{ $t(`designer.agentToolTypes.${item.type}`) }}</option></Select><button type="button" class="icon-button surface !h-9 !w-9" :disabled="!candidate" :aria-label="$t('designer.addAgentTool')" @click="addTool"><Plus :size="14" /></button></div>
          <div class="mt-2 space-y-2">
            <NodeSettingCard v-for="tool in config.tools" :key="tool.id" :title="tool.name" divided>
              <template #header><div class="flex min-w-0 flex-1 items-center gap-2"><span class="flex h-7 w-7 items-center justify-center rounded-md bg-[var(--panel)] text-[var(--primary)]"><component :is="toolIcon(tool.type)" :size="14" /></span><span class="min-w-0 flex-1 truncate text-xs font-semibold">{{ tool.name }}</span></div></template>
              <template #actions><div class="flex items-center gap-2"><ToggleSwitch v-model="tool.enabled" :label="$t('designer.enabled')" /><button type="button" class="icon-button !h-7 !w-7 text-red-600" :aria-label="$t('common.delete')" @click="removeTool(tool.id)"><Trash2 :size="12" /></button></div></template>
              <InputText v-model="tool.description" :placeholder="$t('designer.agentToolDescription')" />
            </NodeSettingCard>
            <div v-if="!config.tools.length" class="resource-empty text-center">{{ $t('designer.noAgentTools') }}</div>
          </div>
        </NodeConfigSection>

        <div class="grid grid-cols-2 gap-3"><FormField :label="$t('designer.maxIterations')" compact><InputText :model-value="String(config.max_iterations)" type="number" min="1" max="50" @update:model-value="config.max_iterations = Number($event)" /></FormField><FormField :label="$t('designer.memoryWindow')" compact><InputText :model-value="String(config.memory.window)" type="number" min="1" max="100" :disabled="!config.memory.enabled" @update:model-value="config.memory.window = Number($event)" /></FormField></div>
        <NodeSettingCard :title="$t('designer.enableAgentMemory')" :hint="$t('designer.enableAgentMemoryHint')"><template #actions><ToggleSwitch v-model="config.memory.enabled" :label="$t('designer.enableAgentMemory')" /></template></NodeSettingCard>
        <NodeSettingCard :title="$t('designer.returnIntermediateSteps')" :hint="$t('designer.returnIntermediateStepsHint')"><template #actions><ToggleSwitch v-model="config.return_intermediate_steps" :label="$t('designer.returnIntermediateSteps')" /></template></NodeSettingCard>
      </div>
    </NodeConfigSection>

    <NodeConfigSection class="mt-5 border-t border-[var(--border)] pt-5" :title="$t('designer.inputVariables')" :hint="$t('designer.inputVariablesHint')" :count="2" kind="input" collapsible>
      <div class="space-y-3">
        <NodeSettingCard :title="$t('designer.agentInstructions')" type="String"><VariableField v-model="config.instructions" :groups="variableGroups" multiline :rows="7" :placeholder="$t('designer.agentInstructionsPlaceholder')" /></NodeSettingCard>
        <NodeSettingCard :title="$t('designer.agentQuery')" type="String"><VariableField v-model="config.query" :groups="variableGroups" :placeholder="$t('designer.agentQueryPlaceholder')" /></NodeSettingCard>
      </div>
    </NodeConfigSection>
  </section>
</template>
