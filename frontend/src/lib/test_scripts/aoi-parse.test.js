import { describe, expect, it } from 'vitest';
import { extractPolygon } from '../modules/diagnose/aoi-parse.js';

describe('extractPolygon', () => {
	it('passes through Polygon', () => {
		const poly = {
			type: 'Polygon',
			coordinates: [
				[
					[0, 0],
					[1, 0],
					[1, 1],
					[0, 1],
					[0, 0]
				]
			]
		};
		expect(extractPolygon(poly)).toEqual(poly);
	});

	it('unwraps Feature', () => {
		const geometry = {
			type: 'Polygon',
			coordinates: [
				[
					[0, 0],
					[1, 0],
					[1, 1],
					[0, 0]
				]
			]
		};
		expect(extractPolygon({ type: 'Feature', properties: {}, geometry })).toEqual(geometry);
	});

	it('merges FeatureCollection polygons into MultiPolygon', () => {
		const fc = {
			type: 'FeatureCollection',
			features: [
				{
					type: 'Feature',
					properties: {},
					geometry: {
						type: 'Polygon',
						coordinates: [
							[
								[0, 0],
								[1, 0],
								[1, 1],
								[0, 0]
							]
						]
					}
				},
				{
					type: 'Feature',
					properties: {},
					geometry: {
						type: 'Polygon',
						coordinates: [
							[
								[2, 2],
								[3, 2],
								[3, 3],
								[2, 2]
							]
						]
					}
				}
			]
		};
		const out = extractPolygon(fc);
		expect(out?.type).toBe('MultiPolygon');
		expect(out?.coordinates).toHaveLength(2);
	});

	it('rejects Point', () => {
		expect(extractPolygon({ type: 'Point', coordinates: [1, 2] })).toBeNull();
	});
});
