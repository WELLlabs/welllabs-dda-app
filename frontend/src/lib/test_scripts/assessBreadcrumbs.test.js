import { describe, expect, it } from 'vitest';
import { assessCrumbs } from '../modules/assess/breadcrumbs.js';

const project = { id: 'p1', name: 'Yavatmal', slug: 'yavatmal' };
const plan = { id: 'pl1', name: 'BME plan' };

describe('assessCrumbs', () => {
	it('shows Assess on the project picker', () => {
		expect(assessCrumbs({})).toEqual([{ label: 'Assess', href: '/assess' }]);
	});

	it('ends on the project name on project home', () => {
		expect(assessCrumbs({ projects: [project], project })).toEqual([
			{ label: 'Assess', href: '/assess' },
			{ label: 'Yavatmal' }
		]);
	});

	it('includes project and plan on a plan page', () => {
		expect(assessCrumbs({ projects: [project], project, plan })).toEqual([
			{ label: 'Assess', href: '/assess' },
			{ label: 'Yavatmal', href: '/wst/assess/yavatmal' },
			{ label: 'BME plan' }
		]);
	});

	it('includes form name on form explore', () => {
		expect(assessCrumbs({ projects: [project], project, plan, form: 'Survey A' })).toEqual([
			{ label: 'Assess', href: '/assess' },
			{ label: 'Yavatmal', href: '/wst/assess/yavatmal' },
			{ label: 'BME plan', href: '/wst/assess/yavatmal/plans/pl1' },
			{ label: 'Survey A' }
		]);
	});
});
