import { error } from '@sveltejs/kit';
import { ABOUT_DOCS_NAV, aboutDocTitle } from '$lib/docs/about/nav.js';
import { extractAboutHeadings, renderAboutMarkdown } from '$lib/docs/renderAboutMarkdown.js';

const sources = import.meta.glob('$lib/docs/about/*.md', {
	query: '?raw',
	import: 'default',
	eager: true
});

/** @type {Record<string, string>} */
const bySlug = {};
for (const [path, raw] of Object.entries(sources)) {
	const file = path.split('/').pop() || '';
	const slug = file.replace(/\.md$/i, '');
	bySlug[slug] = String(raw);
}

/** @type {import('./$types').PageLoad} */
export function load({ params }) {
	const slug = params.slug;
	const allowed = new Set(ABOUT_DOCS_NAV.map((d) => d.slug));
	if (!allowed.has(slug) || !bySlug[slug]) {
		throw error(404, 'Documentation page not found');
	}
	const source = bySlug[slug];
	return {
		slug,
		title: aboutDocTitle(slug),
		html: renderAboutMarkdown(source),
		headings: extractAboutHeadings(source)
	};
}
