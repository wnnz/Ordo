<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Save, Settings2 } from 'lucide-vue-next'
import api from '@/api/client'
import AppShell from '@/components/AppShell.vue'
import AlertBanner from '@/components/ui/AlertBanner.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import PanelSection from '@/components/ui/PanelSection.vue'
import SystemSettingField from '@/components/SystemSettingField.vue'
import Button from '@/volt/Button.vue'
import type { SystemSetting, SystemSettingValue } from '@/types/systemSettings'

const { t } = useI18n()
const settings = ref<SystemSetting[]>([])
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
function setValue(key: string, value: SystemSettingValue) {
  const item = setting(key)
  if (item) item.value = item.type === 'boolean' ? Boolean(value) : Number(value)
}
function reset(item: SystemSetting) { item.value = item.default }
async function load() {
  loading.value = true; error.value = ''
  try { settings.value = (await api.get<SystemSetting[]>('/admin/settings')).data }
  catch (cause: any) { error.value = cause.response?.data?.detail || String(cause) }
  finally { loading.value = false }
}
async function save() {
  saving.value = true; error.value = ''; message.value = ''
  try {
    settings.value = (await api.put<SystemSetting[]>('/admin/settings', { values: Object.fromEntries(settings.value.map(item => [item.key, item.value])) })).data
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
        <PanelSection v-for="group in groups" :key="group.id" :title="group.title" :description="t(`systemSettings.groupHints.${group.id}`)">
          <template #icon><span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--primary-soft)] text-[var(--primary)]"><Settings2 :size="18" /></span></template>
          <div class="grid gap-4 md:grid-cols-2">
            <template v-for="key in group.keys" :key="key">
              <SystemSettingField v-if="setting(key)" :setting="setting(key)!" @update:value="setValue(key, $event)" @reset="reset(setting(key)!)" />
            </template>
          </div>
        </PanelSection>
      </div>
    </div>
  </AppShell>
</template>
