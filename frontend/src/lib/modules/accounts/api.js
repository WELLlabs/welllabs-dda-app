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

export async function login(email, password) {
	return request('/auth/login', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ email, password })
	});
}

export async function logout() {
	await request('/auth/logout', { method: 'POST' });
}

export async function me() {
	return request('/auth/me');
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
