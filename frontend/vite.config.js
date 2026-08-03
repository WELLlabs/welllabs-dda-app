import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	resolve: {
		conditions: ['browser']
	},
	test: {
		environment: 'jsdom',
		setupFiles: ['./src/test/setup.js'],
		globals: true
	},
	server: {
		proxy: {
			// /api is handled by src/routes/api/[...path]/+server.js (SvelteKit),
			// not Vite — keeping both causes inconsistent behaviour.
			'/titiler': {
				target: 'http://localhost:8000',
				rewrite: (path) => path.replace(/^\/titiler/, '')
			}
		}
	}
});
