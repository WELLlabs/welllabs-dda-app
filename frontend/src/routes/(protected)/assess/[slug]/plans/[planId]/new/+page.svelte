<script>
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { findBySlug, itemPath } from '$lib/shared/slug.js';
	import { assessCrumbs } from '$lib/modules/assess/breadcrumbs.js';
	import MelPlanDesigner from '$lib/modules/assess/components/MelPlanDesigner.svelte';
	import { fetchMelPlan, fetchMelProjects } from '$lib/modules/assess/mel-api';

	let slug = $derived(page.params.slug);
	let planId = $derived(page.params.planId);
	let odkFormsMode = $derived(page.url.searchParams.get('forms') === '1');
	let projects = $state([]);
	let project = $state(null);
	let plan = $state(null);
	let loading = $state(true);
	let error = $state('');

	const crumbs = $derived(
		project && plan
			? assessCrumbs({
					projects,
					project,
					plan,
					tail: [{ label: odkFormsMode ? 'Edit forms' : 'Design plan' }]
				})
			: []
	);

	onMount(load);

	async function load() {
		loading = true;
		error = '';
		try {
			const res = await fetchMelProjects();
			projects = res.projects ?? [];
			project = findBySlug(projects, slug);
			if (!project) {
				error = 'Project not found or you do not have access.';
				return;
			}
			plan = await fetchMelPlan(project.id, planId);
		} catch (err) {
			error = String(err);
		} finally {
			loading = false;
		}
	}

	function onBack() {
		if (project && plan) {
			goto(`${itemPath('/assess', project, projects)}/plans/${plan.id}`);
		} else if (project) {
			goto(itemPath('/assess', project, projects));
		} else {
			goto('/assess');
		}
	}
</script>

<svelte:head>
	<title>
		{odkFormsMode ? 'Edit ODK forms' : 'Design'} · {plan?.name || 'MEL plan'} · Assess
	</title>
</svelte:head>

<div class="min-h-screen bg-transparent">
	{#if loading}
		<p class="p-6 font-body text-brand-steel">Loading…</p>
	{:else if error || !project || !plan}
		<div class="mx-auto max-w-lg p-6">
			<p class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 font-body text-sm text-red-700">
				{error || 'Plan not found'}
			</p>
			<button type="button" class="action-btn mt-4" onclick={() => goto('/assess')}>
				Back to projects
			</button>
		</div>
	{:else}
		{#key `${plan.id}-${odkFormsMode}`}
			<MelPlanDesigner
				{onBack}
				{crumbs}
				projectId={project.id}
				planId={plan.id}
				projectName={project.name}
				planName={plan.name}
				lockedInterventionSlug={plan.intervention_slug}
				{odkFormsMode}
			/>
		{/key}
	{/if}
</div>
