import { base } from '$app/paths';

/**
 * Prefix an app-root path with kit.paths.base (e.g. /login → /wst/login).
 * Leaves absolute/external URLs and already-prefixed paths unchanged.
 *
 * Always returns an absolute path (never ./relative) so links and assets work
 * even when the page URL omits the trailing slash (/wst vs /wst/).
 *
 * @param {string} path
 * @returns {string}
 */
export function appPath(path) {
	if (path == null || path === '') return path;
	if (/^(https?:|mailto:|tel:)/i.test(path) || path.startsWith('#') || path.startsWith('//')) {
		return path;
	}
	if (base && (path === base || path.startsWith(`${base}/`))) {
		return path;
	}

	const qIndex = path.indexOf('?');
	const hashIndex = path.indexOf('#');
	let cut = path.length;
	if (qIndex >= 0) cut = Math.min(cut, qIndex);
	if (hashIndex >= 0) cut = Math.min(cut, hashIndex);

	const pathname = path.slice(0, cut) || '/';
	const suffix = path.slice(cut);
	const normalized = pathname.startsWith('/') ? pathname : `/${pathname}`;
	const prefix = base || '';
	return `${prefix}${normalized === '/' ? '' : normalized}${suffix}`;
}

/** Browser API segment under kit.paths.base — /backend not /api (Cloudflare Worker crashes POST on /wst/api/*). */
const API_SEGMENT = '/backend';

/**
 * Public API path under kit.paths.base (e.g. /wst/backend/accounts).
 * @param {string} [path] — suffix after the API segment, e.g. "/accounts"
 * @returns {string}
 */
export function apiPath(path = '') {
	const suffix =
		!path || path === API_SEGMENT || path === `${API_SEGMENT}/`
			? ''
			: path.startsWith(`${API_SEGMENT}/`)
				? path.slice(API_SEGMENT.length)
				: path.startsWith('/api/')
					? path.slice(4)
					: path.startsWith('/')
						? path
						: `/${path}`;
	return `${appPath(API_SEGMENT)}${suffix}`;
}

/** Google OAuth callback — under /wst/backend (same origin as the app). */
export const GOOGLE_OAUTH_CALLBACK_PREFIX = `${appPath(API_SEGMENT)}/accounts/auth/google/callback`;

/** @param {string | null | undefined} path */
export function isGoogleOAuthCallback(path) {
	if (typeof path !== 'string') return false;
	return (
		path.startsWith(GOOGLE_OAUTH_CALLBACK_PREFIX) ||
		path.includes('/accounts/auth/google/callback')
	);
}

/**
 * Normalize API URLs from the backend (may be /api/*, /backend/*, or /wst/backend/*).
 * @param {string | null | undefined} url
 * @returns {string}
 */
export function resolveApiUrl(url) {
	if (url == null || url === '') return url;
	if (/^(https?:|blob:|data:)/i.test(url)) return url;

	let path = url;
	if (base && path.startsWith(`${base}/backend/`)) return path;
	if (path.startsWith('/wst/backend/')) return path;

	if (path.startsWith('/api/')) path = path.slice(4);
	else if (path.startsWith('/backend/')) path = path.slice('/backend'.length);

	return apiPath(path.startsWith('/') ? path : `/${path}`);
}
