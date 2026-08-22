import { describe, expect, it } from 'vitest';
import { apiPath, resolveApiUrl } from '../shared/paths.js';

describe('resolveApiUrl', () => {
	it('normalizes legacy /api paths', () => {
		expect(resolveApiUrl('/api/diagnose/layers/cog')).toBe('/wst/backend/diagnose/layers/cog');
	});

	it('normalizes /backend paths without /wst', () => {
		expect(resolveApiUrl('/backend/diagnose/layers/vector/lulc/data?project_id=x')).toBe(
			'/wst/backend/diagnose/layers/vector/lulc/data?project_id=x'
		);
	});

	it('leaves correct /wst/backend paths unchanged', () => {
		const url = '/wst/backend/diagnose/layers/cog/lulc/tiles/WebMercatorQuad/{z}/{x}/{y}';
		expect(resolveApiUrl(url)).toBe(url);
	});

	it('matches apiPath for diagnose suffix', () => {
		expect(resolveApiUrl('/diagnose/projects')).toBe(apiPath('/diagnose/projects'));
	});
});
