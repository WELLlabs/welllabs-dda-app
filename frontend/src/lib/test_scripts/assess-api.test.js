import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
	fetchForms,
	fetchProjectReport,
	fetchProjects,
	fetchSubmission,
	fetchSubmissions,
	importProjects
} from '../modules/assess/api.js';

describe('assess api', () => {
	beforeEach(() => {
		vi.stubGlobal('fetch', vi.fn());
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		vi.restoreAllMocks();
	});

	function mockJson(data, status = 200) {
		fetch.mockResolvedValue({
			ok: status >= 200 && status < 300,
			status,
			statusText: 'OK',
			json: async () => data,
			text: async () => JSON.stringify(data)
		});
	}

	it('fetchProjects lists assess projects', async () => {
		mockJson([{ id: 'p1' }]);
		await expect(fetchProjects()).resolves.toEqual([{ id: 'p1' }]);
		expect(fetch).toHaveBeenCalledWith('/api/assess/projects', { credentials: 'include' });
	});

	it('importProjects hits the ODK projects endpoint', async () => {
		mockJson({ imported: 2 });
		await expect(importProjects()).resolves.toEqual({ imported: 2 });
		expect(fetch).toHaveBeenCalledWith('/api/assess/odk/projects', { credentials: 'include' });
	});

	it('fetchProjectReport encodes the project id', async () => {
		mockJson({ configured: false });
		await fetchProjectReport('proj/with spaces');
		expect(fetch).toHaveBeenCalledWith(
			'/api/assess/projects/proj%2Fwith%20spaces/reports',
			{ credentials: 'include' }
		);
	});

	it('fetchForms lists forms for a project', async () => {
		mockJson([{ xmlFormId: 'form-a' }]);
		await expect(fetchForms('p1')).resolves.toEqual([{ xmlFormId: 'form-a' }]);
		expect(fetch).toHaveBeenCalledWith('/api/assess/projects/p1/forms', { credentials: 'include' });
	});

	it('fetchSubmissions encodes project and form ids', async () => {
		mockJson([]);
		await fetchSubmissions('p1', 'form/a');
		expect(fetch).toHaveBeenCalledWith(
			'/api/assess/projects/p1/forms/form%2Fa/submissions',
			{ credentials: 'include' }
		);
	});

	it('fetchSubmission encodes instance id', async () => {
		mockJson({ instanceId: 'i1' });
		await fetchSubmission('p1', 'form-a', 'uuid:abc');
		expect(fetch).toHaveBeenCalledWith(
			'/api/assess/projects/p1/forms/form-a/submissions/uuid%3Aabc',
			{ credentials: 'include' }
		);
	});
});
