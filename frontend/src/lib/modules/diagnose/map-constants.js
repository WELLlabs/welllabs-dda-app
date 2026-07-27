/** Brand accents for observation zones, field notes, and hypotheses. */
export const OBSERVATION_ZONE_COLOR = '#0d983b';
export const FIELD_NOTE_COLOR = '#d5b443';
export const HYPOTHESIS_COLOR = '#6366f1';

/** LULC class legend (matches API colormap). */
export const LULC_LEGEND = [
	{ value: 1, label: 'Tree cover', color: '#006400' },
	{ value: 2, label: 'Shrubland', color: '#FFBB22' },
	{ value: 3, label: 'Grassland', color: '#FF0000' },
	{ value: 4, label: 'Cropland', color: '#CCCCCC' },
	{ value: 5, label: 'Built-up', color: '#0077FF' },
	{ value: 6, label: 'Bare / sparse vegetation', color: '#88FF88' },
	{ value: 7, label: 'Snow and ice', color: '#AA5500' },
	{ value: 8, label: 'Water', color: '#FFFFFF' },
	{ value: 9, label: 'Wetland', color: '#999999' },
	{ value: 10, label: 'Mangroves', color: '#550088' },
	{ value: 11, label: 'Moss and lichen', color: '#88CCEE' },
	{ value: 12, label: 'Rangeland', color: '#117733' }
];

/** Observation zone fill colours (7 choices). */
export const ZONE_COLORS = [
	{ id: 'red', hex: '#ef4444', label: 'Red' },
	{ id: 'orange', hex: '#f97316', label: 'Orange' },
	{ id: 'amber', hex: '#eab308', label: 'Amber' },
	{ id: 'green', hex: '#0d983b', label: 'Green' },
	{ id: 'blue', hex: '#3b82f6', label: 'Blue' },
	{ id: 'violet', hex: '#a855f7', label: 'Violet' },
	{ id: 'pink', hex: '#ec4899', label: 'Pink' }
];

export const MAX_FIELD_NOTE_MEDIA_BYTES = 50 * 1024 * 1024;
