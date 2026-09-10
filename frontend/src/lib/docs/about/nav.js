/** @typedef {{ slug: string, title: string, shortTitle?: string }} AboutDocNavItem */

/** Left-nav order for About docs. */
/** @type {AboutDocNavItem[]} */
export const ABOUT_DOCS_NAV = [
	{ slug: 'overview', title: 'Overview' },
	{ slug: 'problem-diagnosis', title: 'Problem Diagnosis Framework', shortTitle: 'Problem Diagnosis' },
	{ slug: 'solution-design', title: 'Solution Design Framework', shortTitle: 'Solution Design' },
	{ slug: 'mel', title: 'Monitoring, Evaluation and Learning (MEL)', shortTitle: 'MEL Framework' }
];

export const ABOUT_DEFAULT_SLUG = 'overview';

/** @param {string} slug */
export function aboutDocTitle(slug) {
	return ABOUT_DOCS_NAV.find((d) => d.slug === slug)?.title ?? 'About';
}
