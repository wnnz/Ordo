<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RotateCcw, Save, Settings2 } from 'lucide-vue-next'
import api from '@/api/client'
import AppShell from '@/components/AppShell.vue'
import AlertBanner from '@/components/ui/AlertBanner.vue'
import FormField from '@/components/ui/FormField.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import Button from '@/volt/Button.vue'
import InputText from '@/volt/InputText.vue'
import ToggleSwitch from '@/volt/ToggleSwitch.vue'

type Setting = {
  key: string
  value: number | boolean
  default: number | boolean
  minimum: number | null
  maximum: number | null
  unit: string
  type: 'integer' | 'boolean'
  source: 'database' | 'environment'
}

const { t } = useI18n()
const settings = ref<Setting[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const message = ref('')

const groups = computed(() => [
  { id: 'accounts', title: t('systemSettings.accounts'), keys: ['disable_user_registration'] },
  { id: 'files', title: t('systemSettings.files'), keys: ['max_upload_bytes', 'file_upload_retention_hours', 'file_output_retention_days', 'file_orphan_grace_hours', 'file_cleanup_batch_size'] },
  { id: 'public', title: t('systemSettings.public'), keys: ['public_rate_limit_requests', 'public_access_rate_limit_requests', 'public_upload_rate_limit_requests', 'public_rate_limit_window_seconds', 'public_max_active_runs_per_app'] },
  { id: 'runs', title: t('systemSettings.runs'), keys: ['workflow_run_lease_seconds', 'workflow_pending_recovery_seconds'] },
])

function setting(key: string) { return settings.value.find(item => item.key === key) }
function label(key: string) { return t(`systemSettings.labels.${key}`) }
function hint(key: string) { return t(`systemSettings.hints.${key}`) }
function setValue(key: string, value: string | number | boolean) {
  const item = setting(key)
  if (item) item.value = item.type === 'boolean' ? Boolean(value) : Number(value)
}
function displayValue(item: Setting) {
  if (item.type === 'boolean') return item.value ? t('systemSettings.enabled') : t('systemSettings.disabled')
  const value = Number(item.value)
  if (item.key === 'max_upload_bytes') return `${(value / 1024 / 1024).toFixed(value % (1024 * 1024) ? 1 : 0)} MB`
  return `${value} ${t(`systemSettings.units.${item.unit}`)}`
}
function reset(item: Setting) { item.value = item.default }
async function load() {
  loading.value = true; error.value = ''
  try { settings.value = (await api.get<Setting[]>('/admin/settings')).data }
  catch (cause: any) { error.value = cause.response?.data?.detail || String(cause) }
  finally { loading.value = false }
}
async function save() {
  saving.value = true; error.value = ''; message.value = ''
  try {
    settings.value = (await api.put<Setting[]>('/admin/settings', { values: Object.fromEntries(settings.value.map(item => [item.key, item.value])) })).data
    message.value = t('systemSettings.saved')
  } catch (cause: any) { error.value = cause.response?.data?.detail || String(cause) }
  finally { saving.value = false }
}
onMounted(load)
</script>

<template>
  <AppShell>
    <div class="mx-auto max-w-5xl px-5 py-5 sm:px-7">
      <PageHeader :title="t('systemSettings.title')" :subtitle="t('systemSettings.subtitle')">
        <template #actions><Button variant="secondary" :loading="loading" @click="load">{{ t('common.refresh') }}</Button><Button :loading="saving" @click="save"><Save :size="15" />{{ t('common.save') }}</Button></template>
      </PageHeader>
      <AlertBanner :message="message" tone="success" /><AlertBanner :message="error" tone="error" />
      <div v-if="!loading" class="mt-5 space-y-5">
        <section v-for="group in groups" :key="group.id" class="surface rounded-xl p-5">
          <div class="flex items-start gap-3"><span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--primary-soft)] text-[var(--primary)]"><Settings2 :size="18" /></span><div><h2 class="font-semibold">{{ group.title }}</h2><p class="muted mt-1 text-xs">{{ t(`systemSettings.groupHints.${group.id}`) }}</p></div></div>
          <div class="mt-5 grid gap-4 md:grid-cols-2">
            <template v-for="key in group.keys" :key="key">
              <FormField v-if="setting(key)" :label="label(key)" :hint="hint(key)" hint-after>
                <div class="flex items-center gap-2">
                  <template v-if="setting(key)!.type === 'boolean'"><ToggleSwitch :model-value="Boolean(setting(key)!.value)" :label="label(key)" @update:model-value="setValue(key, $event)" /><span class="muted shrink-0 text-xs">{{ displayValue(setting(key)!) }}</span></template>
                  <InputText v-else :model-value="String(setting(key)!.value)" type="number" :min="setting(key)!.minimum ?? undefined" :max="setting(key)!.maximum ?? undefined" class="font-mono" @update:model-value="setValue(key, $event)" />
                  <span v-if="setting(key)!.type !== 'boolean'" class="muted shrink-0 text-xs">{{ displayValue(setting(key)!) }}</span><Button variant="ghost" size="sm" :aria-label="t('systemSettings.reset')" @click="reset(setting(key)!)"><RotateCcw :size="14" /></Button>
                </div>
                <span class="muted mt-1 block text-[11px]">{{ setting(key)!.type === 'boolean' ? (setting(key)!.value ? t('systemSettings.enabled') : t('systemSettings.disabled')) : t('systemSettings.range', { min: setting(key)!.minimum, max: setting(key)!.maximum }) }} · {{ setting(key)!.source === 'database' ? t('systemSettings.database') : t('systemSettings.environment') }}</span>
              </FormField>
            </template>
          </div>
        </section>
      </div>
    </div>
  </AppShell>
</template>
