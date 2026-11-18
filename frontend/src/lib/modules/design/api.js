import { createApiClient } from '$lib/shared/api-client.js';
import { apiPath } from '$lib/shared/paths.js';

const request = createApiClient(apiPath('/design'));

// AOI resolution (map click, village, custom upload) reuses the Diagnose
// watershed endpoints so both modules pick places identically.
export {
	fetchWatershedPreviewContext,
	lookupWatershed,
	searchPlaces,
	watershedsFromGeometry,
	watershedsFromPoint
} from '$lib/modules/diagnose/api';

export async function fetchDesignProjects({ signal } = {}) {
	return request('/projects', { retries: 2, retryDelayMs: 600, ...(signal ? { signal } : {}) });
}

export async function fetchDesignProject(id, { signal } = {}) {
	return request(`/projects/${id}`, { retries: 1, retryDelayMs: 700, ...(signal ? { signal } : {}) });
}

/**
 * @param {{
 *   name: string,
 *   source: 'point' | 'village' | 'custom' | 'diagnosis',
 *   source_diagnosis_id?: string,
 *   geometry?: object,
 *   create_token?: string,
 *   aoi_name?: string,
 *   lng?: number,
 *   lat?: number
 * }} payload
 */
export async function createDesignProject(payload) {
	// No retries on POST — a gateway timeout after insert would create duplicates.
	return request('/projects', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(payload),
		retries: 0
	});
}

export async function deleteDesignProject(id) {
	await request(`/projects/${id}`, { method: 'DELETE' });
}

/** PD projects the user can access, for "import AOI from PD project". */
export async function fetchImportableAois({ signal } = {}) {
	const data = await request('/importable-aoi', { retries: 1, ...(signal ? { signal } : {}) });
	return data.projects ?? [];
}

export async function fetchImportableAoi(diagnosisId, { signal } = {}) {
	return request(`/importable-aoi/${diagnosisId}`, { ...(signal ? { signal } : {}) });
}

/** Ranked solutions (most feasible first) with suitability metrics for the project AOI. */
export async function fetchProjectSolutions(projectId, { signal } = {}) {
	return request(`/projects/${projectId}/solutions`, {
		retries: 1,
		retryDelayMs: 900,
		...(signal ? { signal } : {})
	});
}

/** Watershed-level stats for the AOI from the slope, LULC and drainage layers. */
export async function fetchProjectStats(projectId, { signal } = {}) {
	return request(`/projects/${projectId}/stats`, {
		retries: 1,
		retryDelayMs: 900,
		...(signal ? { signal } : {})
	});
}

/** FeatureCollection of suitable areas (polygons) or reaches (lines) for one solution. */
export async function fetchSolutionGeojson(projectId, solutionId, { signal } = {}) {
	return request(`/projects/${projectId}/solutions/${encodeURIComponent(solutionId)}/geojson`, {
		retries: 1,
		...(signal ? { signal } : {})
	});
}

/** How one map location measures against a solution's criteria (click popup). */
export async function inspectPoint(projectId, solutionId, lng, lat, { signal } = {}) {
	const params = new URLSearchParams({ solution_id: solutionId, lng: String(lng), lat: String(lat) });
	return request(`/projects/${projectId}/inspect?${params}`, { ...(signal ? { signal } : {}) });
}
