import { describe, expect, it } from 'vitest';
import {
	ZONE_TEMPLATES,
	matchZoneTemplate,
	suggestedHypothesesForZones
} from './zone-templates.js';

describe('zone templates', () => {
	it('has four field suggestions', () => {
		expect(ZONE_TEMPLATES).toHaveLength(4);
		expect(ZONE_TEMPLATES.map((t) => t.hypothesis)).toEqual([
			'Ridge water scarcity',
			'Flooding / waterlogging',
			'Soil erosion',
			'High farm-water demand'
		]);
	});

	it('matches titles case-insensitively', () => {
		const tpl = matchZoneTemplate('High slope / ridge / dry upper area');
		expect(tpl?.id).toBe('ridge-water-scarcity');
		expect(tpl?.observations).toContain('Dry sources');
		expect(tpl?.questions).toContain('dries first');
	});

	it('suggests hypotheses for matching zones', () => {
		const suggestions = suggestedHypothesesForZones([
			{ text: 'Steep slope / dense drainage' },
			{ text: 'custom zone' },
			{ text: 'High cropping / second crop / extraction stress' }
		]);
		expect(suggestions.map((s) => s.id)).toEqual(['soil-erosion', 'high-farm-water-demand']);
	});
});
