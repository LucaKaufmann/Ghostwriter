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
				changeOrigin: true
			},
			// Root health endpoint for Docker healthcheck
			'/health': {
				target: 'http://localhost:8080',
				changeOrigin: true
			}
		}
	}
});
