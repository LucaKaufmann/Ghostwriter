import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	kit: {
		adapter: adapter({
			// Build output goes to this folder
			pages: 'build',
			assets: 'build',
			fallback: 'index.html', // SPA mode - important for client-side routing
			precompress: false,
			strict: true
		}),
		// Allow all paths for SPA routing
		prerender: {
			entries: []
		}
	}
};

export default config;
