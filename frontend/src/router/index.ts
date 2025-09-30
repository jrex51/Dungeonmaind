import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import LoginView from '@/views/LoginView.vue'
import { useSessionStore } from '@/stores/session.ts'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'login',
      component: LoginView,
    },
    {
      path: '/home',
      name: 'home',
      component: HomeView,
      meta: { requiresAuth: true },
    },
    {
      path: '/about',
      name: 'about',
      // route level code-splitting
      // this generates a separate chunk (About.[hash].js) for this route
      // which is lazy-loaded when the route is visited.
      component: () => import('../views/AboutView.vue'),
    },
    {
      path: '/config',
      name: 'config',
      component: () => import('../views/ConfigView.vue'),
    },
    {
      path: '/rulebook',
      name: 'rulebook',
      component: () => import('../views/RulebookView.vue'),
    },
  ],
});

router.beforeEach((to) => {
  const store = useSessionStore();
  if (to.meta.requiresAuth && !store.currentPlayer) {
    return { name: "login" };
  }
  if (to.name === "login" && store.currentPlayer) {
    return { name: "home" };
  }
});

export default router
