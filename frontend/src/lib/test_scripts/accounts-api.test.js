import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
	addOrgMember,
	createOrg,
	deleteOrg,
	fetchOrgMembers,
	fetchOrgs,
	login,
	logout,
	lookupUserByEmail,
	me,
	register,
	removeOrgMember
} from '../modules/accounts/api.js';

describe('accounts api', () => {
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

	it('register posts credentials to /auth/register', async () => {
		mockJson({ id: 'u1' });
		await register('a@b.com', 'Ada', 'secret');
		expect(fetch).toHaveBeenCalledWith('/api/accounts/auth/register', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ email: 'a@b.com', name: 'Ada', password: 'secret' })
		});
	});

	it('login posts email and password', async () => {
		mockJson({ id: 'u1' });
		await login('a@b.com', 'secret');
		expect(fetch).toHaveBeenCalledWith('/api/accounts/auth/login', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ email: 'a@b.com', password: 'secret' })
		});
	});

	it('logout posts to /auth/logout', async () => {
		fetch.mockResolvedValue({ ok: true, status: 204 });
		await logout();
		expect(fetch).toHaveBeenCalledWith('/api/accounts/auth/logout', { method: 'POST' });
	});

	it('me fetches the current user', async () => {
		mockJson({ id: 'u1', name: 'Ada' });
		await expect(me()).resolves.toEqual({ id: 'u1', name: 'Ada' });
		expect(fetch).toHaveBeenCalledWith('/api/accounts/auth/me', undefined);
	});

	it('lookupUserByEmail encodes the email query', async () => {
		mockJson({ id: 'u2' });
		await lookupUserByEmail('ada lovelace@example.com');
		expect(fetch).toHaveBeenCalledWith(
			'/api/accounts/users/lookup?email=ada%20lovelace%40example.com',
			undefined
		);
	});

	it('fetchOrgs returns organizations array (defaulting to empty)', async () => {
		mockJson({ organizations: [{ id: 'o1', name: 'WELL Labs' }] });
		await expect(fetchOrgs()).resolves.toEqual([{ id: 'o1', name: 'WELL Labs' }]);

		mockJson({});
		await expect(fetchOrgs()).resolves.toEqual([]);
	});

	it('createOrg posts the org name', async () => {
		mockJson({ id: 'o1', name: 'New Org' });
		await createOrg('New Org');
		expect(fetch).toHaveBeenCalledWith('/api/accounts/orgs', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ name: 'New Org' })
		});
	});

	it('fetchOrgMembers returns members array', async () => {
		mockJson({ members: [{ id: 'u1' }] });
		await expect(fetchOrgMembers('o1')).resolves.toEqual([{ id: 'u1' }]);
		expect(fetch).toHaveBeenCalledWith('/api/accounts/orgs/o1/members', undefined);
	});

	it('addOrgMember posts email to members endpoint', async () => {
		mockJson({ id: 'm1' });
		await addOrgMember('o1', 'a@b.com');
		expect(fetch).toHaveBeenCalledWith('/api/accounts/orgs/o1/members', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ email: 'a@b.com' })
		});
	});

	it('removeOrgMember and deleteOrg issue DELETE requests', async () => {
		fetch.mockResolvedValue({ ok: true, status: 204 });
		await removeOrgMember('o1', 'u1');
		expect(fetch).toHaveBeenCalledWith('/api/accounts/orgs/o1/members/u1', { method: 'DELETE' });

		await deleteOrg('o1');
		expect(fetch).toHaveBeenCalledWith('/api/accounts/orgs/o1', { method: 'DELETE' });
	});
});
