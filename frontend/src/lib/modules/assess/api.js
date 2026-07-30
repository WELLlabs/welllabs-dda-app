/** API client for the Assess module (ODK Central-backed monitoring data). */

import { createApiClient } from '$lib/shared/api-client.js';

const API = '/api/assess';
const request = createApiClient(API);

/** List assess projects synced into the platform DB. */
export async function fetchProjects() {
	return request('/projects');
}

/**
 * Import / refresh projects from ODK Central. This is the only way assess
 * projects come into being — it syncs ODK Central projects into the DB and
 * returns the freshly-synced rows.
 */
export async function importProjects() {
	return request('/odk/projects');
}

/** List the ODK forms belonging to a project. */
export async function fetchForms(projectId) {
	return request(`/projects/${encodeURIComponent(projectId)}/forms`);
}

/** List submissions (OData) for a given form within a project. */
export async function fetchSubmissions(projectId, xmlFormId) {
	return request(
		`/projects/${encodeURIComponent(projectId)}/forms/${encodeURIComponent(xmlFormId)}/submissions`
	);
}

/** Fetch a single submission by instance id. */
export async function fetchSubmission(projectId, xmlFormId, instanceId) {
	return request(
		`/projects/${encodeURIComponent(projectId)}/forms/${encodeURIComponent(
			xmlFormId
		)}/submissions/${encodeURIComponent(instanceId)}`
	);
}
