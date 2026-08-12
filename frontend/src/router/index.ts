import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { safeLocalRedirect } from '@/utils/navigation'
const AdminUsersPage = () => import('@/pages/AdminUsersPage.vue')
const LoginPage = () => import('@/pages/LoginPage.vue')
const MembersPage = () => import('@/pages/MembersPage.vue')
const ModelsPage = () => import('@/pages/ModelsPage.vue')
const NewWorkspacePage = () => import('@/pages/NewWorkspacePage.vue')
const PublicAppPage = () => import('@/pages/PublicAppPage.vue')
const ScriptsPage = () => import('@/pages/ScriptsPage.vue')
const SettingsPage = () => import('@/pages/SettingsPage.vue')
const SystemSettingsPage = () => import('@/pages/SystemSettingsPage.vue')
const StudioPage = () => import('@/pages/StudioPage.vue')
const WorkflowDesignerPage = () => import('@/pages/WorkflowDesignerPage.vue')

const router = createRouter({ history: createWebHistory(), routes: [
  { path: '/login', component: LoginPage, meta: { public: true } },
  { path: '/apps/:slug', component: PublicAppPage, meta: { public: true } },
  { path: '/workspaces/new', component: NewWorkspacePage },
  { path: '/admin/users', component: AdminUsersPage, meta: { platformAdmin: true } },
  { path: '/admin/settings', component: SystemSettingsPage, meta: { platformAdmin: true } },
  { path: '/w/:workspaceId/studio', component: StudioPage },
  { path: '/w/:workspaceId/scripts', component: ScriptsPage },
  { path: '/w/:workspaceId/workflows/:workflowId', component: WorkflowDesignerPage },
  { path: '/w/:workspaceId/members', component: MembersPage },
  { path: '/w/:workspaceId/knowledge', redirect: to => `/w/${String(to.params.workspaceId)}/studio` },
  { path: '/w/:workspaceId/models', component: ModelsPage },
  { path: '/w/:workspaceId/settings', component: SettingsPage },
  { path: '/', redirect: () => {
    const token = localStorage.getItem('access_token')
    const id = localStorage.getItem('workspace_id')
    return token && id ? `/w/${id}/studio` : '/login'
  } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
] })
let sessionHydrated = false
router.beforeEach(async to => {
  const token = localStorage.getItem('access_token')
  const workspaceId = localStorage.getItem('workspace_id')
  if (!to.meta.public && !token) return { path: '/login', query: { redirect: to.fullPath } }
  const auth = useAuthStore()
  if (token && !sessionHydrated) {
    try { await auth.refresh() }
    catch {
      auth.logout()
      if (!to.meta.public) return { path: '/login', query: { redirect: to.fullPath } }
    }
    finally { sessionHydrated = true }
  }
  if (to.meta.platformAdmin) {
    if (!auth.user?.is_platform_admin) return '/'
  }
  const returnTo = to.path === '/login' ? safeLocalRedirect(to.query.redirect) : null
  if (to.path === '/login' && token && returnTo) return returnTo
  if (to.path === '/login' && token && workspaceId) return `/w/${workspaceId}/studio`
  if (to.path === '/login' && token && !workspaceId) {
    localStorage.removeItem('access_token')
    localStorage.removeItem('user')
  }
})
export default router
