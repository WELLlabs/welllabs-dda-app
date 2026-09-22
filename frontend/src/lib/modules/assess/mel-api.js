/** API client for MEL plan design in the Assess module. */

import { createApiClient, parseErrorMessage } from '$lib/shared/api-client.js';
import { apiPath } from '$lib/shared/paths.js';

const request = createApiClient(apiPath('/assess/mel'));

async function throwIfNotOk(res) {
	if (!res.ok) throw new Error(await parseErrorMessage(res));
}

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

/** Update MEL project name / description. */
export async function updateMelProject(projectId, { name, description } = {}) {
	const body = {};
	if (name !== undefined) body.name = name;
	if (description !== undefined) body.description = description;
	return request(`/projects/${encodeURIComponent(projectId)}`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(body)
	});
}

/** Delete a MEL project (owner only). */
export async function deleteMelProject(projectId) {
	return request(`/projects/${encodeURIComponent(projectId)}`, { method: 'DELETE' });
}

/** Create a MEL plan bound to one catalog intervention. */
export async function createMelPlan(projectId, { name, interventionSlug, kind = 'plan' }) {
	return request(`/projects/${encodeURIComponent(projectId)}/plans`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			name,
			intervention_slug: interventionSlug,
			kind
		})
	});
}

/** List MEL plans under a project (optional kind filter). */
export async function fetchMelPlans(projectId, { kind } = {}) {
	const q = kind ? `?kind=${encodeURIComponent(kind)}` : '';
	return request(`/projects/${encodeURIComponent(projectId)}/plans${q}`);
}

/** Persist outcome selection / plan_json without publishing ODK. Optional rename. */
export async function saveMelPlan(
	projectId,
	planId,
	{ outcomeIds, planJson, name } = {}
) {
	const body = {};
	if (outcomeIds !== undefined) body.outcome_ids = outcomeIds;
	if (planJson !== undefined) body.plan_json = planJson;
	if (name !== undefined) body.name = name;
	return request(
		`/projects/${encodeURIComponent(projectId)}/plans/${encodeURIComponent(planId)}`,
		{
			method: 'PATCH',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(body)
		}
	);
}

export async function fetchMelAssets(projectId, planId) {
	return request(
		`/projects/${encodeURIComponent(projectId)}/plans/${encodeURIComponent(planId)}/assets`
	);
}

export async function createMelAsset(projectId, planId, { otAnswers, label = '' }) {
	return request(
		`/projects/${encodeURIComponent(projectId)}/plans/${encodeURIComponent(planId)}/assets`,
		{
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ ot_answers: otAnswers, label })
		}
	);
}

export async function updateMelAsset(projectId, planId, assetId, { otAnswers, label } = {}) {
	const body = {};
	if (otAnswers !== undefined) body.ot_answers = otAnswers;
	if (label !== undefined) body.label = label;
	return request(
		`/projects/${encodeURIComponent(projectId)}/plans/${encodeURIComponent(planId)}/assets/${encodeURIComponent(assetId)}`,
		{
			method: 'PATCH',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(body)
		}
	);
}

export async function deleteMelAsset(projectId, planId, assetId) {
	await request(
		`/projects/${encodeURIComponent(projectId)}/plans/${encodeURIComponent(planId)}/assets/${encodeURIComponent(assetId)}`,
		{ method: 'DELETE' }
	);
}

export async function fetchOneTimeQuestions(projectId, planId) {
	return request(
		`/projects/${encodeURIComponent(projectId)}/plans/${encodeURIComponent(planId)}/one-time-questions`
	);
}

export async function fetchCmQuestions(projectId, planId) {
	return request(
		`/projects/${encodeURIComponent(projectId)}/plans/${encodeURIComponent(planId)}/cm-questions`
	);
}

export async function fetchMappingPackages({ interventionSlug, projectId, planId, outcomeIds = [] }) {
	return request('/plans/mapping-packages', {
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

export async function fetchImplementationDashboard(projectId, planId) {
	return request(
		`/projects/${encodeURIComponent(projectId)}/plans/${encodeURIComponent(planId)}/dashboard`
	);
}

export async function fetchAssetDashboard(projectId, planId, assetId) {
	return request(
		`/projects/${encodeURIComponent(projectId)}/plans/${encodeURIComponent(planId)}/assets/${encodeURIComponent(assetId)}/dashboard`
	);
}

/** Download the MEL plan as a .docx */
export async function exportMelPlanDocx(projectId, planId) {
	const res = await fetch(
		apiPath(
			`/assess/mel/projects/${encodeURIComponent(projectId)}/plans/${encodeURIComponent(planId)}/export-docx`
		),
		{ method: 'GET', credentials: 'include' }
	);
	if (!res.ok) {
		throw new Error(await parseErrorMessage(res));
	}
	const blob = await res.blob();
	const disposition = res.headers.get('Content-Disposition') || '';
	const match = disposition.match(/filename="?([^"]+)"?/i);
	const filename = match?.[1] || 'mel-plan.docx';
	return { blob, filename };
}

/** Download all MEL plans in a project as one PDF (shared prose once). */
export async function exportMelProjectPdf(projectId) {
	const res = await fetch(
		apiPath(`/assess/mel/projects/${encodeURIComponent(projectId)}/export-pdf`),
		{ method: 'GET', credentials: 'include' }
	);
	await throwIfNotOk(res);
	const blob = await res.blob();
	const disposition = res.headers.get('Content-Disposition') || '';
	const match = disposition.match(/filename="?([^"]+)"?/i);
	const filename = match?.[1] || 'mel-project-plans.pdf';
	return { blob, filename };
}

/** Download all MEL plans in a project as one Word doc (shared prose once). */
export async function exportMelProjectDocx(projectId) {
	const res = await fetch(
		apiPath(`/assess/mel/projects/${encodeURIComponent(projectId)}/export-docx`),
		{ method: 'GET', credentials: 'include' }
	);
	await throwIfNotOk(res);
	const blob = await res.blob();
	const disposition = res.headers.get('Content-Disposition') || '';
	const match = disposition.match(/filename="?([^"]+)"?/i);
	const filename = match?.[1] || 'mel-project-plans.docx';
	return { blob, filename };
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

export async function fetchMelOrgAccess(projectId) {
	const data = await request(`/projects/${encodeURIComponent(projectId)}/access/orgs`);
	return data.organizations ?? [];
}

export async function addMelOrgAccess(projectId, orgId) {
	return request(`/projects/${encodeURIComponent(projectId)}/access/orgs`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ org_id: orgId })
	});
}

export async function removeMelOrgAccess(projectId, orgId) {
	return request(
		`/projects/${encodeURIComponent(projectId)}/access/orgs/${encodeURIComponent(orgId)}`,
		{ method: 'DELETE' }
	);
}

/** List interventions that have mapping-catalog outcomes and indicators. */
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

/** Filtered log-frame preview for selected outcomes. */
export async function fetchMelLogframe({ interventionSlug, outcomeIds, projectId, planId }) {
	return request('/plans/logframe', {
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

/** Download log-frame MEL plan as .docx (designer / preview flow). */
export async function exportMelPlanDocxFromSelection({
	interventionSlug,
	outcomeIds,
	projectId,
	planId
}) {
	const res = await fetch(apiPath('/assess/mel/plans/export-docx'), {
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
	await throwIfNotOk(res);
	const blob = await res.blob();
	const disposition = res.headers.get('Content-Disposition') || '';
	const match = disposition.match(/filename="?([^"]+)"?/i);
	const filename = match?.[1] || 'mel-plan.docx';
	return { blob, filename };
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
	const res = await fetch(apiPath('/assess/mel/plans/export-pdf'), {
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
	await throwIfNotOk(res);
	const blob = await res.blob();
	const disposition = res.headers.get('Content-Disposition') || '';
	const match = disposition.match(/filename="?([^"]+)"?/i);
	const filename = match?.[1] || 'mel-plan.pdf';
	return { blob, filename };
}
