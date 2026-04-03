import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/auth/LoginView.vue'),
    meta: { layout: 'auth', title: '登录' }
  },
  {
    path: '/',
    component: () => import('@/layouts/DefaultLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        redirect: '/dashboard'
      },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/DashboardView.vue'),
        meta: { title: '仪表板' }
      },
      {
        path: 'users',
        name: 'Users',
        component: () => import('@/views/users/UsersView.vue'),
        meta: { requiresAdmin: true, title: '用户管理' }
      },
      {
        path: 'providers',
        name: 'Providers',
        component: () => import('@/views/providers/ProvidersView.vue'),
        meta: { title: '提供商管理' }
      },
      {
        path: 'channels',
        name: 'Channels',
        component: () => import('@/views/channels/ChannelsView.vue'),
        meta: { title: '渠道管理' }
      },
      {
        path: 'models',
        name: 'Models',
        component: () => import('@/views/models/ModelsView.vue'),
        meta: { title: '模型管理' }
      },
      {
        path: 'keys',
        name: 'Keys',
        component: () => import('@/views/keys/KeysView.vue'),
        meta: { title: 'API Key管理' }
      },
      {
        path: 'logs',
        name: 'Logs',
        component: () => import('@/views/logs/LogsView.vue'),
        meta: { title: '日志查看' }
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('@/views/profile/ProfileView.vue'),
        meta: { title: '个人资料' }
      }
    ]
  },
  {
    path: '/401',
    name: 'Unauthorized',
    component: () => import('@/views/errors/UnauthorizedView.vue'),
    meta: { layout: 'auth' }
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/errors/NotFoundView.vue')
  }
]

export const router = createRouter({
  history: createWebHashHistory(),
  routes
})

// Router guards
router.beforeEach(async (to, _from, next) => {
  const authStore = useAuthStore()

  // Update document title
  if (to.meta.title) {
    document.title = `${to.meta.title} - AI Gateway`
  }

  // Routes requiring authentication
  if (to.meta.requiresAuth) {
    if (!authStore.isAuthenticated) {
      return next({ name: 'Login', query: { redirect: to.fullPath } })
    }

    // Ensure user info is loaded
    if (!authStore.user) {
      await authStore.fetchCurrentUser()
    }

    // Routes requiring admin permission
    if (to.meta.requiresAdmin && !authStore.isAdmin) {
      return next({ name: 'Unauthorized' })
    }
  }

  // Login page - redirect authenticated users to dashboard
  if (to.name === 'Login' && authStore.isAuthenticated) {
    return next({ name: 'Dashboard' })
  }

  next()
})