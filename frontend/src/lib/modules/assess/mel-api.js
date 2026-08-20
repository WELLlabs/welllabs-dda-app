/** API client for MEL plan design in the Assess module. */

import { createApiClient } from '$lib/shared/api-client.js';

const request = createApiClient('/api/assess/mel');

/** List MEL projects the current user owns or is a member of. */
export async function fetchMelProjects() {
	return request('/projects');
}

/** Create a MEL project (container for many one-intervention plans). */
export async function createMelProject({ name, description = '' }) {
	return request('/projects', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ name, description })
	});
}

/** Fetch one MEL project (requires membership). */
export async function fetchMelProject(projectId) {
	return request(`/projects/${encodeURIComponent(projectId)}`);
}

/** Delete a MEL project (owner only). */
export async function deleteMelProject(projectId) {
	return request(`/projects/${encodeURIComponent(projectId)}`, { method: 'DELETE' });
}

/** List MEL plans under a project. */
export async function fetchMelPlans(projectId) {
	return request(`/projects/${encodeURIComponent(projectId)}/plans`);
}

/** Create a MEL plan bound to one catalog intervention. */
export async function createMelPlan(projectId, { name, interventionSlug }) {
	return request(`/projects/${encodeURIComponent(projectId)}/plans`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			name,
			intervention_slug: interventionSlug
		})
	});
}

/** Fetch one MEL plan. */
export async function fetchMelPlan(projectId, planId) {
	return request(
		`/projects/${encodeURIComponent(projectId)}/plans/${encodeURIComponent(planId)}`
	);
}

/** Delete a MEL plan (and its forms via cascade). */
export async function deleteMelPlan(projectId, planId) {
	return request(
		`/projects/${encodeURIComponent(projectId)}/plans/${encodeURIComponent(planId)}`,
		{ method: 'DELETE' }
	);
}

/** List forms published under a MEL plan. */
export async function fetchMelPlanForms(projectId, planId) {
	return request(
		`/projects/${encodeURIComponent(projectId)}/plans/${encodeURIComponent(planId)}/forms`
	);
}

/** Normalized ODK submissions for a MEL form (from configured ODK_PROJECT_ID). */
export async function fetchMelFormSubmissions(projectId, planId, xmlFormId) {
	return request(
		`/projects/${encodeURIComponent(projectId)}/plans/${encodeURIComponent(planId)}/forms/${encodeURIComponent(xmlFormId)}/submissions`
	);
}

/** ODK Collect QR settings payload for a published MEL form. */
export async function fetchMelFormCollectQr(projectId, planId, xmlFormId) {
	return request(
		`/projects/${encodeURIComponent(projectId)}/plans/${encodeURIComponent(planId)}/forms/${encodeURIComponent(xmlFormId)}/collect-qr`
	);
}

/** List all forms under a MEL project (across plans). */
export async function fetchMelProjectForms(projectId) {
	return request(`/projects/${encodeURIComponent(projectId)}/forms`);
}

export async function fetchMelUserAccess(projectId) {
	return request(`/projects/${encodeURIComponent(projectId)}/access/users`);
}

export async function addMelUserAccess(projectId, email, role = 'member') {
	return request(`/projects/${encodeURIComponent(projectId)}/access/users`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ email, role })
	});
}

export async function updateMelUserAccessRole(projectId, userId, role) {
	return request(
		`/projects/${encodeURIComponent(projectId)}/access/users/${encodeURIComponent(userId)}/role`,
		{
			method: 'PATCH',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ role })
		}
	);
}

export async function removeMelUserAccess(projectId, userId) {
	return request(
		`/projects/${encodeURIComponent(projectId)}/access/users/${encodeURIComponent(userId)}`,
		{ method: 'DELETE' }
	);
}

/** List interventions from the outcomes/indicators catalog. */
export async function fetchMelInterventions() {
	return request('/interventions');
}

/** Full intervention detail including outcomes and indicators. */
export async function fetchMelIntervention(slug) {
	return request(`/interventions/${encodeURIComponent(slug)}`);
}

/** Preview selected outcomes and the indicators to collect. */
export async function previewMelPlan({ interventionSlug, outcomeIds, projectId, planId }) {
	return request('/plans/preview', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			intervention_slug: interventionSlug,
			outcome_ids: outcomeIds,
			project_id: projectId || null,
			plan_id: planId || null
		})
	});
}

/** Build Continuous / One-time / BME schedule packages for the plan. */
export async function fetchMelPackages({ interventionSlug, outcomeIds, projectId, planId }) {
	return request('/plans/packages', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			intervention_slug: interventionSlug,
			outcome_ids: outcomeIds,
			project_id: projectId || null,
			plan_id: planId || null
		})
	});
}

/** Publish one or more schedule packages as ODK forms under a MEL plan.

 * Pass ``xml_form_id`` on a package to publish a new version of an existing form.
 */
export async function createMelOdkForms({
	projectId,
	planId,
	interventionSlug,
	outcomeIds,
	packages
}) {
	return request('/plans/create-forms', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			project_id: projectId,
			plan_id: planId,
			intervention_slug: interventionSlug,
			outcome_ids: outcomeIds,
			packages: packages ?? []
		})
	});
}

/** Download the MEL plan as a PDF. */
export async function exportMelPlanPdf({ interventionSlug, outcomeIds, projectId, planId }) {
	const res = await fetch('/api/assess/mel/plans/export-pdf', {
		method: 'POST',
		credentials: 'include',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			intervention_slug: interventionSlug,
			outcome_ids: outcomeIds,
			project_id: projectId || null,
			plan_id: planId || null
		})
	});
	if (!res.ok) {
		const text = await res.text();
		let message = text || res.statusText;
		try {
			const json = JSON.parse(text);
			if (json.detail)
				message = typeof json.detail === 'string' ? json.detail : JSON.stringify(json.detail);
		} catch {
			// keep raw
		}
		throw new Error(message);
	}
	const blob = await res.blob();
	const disposition = res.headers.get('Content-Disposition') || '';
	const match = disposition.match(/filename="?([^"]+)"?/i);
	const filename = match?.[1] || 'mel-plan.pdf';
	return { blob, filename };
}
