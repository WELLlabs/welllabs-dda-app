import { createApiClient, streamSSE } from '$lib/shared/api-client.js';
import { apiPath } from '$lib/shared/paths.js';

const API = apiPath('/diagnose');
const request = createApiClient(API);

/** Short-lived list cache so rapid project↔list navigation does not re-hit the API. */
let _projectsCache = /** @type {{ at: number, data: any } | null} */ (null);
const PROJECTS_CACHE_MS = 45_000;

export function invalidateProjectsCache() {
	_projectsCache = null;
}

function bboxQuery(bounds) {
	if (!bounds || bounds.length !== 4) return '';
	const q = bounds.map((v) => encodeURIComponent(v)).join(',');
	return `?bbox=${q}`;
}

export async function fetchProjects({ signal, fresh = false } = {}) {
	if (!fresh && _projectsCache && Date.now() - _projectsCache.at < PROJECTS_CACHE_MS) {
		return _projectsCache.data;
	}
	// Soft-retry: navigating back to the list must not fail on a single transient
	// Cloudflare/gateway blip while GIS work is draining.
	const data = await request('/projects', {
		retries: 2,
		retryDelayMs: 600,
		...(signal ? { signal } : {})
	});
	if (!signal?.aborted) {
		_projectsCache = { at: Date.now(), data };
	}
	return data;
}

export async function fetchProject(id, { signal } = {}) {
	return request(`/projects/${id}`, {
		retries: 1,
		retryDelayMs: 700,
		...(signal ? { signal } : {})
	});
}

export async function createProject(nameOrPayload, lng, lat) {
	const body =
		typeof nameOrPayload === 'object' && nameOrPayload !== null
			? nameOrPayload
			: { name: nameOrPayload, lng, lat };
	// No retries on POST — CF timeout after insert would create duplicates.
	invalidateProjectsCache();
	return request('/projects', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(body),
		retries: 0
	});
}

export async function deleteProject(id) {
	invalidateProjectsCache();
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

export async function lookupWatershed(lng, lat, { signal } = {}) {
	return request('/watersheds/lookup', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ lng, lat }),
		signal,
		retries: 1,
		retryDelayMs: 800
	});
}

export async function searchVillages(q, limit = 20, bounds = null) {
	const params = new URLSearchParams({ q, limit: String(limit) });
	if (bounds && bounds.length === 4) {
		params.set('bbox', bounds.map(String).join(','));
	}
	const data = await request(`/watersheds/villages/search?${params}`);
	return data.villages ?? [];
}

export async function fetchVillageStates() {
	const data = await request('/watersheds/villages/states');
	return data.states ?? [];
}

export async function fetchVillageDistricts(state) {
	const params = new URLSearchParams({ state });
	const data = await request(`/watersheds/villages/districts?${params}`);
	return data.districts ?? [];
}

export async function fetchVillagesByDistrict(state, district, q = '') {
	const params = new URLSearchParams({ state, district });
	if (q) params.set('q', q);
	const data = await request(`/watersheds/villages/by-district?${params}`);
	return data.villages ?? [];
}

export async function watershedsFromVillage({ villageId, geometry, signal } = {}) {
	return request('/watersheds/from-village', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			village_id: villageId ?? null,
			geometry: geometry ?? null
		}),
		signal,
		retries: 1,
		retryDelayMs: 800
	});
}

export async function watershedsFromGeometry(geometry, name = null) {
	return request('/watersheds/from-geometry', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ geometry, name })
	});
}

/** Rivers / basin / sub-basin / L7 overlays for the create-project map preview. */
export async function fetchWatershedPreviewContext(geometry, { signal, includeRivers = true } = {}) {
	return request('/watersheds/preview-context', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ geometry, include_rivers: includeRivers }),
		signal,
		retries: 2,
		retryDelayMs: 900
	});
}

/** Post-create Watershed layer: basin / sub-basin / L7 / L12 / rivers. */
export async function fetchWatershedHierarchy(projectId, { signal } = {}) {
	return request(
		`/layers/watershed/hierarchy?project_id=${encodeURIComponent(projectId)}`,
		// One retry max — stacking retries during reload saturates API workers.
		{ signal, retries: 1, retryDelayMs: 1200 }
	);
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
	return request(`/layers/cog${layerQuery(bounds, projectId)}`, {
		retries: 1,
		retryDelayMs: 700
	});
}

export async function fetchVectorLayers(projectId) {
	const q = projectId ? `?project_id=${encodeURIComponent(projectId)}` : '';
	return request(`/layers/vector${q}`, { retries: 1, retryDelayMs: 700 });
}

export async function fetchLayerAnalysis(layerId, projectId, { isCog = false, signal } = {}) {
	const base = isCog ? '/layers/cog' : '/layers/vector';
	return request(
		`${base}/${encodeURIComponent(layerId)}/analysis?project_id=${encodeURIComponent(projectId)}`,
		{ signal, retries: 1, retryDelayMs: 800 }
	);
}

export async function fetchBatchLayerAnalysis(projectId, { signal } = {}) {
	return request(`/layers/analysis/batch?project_id=${encodeURIComponent(projectId)}`, {
		signal,
		retries: 0
	});
}

/** Downsampled watershed DEM elevation grid for the 3D terrain viewer. */
export async function fetchDemMesh(projectId) {
	return request(`/layers/dem/mesh?project_id=${encodeURIComponent(projectId)}`);
}

/** Plotly surfacecolor grid for draping a layer on the DEM mesh. */
export async function fetchLayerDrapeGrid(layerId, projectId) {
	return request(
		`/layers/${encodeURIComponent(layerId)}/drape-grid?project_id=${encodeURIComponent(projectId)}`
	);
}

/** Blob URL for a layer drape PNG aligned to the DEM mesh. Caller must revoke. */
export async function fetchLayerDrapeUrl(layerId, projectId) {
	const res = await fetch(
		`${API}/layers/${encodeURIComponent(layerId)}/drape?project_id=${encodeURIComponent(projectId)}`,
		{ credentials: 'include' }
	);
	if (!res.ok) {
		const text = await res.text();
		let message = text || res.statusText;
		try {
			const json = JSON.parse(text);
			if (json.detail) message = typeof json.detail === 'string' ? json.detail : JSON.stringify(json.detail);
		} catch {
			/* keep raw */
		}
		throw new Error(message);
	}
	const blob = await res.blob();
	return URL.createObjectURL(blob);
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

/** Stream atlas PDF build progress, then download when done. */
export async function exportDiagnosisPdfStream(projectId, handlers = {}) {
	const { signal, ...eventHandlers } = handlers;
	return streamSSE(
		`${API}/projects/${encodeURIComponent(projectId)}/export-pdf/stream`,
		{
			method: 'POST',
			headers: {
				Accept: 'text/event-stream'
			},
			signal
		},
		eventHandlers
	);
}

/** Download a previously generated atlas PDF. */
export async function downloadDiagnosisPdf(projectId, filename, { signal } = {}) {
	const res = await fetch(
		`${API}/projects/${encodeURIComponent(projectId)}/export-pdf/download?file=${encodeURIComponent(filename)}`,
		{ method: 'GET', credentials: 'include', signal }
	);
	if (!res.ok) {
		const text = await res.text();
		let message = text || res.statusText;
		try {
			const json = JSON.parse(text);
			if (json.detail)
				message = typeof json.detail === 'string' ? json.detail : JSON.stringify(json.detail);
		} catch {
			/* keep raw */
		}
		throw new Error(message);
	}
	const blob = await res.blob();
	return { blob, filename };
}

/** @deprecated Prefer exportDiagnosisPdfStream */
export async function exportDiagnosisPdf(projectId, { signal } = {}) {
	const res = await fetch(`${API}/projects/${encodeURIComponent(projectId)}/export-pdf`, {
		method: 'POST',
		credentials: 'include',
		signal
	});
	if (!res.ok) {
		const text = await res.text();
		let message = text || res.statusText;
		try {
			const json = JSON.parse(text);
			if (json.detail)
				message = typeof json.detail === 'string' ? json.detail : JSON.stringify(json.detail);
		} catch {
			/* keep raw */
		}
		throw new Error(message);
	}
	const blob = await res.blob();
	const disposition = res.headers.get('Content-Disposition') || '';
	const match = disposition.match(/filename="?([^"]+)"?/i);
	const filename = match?.[1] || 'Diagnosis_Report.pdf';
	return { blob, filename };
}

/** Rewrite Titiler URLs to use the Vite dev proxy. */
export function proxyTitilerUrl(url) {
	return url.replace(/^https?:\/\/[^/]+/, '/titiler');
}

export { bboxQuery };
