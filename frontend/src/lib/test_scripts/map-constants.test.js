import { describe, expect, it } from 'vitest';
import {
	FIELD_NOTE_COLOR,
	HYPOTHESIS_COLOR,
	MAX_FIELD_NOTE_MEDIA_BYTES,
	OBSERVATION_ZONE_COLOR,
	ZONE_COLORS
} from '../modules/diagnose/map-constants.js';

describe('map-constants', () => {
	it('exports brand accent colours', () => {
		expect(OBSERVATION_ZONE_COLOR).toBe('#0d983b');
		expect(FIELD_NOTE_COLOR).toBe('#d5b443');
		expect(HYPOTHESIS_COLOR).toBe('#6366f1');
	});

	it('defines seven zone colour choices with id, hex, and label', () => {
		expect(ZONE_COLORS).toHaveLength(7);
		for (const colour of ZONE_COLORS) {
			expect(colour).toEqual(
				expect.objectContaining({
					id: expect.any(String),
					hex: expect.stringMatching(/^#[0-9a-f]{6}$/i),
					label: expect.any(String)
				})
			);
		}
		expect(ZONE_COLORS.map((c) => c.id)).toEqual([
			'red',
			'orange',
			'amber',
			'green',
			'blue',
			'violet',
			'pink'
		]);
	});

	it('caps field-note media at 50 MB', () => {
		expect(MAX_FIELD_NOTE_MEDIA_BYTES).toBe(50 * 1024 * 1024);
	});
});
