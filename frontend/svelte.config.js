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
			// Explicit assets path forces SvelteKit to emit absolute URLs for CSS
			// and JS chunks (e.g. "/wst/_app/...") in SSR HTML instead of the
			// relative "./_app/..." it generates when only `base` is set.  Relative
			// paths break when the page is served without a trailing slash because
			// the browser resolves "./" against "/" instead of "/wst/".
			assets: '/wst'
		}
	}
};

export default config;
