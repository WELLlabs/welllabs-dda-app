/** Dev proxy: forward /api/* to the FastAPI backend.
 *
 * In development, all browser `/api/*` requests hit this SvelteKit catch-all
 * (Vite's `server.proxy` is intentionally unused for `/api` — see vite.config.js).
 * In production, put a reverse proxy (nginx, Caddy, or ALB) in front and route
 * `/api/*` directly to FastAPI so uploads never pass through Node.
 */

import { redirect } from '@sveltejs/kit';

const API_BASE = process.env.API_URL || 'http://localhost:8080';

/**
 * Apply upstream Set-Cookie values onto the SvelteKit cookie jar so the browser
 * actually receives them (undici hides Set-Cookie on fetch Headers).
 * @param {import('@sveltejs/kit').Cookies} cookies
 * @param {string[]} rawCookies
 */
function applyUpstreamCookies(cookies, rawCookies) {
	for (const raw of rawCookies) {
		const parts = raw.split(';').map((p) => p.trim());
		const [nameValue, ...attrs] = parts;
		const eq = nameValue.indexOf('=');
		if (eq <= 0) continue;
		const name = nameValue.slice(0, eq).trim();
		const value = nameValue.slice(eq + 1).trim();

		/** @type {import('cookie').CookieSerializeOptions & { path: string }} */
		const opts = {
			path: '/',
			httpOnly: false,
			secure: false,
			sameSite: 'lax'
		};

		for (const attr of attrs) {
			const lower = attr.toLowerCase();
			if (lower.startsWith('max-age=')) {
				const n = Number(attr.slice(8));
				if (!Number.isNaN(n)) opts.maxAge = n;
			} else if (lower.startsWith('path=')) {
				opts.path = attr.slice(5) || '/';
			} else if (lower === 'httponly') {
				opts.httpOnly = true;
			} else if (lower === 'secure') {
				opts.secure = true;
			} else if (lower.startsWith('samesite=')) {
				const v = attr.slice(9).toLowerCase();
				if (v === 'lax' || v === 'strict' || v === 'none') opts.sameSite = v;
			}
		}

		cookies.set(name, value, opts);
	}
}

/** @param {import('@sveltejs/kit').RequestEvent} event */
async function proxy(event) {
	const { params, request, url, cookies } = event;
	const target = `${API_BASE}/api/${params.path}${url.search}`;

	const headers = new Headers(request.headers);
	headers.delete('host');
	headers.delete('connection');
	// So FastAPI/OAuth builds callback URLs on the Vite origin (5173/5174), not :8080
	headers.set('x-forwarded-host', url.host);
	headers.set('x-forwarded-proto', url.protocol.replace(':', '') || 'http');
	headers.set('x-forwarded-port', url.port || (url.protocol === 'https:' ? '443' : '80'));
	headers.set('forwarded', `host=${url.host};proto=${url.protocol.replace(':', '')}`);

	/** @type {RequestInit & { duplex?: string }} */
	const init = {
		method: request.method,
		headers,
		// Critical for OAuth/login: do not follow upstream 302s or Set-Cookie is lost
		redirect: 'manual'
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

	const setCookies =
		typeof res.headers.getSetCookie === 'function' ? res.headers.getSetCookie() : [];
	applyUpstreamCookies(cookies, setCookies);

	// OAuth / login redirects: cookies are already applied via cookies.set above
	if (res.status >= 300 && res.status < 400) {
		const location = res.headers.get('location');
		if (location) {
			redirect(/** @type {300 | 301 | 302 | 303 | 304 | 305 | 306 | 307 | 308} */ (res.status), location);
		}
	}

	const outHeaders = new Headers();
	for (const [key, value] of res.headers.entries()) {
		const lower = key.toLowerCase();
		if (
			lower === 'content-encoding' ||
			lower === 'set-cookie' ||
			lower === 'transfer-encoding' ||
			lower === 'location'
		) {
			continue;
		}
		outHeaders.append(key, value);
	}

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
