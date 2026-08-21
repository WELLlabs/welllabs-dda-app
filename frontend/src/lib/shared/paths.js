import { base, resolve } from '$app/paths';

/**
 * Prefix an app-root path with kit.paths.base (e.g. /login → /wst/login).
 * Leaves absolute/external URLs and already-prefixed paths unchanged.
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
	return `${resolve(/** @type {any} */ (normalized))}${suffix}`;
}
