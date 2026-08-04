import { createApiClient } from '$lib/shared/api-client.js';

const API = '/api/accounts';
const request = createApiClient(API);

export async function register(email, name, password) {
	return request('/auth/register', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ email, name, password })
	});
}

/** CookieTransport login expects OAuth2-style form fields (username = email). */
export async function login(email, password) {
	const body = new URLSearchParams();
	body.set('username', email);
	body.set('password', password);
	await request('/auth/login', {
		method: 'POST',
		headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
		body
	});
	return me();
}

export async function logout() {
	await request('/auth/logout', { method: 'POST' });
}

export async function me() {
	return request('/auth/me');
}

/** Update the signed-in user's profile (FastAPI Users /users/me). */
export async function updateMe(fields) {
	return request('/auth/users/me', {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(fields)
	});
}

export async function verifyEmail(token) {
	return request('/auth/verify', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ token })
	});
}

export async function requestVerifyEmail(email) {
	return request('/auth/request-verify-token', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ email })
	});
}

export async function forgotPassword(email) {
	return request('/auth/forgot-password', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ email })
	});
}

export async function resetPassword(token, password) {
	return request('/auth/reset-password', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ token, password })
	});
}

/** Start Google OAuth (sign-up or sign-in). Fetches authorize URL then redirects. */
export async function startGoogleAuth() {
	const res = await fetch(`${API}/auth/google/authorize`, { credentials: 'include' });
	if (!res.ok) {
		const text = await res.text();
		throw new Error(text || `Google authorize failed (${res.status})`);
	}
	const data = await res.json();
	if (!data?.authorization_url) {
		throw new Error('Google authorize did not return a URL');
	}
	window.location.href = data.authorization_url;
}

/** @deprecated Prefer startGoogleAuth() — authorize endpoint returns JSON, not a redirect. */
export function googleAuthorizeUrl() {
	return `${API}/auth/google/authorize`;
}

export async function lookupUserByEmail(email) {
	return request(`/users/lookup?email=${encodeURIComponent(email)}`);
}

export async function fetchOrgs() {
	const data = await request('/orgs');
	return data.organizations ?? [];
}

export async function createOrg(name) {
	return request('/orgs', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ name })
	});
}

export async function fetchOrgMembers(orgId) {
	const data = await request(`/orgs/${orgId}/members`);
	return data.members ?? [];
}

export async function addOrgMember(orgId, email) {
	return request(`/orgs/${orgId}/members`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ email })
	});
}

export async function removeOrgMember(orgId, userId) {
	await request(`/orgs/${orgId}/members/${userId}`, { method: 'DELETE' });
}

export async function deleteOrg(orgId) {
	await request(`/orgs/${orgId}`, { method: 'DELETE' });
}

export async function connectQFieldAccount(username, password) {
	return request('/qfield/connect', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ username, password })
	});
}

export async function getQFieldStatus() {
	return request('/qfield/status');
}

export async function disconnectQFieldAccount() {
	await request('/qfield/disconnect', { method: 'DELETE' });
}

export async function fetchOrgProjects(orgId) {
	const data = await request(`/orgs/${orgId}/projects`);
	return data.projects ?? [];
}

export async function updateMemberRole(orgId, userId, role) {
	return request(`/orgs/${orgId}/members/${userId}/role`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ role })
	});
}
