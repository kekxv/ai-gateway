import {
  createRouter,
  createWebHistory,
  type Router,
  type RouterHistory,
  type RouteRecordRaw,
} from 'vue-router'

import { useAuthStore } from '@/stores/auth'

export { resolveLoginRedirect } from './redirect'

export const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('@/layouts/AdminLayout.vue'),
    children: [
      {
        path: '',
        name: 'dashboard',
        component: () => import('@/views/DashboardView.vue'),
        meta: { title: '控制台概览' },
      },
      {
        path: 'providers',
        name: 'providers',
        component: () => import('@/views/ProvidersView.vue'),
        meta: { title: '供应商管理' },
      },
      {
        path: 'models',
        name: 'models',
        component: () => import('@/views/ModelsView.vue'),
        meta: { title: '模型管理' },
      },
      {
        path: 'users',
        name: 'users',
        component: () => import('@/views/UsersView.vue'),
        meta: { title: '用户管理' },
      },
      {
        path: 'api-keys',
        name: 'api-keys',
        component: () => import('@/views/ApiKeysView.vue'),
        meta: { title: '接口密钥' },
      },
      {
        path: 'request-logs',
        name: 'request-logs',
        component: () => import('@/views/RequestLogsView.vue'),
        meta: { title: '请求日志' },
      },
      {
        path: 'security',
        name: 'security',
        component: () => import('@/views/FutureView.vue'),
        meta: { title: '安全设置' },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
  },
]

export function createAppRouter(
  history: RouterHistory = createWebHistory(import.meta.env.BASE_URL),
): Router {
  const router = createRouter({ history, routes })
  let restorePromise: Promise<void> | undefined

  router.beforeEach(async (to) => {
    const auth = useAuthStore()
    restorePromise ??= auth.restore()
    await restorePromise

    if (to.name === 'login' && auth.authenticated) return { name: 'dashboard' }
    if (to.meta.public === true) return true
    if (!auth.authenticated) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }
    return true
  })

  return router
}

export default createAppRouter()
