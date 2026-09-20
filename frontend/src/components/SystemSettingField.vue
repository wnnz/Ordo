<script setup lang="ts">
import { computed } from 'vue'
import { RotateCcw } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import FormField from '@/components/ui/FormField.vue'
import Button from '@/volt/Button.vue'
import InputText from '@/volt/InputText.vue'
import ToggleSwitch from '@/volt/ToggleSwitch.vue'
import type { SystemSetting, SystemSettingValue } from '@/types/systemSettings'

const props = defineProps<{ setting: SystemSetting }>()
const emit = defineEmits<{
  'update:value': [value: SystemSettingValue]
  reset: []
}>()
const { t } = useI18n()

const label = computed(() => t(`systemSettings.labels.${props.setting.key}`))
const hint = computed(() => t(`systemSettings.hints.${props.setting.key}`))
const displayValue = computed(() => {
  if (props.setting.type === 'boolean') {
    return props.setting.value ? t('systemSettings.enabled') : t('systemSettings.disabled')
  }
  const value = Number(props.setting.value)
  if (props.setting.key === 'max_upload_bytes') {
    return `${(value / 1024 / 1024).toFixed(value % (1024 * 1024) ? 1 : 0)} MB`
  }
  return `${value} ${t(`systemSettings.units.${props.setting.unit}`)}`
})
const helperText = computed(() => {
  const detail = props.setting.type === 'boolean'
    ? (props.setting.value ? t('systemSettings.enabled') : t('systemSettings.disabled'))
    : t('systemSettings.range', { min: props.setting.minimum, max: props.setting.maximum })
  const source = props.setting.source === 'database'
    ? t('systemSettings.database')
    : t('systemSettings.environment')
  return `${detail} · ${source}`
})

function updateValue(value: string | number | boolean) {
  emit('update:value', props.setting.type === 'boolean' ? Boolean(value) : Number(value))
}
</script>

<template>
  <FormField :label="label" :hint="hint" hint-after>
    <div class="flex items-center gap-2">
      <template v-if="setting.type === 'boolean'">
        <ToggleSwitch
          :model-value="Boolean(setting.value)"
          :label="label"
          @update:model-value="updateValue"
        />
        <span class="muted shrink-0 text-xs">{{ displayValue }}</span>
      </template>
      <template v-else>
        <InputText
          :model-value="String(setting.value)"
          type="number"
          :min="setting.minimum ?? undefined"
          :max="setting.maximum ?? undefined"
          class="font-mono"
          @update:model-value="updateValue"
        />
        <span class="muted shrink-0 text-xs">{{ displayValue }}</span>
      </template>
      <Button
        variant="ghost"
        size="sm"
        :aria-label="t('systemSettings.reset')"
        @click="emit('reset')"
      >
        <RotateCcw :size="14" />
      </Button>
    </div>
    <span class="muted mt-1 block text-[11px]">{{ helperText }}</span>
  </FormField>
</template>
