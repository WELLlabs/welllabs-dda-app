import { createApiClient, streamSSE } from '$lib/shared/api-client.js';

const API = '/api/diagnose';
const request = createApiClient(API);

function bboxQuery(bounds) {
	if (!bounds || bounds.length !== 4) return '';
	const q = bounds.map((v) => encodeURIComponent(v)).join(',');
	return `?bbox=${q}`;
}

export async function fetchProjects() {
	return request('/projects');
}

export async function fetchProject(id) {
	return request(`/projects/${id}`);
}

export async function createProject(name, lng, lat) {
	return request('/projects', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ name, lng, lat })
	});
}

export async function deleteProject(id) {
	await request(`/projects/${id}`, { method: 'DELETE' });
}

export async function fetchUserAccess(projectId) {
	const data = await request(`/projects/${projectId}/access/users`);
	return data.users ?? [];
}

export async function addUserAccess(projectId, email) {
	return request(`/projects/${projectId}/access/users`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ email })
	});
}

export async function removeUserAccess(projectId, userId) {
	await request(`/projects/${projectId}/access/users/${userId}`, { method: 'DELETE' });
}

export async function updateUserAccessRole(projectId, userId, role) {
	return request(`/projects/${projectId}/access/users/${userId}/role`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ role })
	});
}

export async function fetchOrgAccess(projectId) {
	const data = await request(`/projects/${projectId}/access/orgs`);
	return data.organizations ?? [];
}

export async function addOrgAccess(projectId, orgId) {
	return request(`/projects/${projectId}/access/orgs`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ org_id: orgId })
	});
}

export async function removeOrgAccess(projectId, orgId) {
	await request(`/projects/${projectId}/access/orgs/${orgId}`, { method: 'DELETE' });
}

export async function lookupWatershed(lng, lat) {
	return request('/watersheds/lookup', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ lng, lat })
	});
}

function layerQuery(bounds, projectId) {
	const params = new URLSearchParams();
	if (bounds && bounds.length === 4) {
		params.set('bbox', bounds.map(String).join(','));
	}
	if (projectId) {
		params.set('project_id', projectId);
	}
	const qs = params.toString();
	return qs ? `?${qs}` : '';
}

export async function fetchCogLayers(bounds, projectId) {
	return request(`/layers/cog${layerQuery(bounds, projectId)}`);
}

export async function fetchObservationZones(projectId) {
	return request(`/observation-zones?project_id=${encodeURIComponent(projectId)}`);
}

export async function createObservationZone(projectId, geometry, text, observations, questions, color) {
	return request('/observation-zones', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			project_id: projectId,
			geometry,
			text,
			observations,
			questions,
			color
		})
	});
}

export async function updateObservationZone(id, data) {
	return request(`/observation-zones/${id}`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(data)
	});
}

export async function deleteObservationZone(id) {
	await request(`/observation-zones/${id}`, { method: 'DELETE' });
}

export async function fetchFieldNotes(projectId) {
	return request(`/field-notes?project_id=${encodeURIComponent(projectId)}`);
}

export async function createFieldNote(
	projectId,
	geometry,
	title,
	text,
	photo,
	audio,
	hypothesisId = null
) {
	const form = new FormData();
	form.append('project_id', projectId);
	form.append('geometry', JSON.stringify(geometry));
	form.append('title', title);
	form.append('text', text);
	if (hypothesisId) form.append('hypothesis_id', hypothesisId);
	if (photo) form.append('photo', photo);
	if (audio) form.append('audio', audio);
	const res = await fetch(`${API}/field-notes`, { method: 'POST', body: form });
	if (!res.ok) throw new Error(await res.text());
	return res.json();
}

export async function updateFieldNote(id, data) {
	return request(`/field-notes/${id}`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(data)
	});
}

export async function deleteFieldNote(id) {
	await request(`/field-notes/${id}`, { method: 'DELETE' });
}

export async function fetchHypotheses(projectId) {
	const data = await request(`/hypotheses?project_id=${encodeURIComponent(projectId)}`);
	return data.hypotheses ?? [];
}

export async function createHypothesis(projectId, hypothesis, observationZoneIds) {
	return request('/hypotheses', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			project_id: projectId,
			hypothesis,
			observation_zone_ids: observationZoneIds
		})
	});
}

export async function updateHypothesis(id, data) {
	return request(`/hypotheses/${id}`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(data)
	});
}

export async function deleteHypothesis(id) {
	await request(`/hypotheses/${id}`, { method: 'DELETE' });
}

export function fieldNoteMediaUrl(photoPath) {
	if (!photoPath) return null;
	return `${API}/field-notes/media?key=${encodeURIComponent(photoPath)}`;
}

export function fieldNoteThumbnailUrl(photoPath, size = 128) {
	if (!photoPath) return null;
	return `${API}/field-notes/media/thumbnail?key=${encodeURIComponent(photoPath)}&size=${size}`;
}

export async function packageToQfield(projectId) {
	return request('/qfield/package', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ project_id: projectId })
	});
}

/**
 * Package to QField with SSE progress stream.
 * @param {string} projectId
 * @param {{ onProgress?: (percent: number, message: string, time?: string) => void, onDone?: (result: object) => void, onError?: (message: string) => void, signal?: AbortSignal }} handlers
 */
export async function packageToQfieldStream(projectId, handlers = {}) {
	const { signal, ...eventHandlers } = handlers;
	return streamSSE(
		`${API}/qfield/package/stream`,
		{
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				Accept: 'text/event-stream'
			},
			body: JSON.stringify({ project_id: projectId }),
			signal
		},
		eventHandlers
	);
}

export async function syncFromQfield(projectId) {
	return request('/qfield/sync', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ project_id: projectId })
	});
}

/**
 * Sync from QField with SSE progress stream.
 * @param {string} projectId
 * @param {{ onProgress?: (percent: number, message: string, time?: string) => void, onDone?: (result: object) => void, onError?: (message: string) => void, signal?: AbortSignal }} handlers
 */
export async function syncFromQfieldStream(projectId, handlers = {}) {
	const { signal, ...eventHandlers } = handlers;
	return streamSSE(
		`${API}/qfield/sync/stream`,
		{
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				Accept: 'text/event-stream'
			},
			body: JSON.stringify({ project_id: projectId }),
			signal
		},
		eventHandlers
	);
}

/** Rewrite Titiler URLs to use the Vite dev proxy. */
export function proxyTitilerUrl(url) {
	return url.replace(/^https?:\/\/[^/]+/, '/titiler');
}

export { bboxQuery };
