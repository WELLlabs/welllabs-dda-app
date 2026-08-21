/** Generic slug helpers, reused by any module that routes items (projects, plans, etc.) by name. */

/** @param {string} name */
export function slugify(name) {
	return (
		String(name)
			.toLowerCase()
			.trim()
			.normalize('NFKD')
			.replace(/[\u0300-\u036f]/g, '')
			.replace(/[^a-z0-9\s-]/g, '')
			.replace(/[\s_]+/g, '-')
			.replace(/-+/g, '-')
			.replace(/^-|-$/g, '') || 'item'
	);
}

/**
 * Build a `${basePath}/{slug}` route for an item, disambiguating with a short id
 * suffix if multiple items share the same slug.
 * @param {string} basePath e.g. '/diagnose'
 * @param {{ id: string, name: string }} item
 * @param {Array<{ id: string, name: string }>} [items]
 */
export function itemPath(basePath, item, items = []) {
	const base = slugify(item.name);
	const collisions = items.filter((p) => slugify(p.name) === base);
	if (collisions.length > 1) {
		return `${basePath}/${base}-${item.id.slice(0, 8)}`;
	}
	return `${basePath}/${base}`;
}

/**
 * Resolve a slug (optionally suffixed with a short id) back to an item.
 * @param {Array<{ id: string, name: string, updated_at?: string }>} items
 * @param {string} slug
 */
export function findBySlug(items, slug) {
	if (!slug) return null;

	const suffixMatch = slug.match(/^(.+)-([0-9a-f]{8})$/i);
	if (suffixMatch) {
		const [, base, idPrefix] = suffixMatch;
		const hit = items.find(
			(p) => slugify(p.name) === base && p.id.toLowerCase().startsWith(idPrefix.toLowerCase())
		);
		if (hit) return hit;
	}

	const matches = items.filter((p) => slugify(p.name) === slug);
	if (matches.length === 1) return matches[0];
	if (matches.length > 1) {
		return matches.sort(
			(a, b) => new Date(b.updated_at ?? 0).getTime() - new Date(a.updated_at ?? 0).getTime()
		)[0];
	}
	return null;
}
