import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
	addOrgAccess,
	addUserAccess,
	createProject,
	deleteProject,
	fetchOrgAccess,
	fetchProject,
	fetchProjects,
	fetchUserAccess,
	lookupWatershed,
	removeOrgAccess,
	removeUserAccess
} from '../modules/diagnose/api.js';

describe('diagnose api', () => {
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

	it('fetchProjects and fetchProject hit project endpoints', async () => {
		mockJson([{ id: 'p1' }]);
		await expect(fetchProjects()).resolves.toEqual([{ id: 'p1' }]);
		expect(fetch).toHaveBeenCalledWith('/api/diagnose/projects', undefined);

		mockJson({ id: 'p1', name: 'North' });
		await expect(fetchProject('p1')).resolves.toEqual({ id: 'p1', name: 'North' });
		expect(fetch).toHaveBeenCalledWith('/api/diagnose/projects/p1', undefined);
	});

	it('createProject posts name and coordinates', async () => {
		mockJson({ id: 'p1' });
		await createProject('North', 77.5, 12.9);
		expect(fetch).toHaveBeenCalledWith('/api/diagnose/projects', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ name: 'North', lng: 77.5, lat: 12.9 })
		});
	});

	it('deleteProject issues DELETE', async () => {
		fetch.mockResolvedValue({ ok: true, status: 204 });
		await deleteProject('p1');
		expect(fetch).toHaveBeenCalledWith('/api/diagnose/projects/p1', { method: 'DELETE' });
	});

	it('user access helpers read and mutate members', async () => {
		mockJson({ users: [{ id: 'u1' }] });
		await expect(fetchUserAccess('p1')).resolves.toEqual([{ id: 'u1' }]);

		mockJson({ id: 'u2' });
		await addUserAccess('p1', 'a@b.com');
		expect(fetch).toHaveBeenCalledWith('/api/diagnose/projects/p1/access/users', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ email: 'a@b.com' })
		});

		fetch.mockResolvedValue({ ok: true, status: 204 });
		await removeUserAccess('p1', 'u1');
		expect(fetch).toHaveBeenCalledWith('/api/diagnose/projects/p1/access/users/u1', {
			method: 'DELETE'
		});
	});

	it('org access helpers read and mutate org grants', async () => {
		mockJson({ organizations: [{ id: 'o1' }] });
		await expect(fetchOrgAccess('p1')).resolves.toEqual([{ id: 'o1' }]);

		mockJson({ id: 'grant1' });
		await addOrgAccess('p1', 'o1');
		expect(fetch).toHaveBeenCalledWith('/api/diagnose/projects/p1/access/orgs', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ org_id: 'o1' })
		});

		fetch.mockResolvedValue({ ok: true, status: 204 });
		await removeOrgAccess('p1', 'o1');
		expect(fetch).toHaveBeenCalledWith('/api/diagnose/projects/p1/access/orgs/o1', {
			method: 'DELETE'
		});
	});

	it('lookupWatershed posts coordinates', async () => {
		mockJson({ name: 'WS-1' });
		await lookupWatershed(77.1, 12.2);
		expect(fetch).toHaveBeenCalledWith('/api/diagnose/watersheds/lookup', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ lng: 77.1, lat: 12.2 })
		});
	});
});
