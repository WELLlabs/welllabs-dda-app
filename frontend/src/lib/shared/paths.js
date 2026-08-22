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
	// API routes live at /api/* on the host root — never under kit.paths.base.
	if (path.startsWith('/api/')) {
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

/** Google OAuth callback — must hit FastAPI at /api/*, not /wst/api/*. */
export const GOOGLE_OAUTH_CALLBACK_PREFIX = '/api/accounts/auth/google/callback';

/** @param {string | null | undefined} path */
export function isGoogleOAuthCallback(path) {
	return typeof path === 'string' && path.startsWith(GOOGLE_OAUTH_CALLBACK_PREFIX);
}
