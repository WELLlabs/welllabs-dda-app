import { marked } from 'marked';
import { appPath } from '$lib/shared/paths.js';

/**
 * @param {string} text
 */
function slugify(text) {
	return String(text)
		.replace(/<[^>]+>/g, '')
		.trim()
		.toLowerCase()
		.replace(/&amp;/g, 'and')
		.replace(/[^a-z0-9]+/g, '-')
		.replace(/^-|-$/g, '');
}

const renderer = new marked.Renderer();

renderer.heading = function heading({ tokens, depth }) {
	const text = this.parser.parseInline(tokens);
	const id = slugify(text);
	return `<h${depth} id="${id}">${text}</h${depth}>\n`;
};

renderer.link = function link({ href, title, tokens }) {
	const text = this.parser.parseInline(tokens);
	let url = href || '';
	const titleAttr = title ? ` title="${title}"` : '';

	// Relative doc links: ./problem-diagnosis → /about/problem-diagnosis
	if (url.startsWith('./')) {
		url = appPath(`/about/${url.slice(2).replace(/\.md$/i, '')}`);
	} else if (url.startsWith('/docs/')) {
		url = appPath(url);
	}

	const external = /^(https?:|mailto:)/i.test(url);
	const rel = external ? ' rel="noopener noreferrer"' : '';
	const target = external || url.endsWith('.pdf') ? ' target="_blank"' : '';
	return `<a href="${url}"${titleAttr}${target}${rel}>${text}</a>`;
};

marked.setOptions({
	gfm: true,
	breaks: false
});

/**
 * Render about-docs markdown to HTML (base-aware links + heading anchors).
 * @param {string} source
 * @returns {string}
 */
export function renderAboutMarkdown(source) {
	return marked.parse(source, { renderer });
}

/**
 * Extract on-page TOC from markdown headings (## and deeper).
 * @param {string} source
 * @returns {{ id: string, text: string, depth: number }[]}
 */
export function extractAboutHeadings(source) {
	/** @type {{ id: string, text: string, depth: number }[]} */
	const out = [];
	for (const line of String(source).split('\n')) {
		const m = /^(#{2,4})\s+(.+)$/.exec(line.trim());
		if (!m) continue;
		const text = m[2].replace(/\[([^\]]+)\]\([^)]+\)/g, '$1').trim();
		out.push({ id: slugify(text), text, depth: m[1].length });
	}
	return out;
}
