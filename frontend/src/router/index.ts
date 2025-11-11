import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import LoginView from '@/views/LoginView.vue'
import { useSessionStore } from '@/stores/session.ts'
import { useConfigStore } from "@/stores/backendConfig.ts"
import { useRecorderStore } from '@/stores/recorder'
import { checkPlayerExists } from "@/api/playersAPI.ts";
import { fetchConfig } from "@/api/backendConfigAPI.ts";

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
    {
      path: '/players',
      name: 'players',
      component: () => import('../views/PlayersView.vue'),
    },
  ],
});

router.beforeEach(async (to, from) => {
  const sessionStore = useSessionStore();
  const isAuthenticated = !!sessionStore.currentPlayer;

  if (to.meta.requiresAuth) {
    if (!isAuthenticated) {
      return { name: "login" };
    }

    try {
      const res = await checkPlayerExists(sessionStore.currentPlayer!.id);
      if (!res.exists) {
        sessionStore.clearSession();
        return { name: "login" };
      }
    } catch (err) {
      // Treat API error as session invalidation
      console.error("Error validating player session:", err);
      sessionStore.clearSession();
      return { name: "login" };
    }
  }

  if (to.name === "login" && isAuthenticated) {
    return { name: "home" };
  }

  if (to.name === "config") {
    try {
      const config = await fetchConfig();
      const configStore = useConfigStore();
      configStore.setConfig(config);
    } catch (error) {
      console.error("Error loading config:", error);
    }
  }
});

export default router