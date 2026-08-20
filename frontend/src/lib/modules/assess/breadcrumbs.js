import { itemPath } from '$lib/shared/slug.js';

/**
 * @typedef {{ label: string, href?: string }} Crumb
 */

/**
 * Build Assess module breadcrumb trail.
 *
 * @param {{
 *   projects?: any[],
 *   project?: any,
 *   plan?: any,
 *   form?: string,
 *   tail?: Crumb[]
 * }} opts
 * @returns {Crumb[]}
 */
export function assessCrumbs({ projects = [], project, plan, form, tail = [] }) {
	const crumbs = [{ label: 'Assess', href: '/assess' }];

	if (!project) {
		return tail.length ? [...crumbs, ...tail] : crumbs;
	}

	const slugBase = itemPath('/assess', project, projects);
	crumbs.push({
		label: project.name,
		href: plan || form || tail.length ? slugBase : undefined
	});

	if (plan) {
		const planBase = `${slugBase}/plans/${plan.id}`;
		if (form) {
			crumbs.push({ label: plan.name, href: planBase });
			crumbs.push({ label: form });
		} else if (tail.length) {
			crumbs.push({ label: plan.name, href: planBase });
			crumbs.push(...tail);
		} else {
			crumbs.push({ label: plan.name });
		}
		return crumbs;
	}

	return [...crumbs, ...tail];
}
