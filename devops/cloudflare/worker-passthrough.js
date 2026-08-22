/**
 * Safe Cloudflare Worker for ai.welllabs.org — forwards everything to origin.
 * Replace any broken Worker with this to fix error 1101 on POST /wst/api/*.
 *
 * Deploy: wrangler deploy
 * Route:  ai.welllabs.org/*
 */
export default {
	async fetch(request, env, ctx) {
		ctx.passThroughOnException();
		return fetch(request);
	}
};
