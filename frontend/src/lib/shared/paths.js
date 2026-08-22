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

/**
 * Public API path under kit.paths.base (e.g. /wst/api/accounts).
 * @param {string} [path] — suffix after /api, e.g. "/accounts" or "/diagnose/projects"
 * @returns {string}
 */
export function apiPath(path = '') {
	const suffix =
		!path || path === '/api' || path === '/api/'
			? ''
			: path.startsWith('/api/')
				? path.slice(4)
				: path.startsWith('/')
					? path
					: `/${path}`;
	return `${appPath('/api')}${suffix}`;
}

/** Google OAuth callback — under /wst/api in production (same origin as the app). */
export const GOOGLE_OAUTH_CALLBACK_PREFIX = `${appPath('/api')}/accounts/auth/google/callback`;

/** @param {string | null | undefined} path */
export function isGoogleOAuthCallback(path) {
	if (typeof path !== 'string') return false;
	return (
		path.startsWith(GOOGLE_OAUTH_CALLBACK_PREFIX) ||
		path.startsWith('/api/accounts/auth/google/callback')
	);
}
