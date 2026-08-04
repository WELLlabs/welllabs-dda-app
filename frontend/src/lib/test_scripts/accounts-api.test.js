import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
	addOrgMember,
	createOrg,
	deleteOrg,
	fetchOrgMembers,
	fetchOrgs,
	forgotPassword,
	login,
	logout,
	lookupUserByEmail,
	me,
	register,
	removeOrgMember,
	requestVerifyEmail,
	resetPassword,
	startGoogleAuth,
	updateMe,
	verifyEmail
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
			credentials: 'include',
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ email: 'a@b.com', name: 'Ada', password: 'secret' })
		});
	});

	it('login posts form-urlencoded credentials then loads /me', async () => {
		fetch
			.mockResolvedValueOnce({
				ok: true,
				status: 204,
				statusText: 'No Content',
				text: async () => ''
			})
			.mockResolvedValueOnce({
				ok: true,
				status: 200,
				statusText: 'OK',
				json: async () => ({ id: 'u1', email: 'a@b.com' }),
				text: async () => JSON.stringify({ id: 'u1', email: 'a@b.com' })
			});
		await expect(login('a@b.com', 'secret')).resolves.toEqual({ id: 'u1', email: 'a@b.com' });
		expect(fetch).toHaveBeenNthCalledWith(1, '/api/accounts/auth/login', {
			credentials: 'include',
			method: 'POST',
			headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
			body: expect.any(URLSearchParams)
		});
		const body = fetch.mock.calls[0][1].body;
		expect(body.get('username')).toBe('a@b.com');
		expect(body.get('password')).toBe('secret');
		expect(fetch).toHaveBeenNthCalledWith(2, '/api/accounts/auth/me', { credentials: 'include' });
	});

	it('logout posts to /auth/logout', async () => {
		fetch.mockResolvedValue({ ok: true, status: 204 });
		await logout();
		expect(fetch).toHaveBeenCalledWith('/api/accounts/auth/logout', {
			credentials: 'include',
			method: 'POST'
		});
	});

	it('me fetches the current user', async () => {
		mockJson({ id: 'u1', name: 'Ada' });
		await expect(me()).resolves.toEqual({ id: 'u1', name: 'Ada' });
		expect(fetch).toHaveBeenCalledWith('/api/accounts/auth/me', { credentials: 'include' });
	});

	it('updateMe patches /auth/users/me', async () => {
		mockJson({ id: 'u1', name: 'Ada Lovelace' });
		await expect(updateMe({ name: 'Ada Lovelace' })).resolves.toEqual({
			id: 'u1',
			name: 'Ada Lovelace'
		});
		expect(fetch).toHaveBeenCalledWith('/api/accounts/auth/users/me', {
			credentials: 'include',
			method: 'PATCH',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ name: 'Ada Lovelace' })
		});
	});

	it('verify / request-verify / forgot / reset hit auth endpoints', async () => {
		mockJson({});
		await verifyEmail('tok');
		expect(fetch).toHaveBeenCalledWith('/api/accounts/auth/verify', {
			credentials: 'include',
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ token: 'tok' })
		});

		mockJson({});
		await requestVerifyEmail('a@b.com');
		expect(fetch).toHaveBeenCalledWith('/api/accounts/auth/request-verify-token', {
			credentials: 'include',
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ email: 'a@b.com' })
		});

		mockJson({});
		await forgotPassword('a@b.com');
		expect(fetch).toHaveBeenCalledWith('/api/accounts/auth/forgot-password', {
			credentials: 'include',
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ email: 'a@b.com' })
		});

		mockJson({});
		await resetPassword('tok', 'password123');
		expect(fetch).toHaveBeenCalledWith('/api/accounts/auth/reset-password', {
			credentials: 'include',
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ token: 'tok', password: 'password123' })
		});
	});

	it('startGoogleAuth redirects to authorization_url', async () => {
		const hrefSetter = vi.fn();
		vi.stubGlobal('window', {
			location: {
				get href() {
					return '';
				},
				set href(v) {
					hrefSetter(v);
				}
			}
		});
		mockJson({ authorization_url: 'https://accounts.google.com/o/oauth2/v2/auth?x=1' });
		await startGoogleAuth();
		expect(fetch).toHaveBeenCalledWith('/api/accounts/auth/google/authorize', {
			credentials: 'include'
		});
		expect(hrefSetter).toHaveBeenCalledWith('https://accounts.google.com/o/oauth2/v2/auth?x=1');
	});

	it('lookupUserByEmail encodes the email query', async () => {
		mockJson({ id: 'u2' });
		await lookupUserByEmail('ada lovelace@example.com');
		expect(fetch).toHaveBeenCalledWith(
			'/api/accounts/users/lookup?email=ada%20lovelace%40example.com',
			{ credentials: 'include' }
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
			credentials: 'include',
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ name: 'New Org' })
		});
	});

	it('fetchOrgMembers returns members array', async () => {
		mockJson({ members: [{ id: 'u1' }] });
		await expect(fetchOrgMembers('o1')).resolves.toEqual([{ id: 'u1' }]);
		expect(fetch).toHaveBeenCalledWith('/api/accounts/orgs/o1/members', {
			credentials: 'include'
		});
	});

	it('addOrgMember posts email to members endpoint', async () => {
		mockJson({ id: 'm1' });
		await addOrgMember('o1', 'a@b.com');
		expect(fetch).toHaveBeenCalledWith('/api/accounts/orgs/o1/members', {
			credentials: 'include',
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ email: 'a@b.com' })
		});
	});

	it('removeOrgMember and deleteOrg issue DELETE requests', async () => {
		fetch.mockResolvedValue({ ok: true, status: 204 });
		await removeOrgMember('o1', 'u1');
		expect(fetch).toHaveBeenCalledWith('/api/accounts/orgs/o1/members/u1', {
			credentials: 'include',
			method: 'DELETE'
		});

		await deleteOrg('o1');
		expect(fetch).toHaveBeenCalledWith('/api/accounts/orgs/o1', {
			credentials: 'include',
			method: 'DELETE'
		});
	});
});
