import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		proxy: {
			// Proxy API requests to FastAPI backend during development
			'/api': {
				target: 'http://localhost:8080',
				changeOrigin: true,
				rewrite: (path) => path.replace(/^\/api/, '')
			},
			// Also proxy health endpoint
			'/health': {
				target: 'http://localhost:8080',
				changeOrigin: true
			},
			// Proxy config endpoint
			'/config': {
				target: 'http://localhost:8080',
				changeOrigin: true
			}
		}
	}
});
