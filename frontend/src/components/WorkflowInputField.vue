<script setup lang="ts">
import { FileUp, UploadCloud } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import FormField from '@/components/ui/FormField.vue'
import InputText from '@/volt/InputText.vue'
import Select from '@/volt/Select.vue'
import Textarea from '@/volt/Textarea.vue'

const props = withDefaults(defineProps<{ field: any; modelValue: any; uploading?: boolean }>(), { uploading: false })
const emit = defineEmits<{ 'update:modelValue': [value: any]; 'file-change': [event: Event] }>()
const { t } = useI18n()
function fileNames() {
  if (!props.modelValue) return ''
  return Array.isArray(props.modelValue) ? props.modelValue.map((file: any) => file.filename).join(', ') : props.modelValue.filename
}
</script>

<template>
  <FormField :label="field.label || field.name" :required="field.required">
    <Textarea v-if="field.type === 'textarea'" :model-value="modelValue" class="h-24" :placeholder="field.placeholder" :required="field.required" :maxlength="field.max_length || undefined" @update:model-value="emit('update:modelValue', $event)" />
    <Select v-else-if="field.type === 'select'" :model-value="modelValue" :required="field.required" @update:model-value="emit('update:modelValue', $event)"><option v-if="field.placeholder" value="" :disabled="field.required">{{ field.placeholder }}</option><option v-for="option in field.options" :key="option" :value="option">{{ option }}</option></Select>
    <div v-else-if="field.type === 'file' || field.type === 'files'"><label class="flex min-h-20 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-[var(--border)] bg-[var(--input-bg)]"><UploadCloud :size="20" class="text-[var(--primary)]" /><span class="muted mt-1.5 text-xs">{{ uploading ? t('common.loading') : t('designer.chooseFile') }}</span><input class="hidden" type="file" :multiple="field.type === 'files'" :required="field.required && !modelValue" @change="emit('file-change', $event)"></label><div v-if="modelValue" class="mt-2 text-xs text-[var(--primary)]"><FileUp class="mr-1 inline" :size="13" />{{ fileNames() }}</div></div>
    <InputText v-else :model-value="modelValue" :type="field.type === 'number' ? 'number' : field.type === 'month' ? 'month' : 'text'" :placeholder="field.placeholder" :required="field.required" :maxlength="field.max_length || undefined" :min="field.type === 'number' ? field.min : undefined" :max="field.type === 'number' ? field.max : undefined" @update:model-value="emit('update:modelValue', $event)" />
  </FormField>
</template>
