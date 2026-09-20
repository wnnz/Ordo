<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ShieldCheck, UserCheck, UserX, Users } from 'lucide-vue-next'
import api from '@/api/client'
import AppShell from '@/components/AppShell.vue'
import AvatarInitial from '@/components/ui/AvatarInitial.vue'
import { useAuthStore, type User } from '@/stores/auth'
import Button from '@/volt/Button.vue'
import AlertBanner from '@/components/ui/AlertBanner.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'

type ManagedUser = User & { is_active: boolean; created_at: string }
const auth = useAuthStore()
const users = ref<ManagedUser[]>([])
const error = ref('')
async function load() { users.value = (await api.get('/admin/users')).data }
async function update(user: ManagedUser, changes: Partial<ManagedUser>) {
  error.value = ''
  try {
    const { data } = await api.patch(`/admin/users/${user.id}`, changes)
    Object.assign(user, data)
  } catch (cause: any) { error.value = cause.response?.data?.detail || String(cause) }
}
onMounted(load)
</script>

<template><AppShell><div class="mx-auto max-w-5xl px-7 py-5"><PageHeader :title="$t('admin.title')" :subtitle="$t('admin.subtitle')" /><AlertBanner :message="error" tone="error" /><div class="surface mt-5 overflow-hidden rounded-xl"><div v-for="user in users" :key="user.id" class="flex items-center gap-3 border-b border-[var(--border)] px-4 py-3 last:border-0"><AvatarInitial :name="user.display_name" /><div class="min-w-0"><div class="flex items-center gap-2 text-sm font-medium"><span class="truncate">{{ user.display_name }}</span><ShieldCheck v-if="user.is_platform_admin" :size="14" class="text-[var(--primary)]" /></div><div class="muted truncate text-xs">{{ user.email }}</div></div><StatusBadge class="ml-auto" :label="user.is_active ? $t('admin.active') : $t('admin.disabled')" :tone="user.is_active ? 'success' : 'danger'" /><Button v-if="user.is_platform_admin" variant="secondary" :disabled="user.id === auth.user?.id" @click="update(user, { is_platform_admin: false })"><UserX :size="15" />{{ $t('admin.revokeAdmin') }}</Button><Button v-else variant="secondary" @click="update(user, { is_platform_admin: true })"><UserCheck :size="15" />{{ $t('admin.makeAdmin') }}</Button><Button variant="ghost" :disabled="user.id === auth.user?.id" @click="update(user, { is_active: !user.is_active })">{{ user.is_active ? $t('admin.disable') : $t('admin.enable') }}</Button></div><EmptyState v-if="!users.length" :title="$t('common.empty')" compact><template #icon><Users :size="36" /></template></EmptyState></div></div></AppShell></template>
