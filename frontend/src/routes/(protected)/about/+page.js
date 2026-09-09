import { redirect } from '@sveltejs/kit';
import { ABOUT_DEFAULT_SLUG } from '$lib/docs/about/nav.js';
import { appPath } from '$lib/shared/paths.js';

/** @type {import('./$types').PageLoad} */
export function load() {
	throw redirect(307, appPath(`/about/${ABOUT_DEFAULT_SLUG}`));
}
