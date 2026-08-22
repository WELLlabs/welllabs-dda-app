import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	compilerOptions: {
		runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true)
	},
	kit: {
		adapter: adapter(),
		paths: {
			base: '/wst',
			// Emit absolute /wst/... URLs in SSR HTML (not ./relative) so assets and
			// links work when the page URL omits the trailing slash.
			relative: false
		}
	}
};

export default config;
