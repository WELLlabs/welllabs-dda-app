import adapter from '@sveltejs/adapter-node';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	compilerOptions: {
		// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
		runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true)
	},
	kit: {
		// Use adapter-node for self-hosted Node.js deployment on EC2.
		// Produces build/index.js which is run directly by the systemd service.
		adapter: adapter()
	}
};

export default config;
