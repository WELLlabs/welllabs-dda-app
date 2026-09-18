/**
 * Suggested observation-zone titles with observe/ask prompts and a linked hypothesis.
 * Used when drawing a new zone and when creating hypotheses linked to those zones.
 */

/** @typedef {{ id: string, title: string, observations: string, questions: string, hypothesis: string }} ZoneTemplate */

/** @type {ZoneTemplate[]} */
export const ZONE_TEMPLATES = [
	{
		id: 'ridge-water-scarcity',
		title: 'High slope / ridge / dry upper area',
		observations: 'Dry sources, shallow soil, runoff marks, failed recharge works',
		questions: 'Which source dries first, and who loses crop or drinking water first?',
		hypothesis: 'Ridge water scarcity'
	},
	{
		id: 'flooding-waterlogging',
		title: 'Low area / nala / canal / command zone',
		observations: 'Standing water, salinity, blocked drain, crop stress',
		questions: 'Where does water stand, for how long, and who is affected?',
		hypothesis: 'Flooding / waterlogging'
	},
	{
		id: 'soil-erosion',
		title: 'Steep slope / dense drainage',
		observations: 'Rills, gullies, washed bunds, sediment',
		questions: 'Where does soil move during storms, and what protection exists?',
		hypothesis: 'Soil erosion'
	},
	{
		id: 'high-farm-water-demand',
		title: 'High cropping / second crop / extraction stress',
		observations: 'Pumps, wells, water-intensive crops, dry tail-end plots',
		questions: 'What enables the second crop, who misses it, and has pumping increased?',
		hypothesis: 'High farm-water demand'
	}
];

/**
 * @param {string | null | undefined} title
 * @returns {ZoneTemplate | null}
 */
export function matchZoneTemplate(title) {
	const t = String(title || '')
		.trim()
		.toLowerCase();
	if (!t) return null;
	return (
		ZONE_TEMPLATES.find((tpl) => tpl.title.toLowerCase() === t) ||
		ZONE_TEMPLATES.find((tpl) => t.includes(tpl.title.toLowerCase())) ||
		null
	);
}

/**
 * @param {{ text?: string | null }[]} zones
 * @returns {ZoneTemplate[]}
 */
export function suggestedHypothesesForZones(zones) {
	/** @type {ZoneTemplate[]} */
	const out = [];
	const seen = new Set();
	for (const zone of zones || []) {
		const tpl = matchZoneTemplate(zone?.text);
		if (tpl && !seen.has(tpl.id)) {
			seen.add(tpl.id);
			out.push(tpl);
		}
	}
	return out;
}
