import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import { networkInterfaces } from 'os'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import vueDevTools from 'vite-plugin-vue-devtools'

function getAllNetworkIPs() {
  const nets = networkInterfaces()
  const addresses = []

  for (const name of Object.keys(nets)) {
    if (name.toLowerCase().includes('docker') || name.toLowerCase().includes('vethernet')) {
      continue
    }
    for (const net of nets[name] ?? []) {
      if (net.family === 'IPv4' && !net.internal && isLocalIP(net.address)) {
        addresses.push(net.address)
      }
    }
  }
  return addresses
}

function isLocalIP(ip: string) {
  return (
    ip.startsWith('10.') ||
    ip.startsWith('192.168.') ||
    /^172\.(1[6-9]|2[0-9]|3[0-1])\./.test(ip)
  )
}

const isDockerMode = process.env.VITE_DOCKER_MODE?.toLowerCase() === "true";
const isHostMode = process.argv.includes('--host')
const networkIps = isDockerMode ? [] : (isHostMode ? getAllNetworkIPs() : [])

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueJsx(),
    //vueDevTools(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
  define: {
    __NETWORK_IPS__: JSON.stringify(networkIps)
  }
})
