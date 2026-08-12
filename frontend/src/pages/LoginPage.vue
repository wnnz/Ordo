<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { Languages, Moon, Sparkles, Sun } from 'lucide-vue-next'
import api from '@/api/client'
import Button from '@/volt/Button.vue'; import InputText from '@/volt/InputText.vue'
import AlertBanner from '@/components/ui/AlertBanner.vue'; import FormField from '@/components/ui/FormField.vue'
import { useAuthStore } from '@/stores/auth'; import { usePreferencesStore } from '@/stores/preferences'
import { useWorkspacesStore } from '@/stores/workspaces'
import { safeLocalRedirect } from '@/utils/navigation'

const { t } = useI18n(); const route = useRoute(); const router = useRouter(); const auth = useAuthStore(); const preferences = usePreferencesStore(); const workspaces = useWorkspacesStore()
const registerMode = ref(false); const registrationEnabled = ref(true); const email = ref(''); const password = ref(''); const name = ref(''); const error = ref(''); const loading = ref(false)
async function loadRegistrationStatus() {
  try { registrationEnabled.value = (await api.get<{ enabled: boolean }>('/auth/registration-status')).data.enabled }
  catch { registrationEnabled.value = true }
}
async function submit() {
  loading.value = true; error.value = ''
  try {
    registerMode.value ? await auth.register(email.value, password.value, name.value) : await auth.login(email.value, password.value)
    await workspaces.load()
    const returnTo = safeLocalRedirect(route.query.redirect)
    await router.replace(returnTo || (workspaces.activeId ? `/w/${workspaces.activeId}/studio` : '/workspaces/new'))
  }
  catch (cause: any) { error.value = cause.response?.data?.detail || String(cause) }
  finally { loading.value = false }
}
onMounted(loadRegistrationStatus)
</script>

<template>
  <div class="relative flex min-h-screen items-center justify-center overflow-hidden bg-[var(--app-bg)] p-6">
    <div class="absolute left-6 top-5 flex items-center gap-2 text-lg font-bold"><span class="flex h-8 w-8 items-center justify-center rounded-xl bg-[var(--primary)] text-white">O</span>Ordo</div>
    <div class="absolute right-6 top-5 flex gap-1"><Button data-testid="locale-toggle" :aria-label="preferences.locale === 'zh' ? 'Switch to English' : '切换到中文'" variant="ghost" class="!w-9 !px-0" @click="preferences.setLocale(preferences.locale === 'zh' ? 'en' : 'zh')"><Languages :size="17" /></Button><Button data-testid="theme-toggle" :aria-label="preferences.isDark ? t('common.light') : t('common.dark')" variant="ghost" class="!w-9 !px-0" @click="preferences.setTheme(preferences.isDark ? 'light' : 'dark')"><Sun v-if="preferences.isDark" :size="17" /><Moon v-else :size="17" /></Button></div>
    <div class="absolute -left-32 top-1/3 h-96 w-96 rounded-full bg-blue-300/20 blur-3xl"></div><div class="absolute -right-20 bottom-0 h-96 w-96 rounded-full bg-violet-300/20 blur-3xl"></div>
    <form class="surface relative w-full max-w-md rounded-2xl p-8 shadow-xl shadow-slate-900/5" @submit.prevent="submit">
      <span class="mb-5 flex h-11 w-11 items-center justify-center rounded-xl bg-[var(--primary-soft)] text-[var(--primary)]"><Sparkles :size="22" /></span>
      <h1 class="text-2xl font-semibold tracking-tight">{{ t('auth.title') }}</h1><p class="muted mt-2 text-sm">{{ t('auth.subtitle') }}</p>
      <div class="mt-7 space-y-4"><FormField v-if="registerMode" :label="t('auth.name')" required><InputText v-model="name" required /></FormField><FormField :label="t('auth.email')" required><InputText v-model="email" type="email" required /></FormField><FormField :label="t('auth.password')" required><InputText v-model="password" type="password" required /></FormField></div>
      <AlertBanner :message="error" tone="error" />
      <Button class="mt-6 !w-full" type="submit" :loading="loading" :label="registerMode ? t('auth.register') : t('auth.login')" />
      <Button v-if="registrationEnabled" type="button" variant="link" block class="mt-4" @click="registerMode = !registerMode">{{ registerMode ? t('auth.switchLogin') : t('auth.switchRegister') }}</Button>
    </form>
  </div>
</template>
