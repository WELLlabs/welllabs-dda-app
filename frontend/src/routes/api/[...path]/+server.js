/** Dev proxy: forward /api/* to the FastAPI backend.
 *
 * In development, all browser `/api/*` requests hit this SvelteKit catch-all
 * (Vite's `server.proxy` is intentionally unused for `/api` — see vite.config.js).
 * In production, put a reverse proxy (nginx, Caddy, or ALB) in front and route
 * `/api/*` directly to FastAPI so uploads never pass through Node.
 */

const API_BASE = process.env.API_URL || 'http://localhost:8080';

/** @param {import('@sveltejs/kit').RequestEvent} event */
async function proxy(event) {
	const { params, request, url } = event;
	const target = `${API_BASE}/api/${params.path}${url.search}`;

	const headers = new Headers(request.headers);
	headers.delete('host');
	headers.delete('connection');

	/** @type {RequestInit & { duplex?: string }} */
	const init = {
		method: request.method,
		headers
	};

	if (request.method !== 'GET' && request.method !== 'HEAD') {
		const contentType = request.headers.get('content-type') || '';
		// Stream large multipart uploads (field-note photo/audio). Buffer JSON and
		// other small bodies — Node undici often fails on streamed JSON POSTs
		// when Content-Length is present (login/register, etc.).
		if (contentType.includes('multipart/form-data') && request.body) {
			headers.delete('content-length');
			init.body = request.body;
			init.duplex = 'half';
		} else {
			init.body = await request.arrayBuffer();
		}
	}

	const res = await fetch(target, init);
	const outHeaders = new Headers(res.headers);
	outHeaders.delete('content-encoding');

	return new Response(res.body, {
		status: res.status,
		statusText: res.statusText,
		headers: outHeaders
	});
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const PUT = proxy;
export const DELETE = proxy;
