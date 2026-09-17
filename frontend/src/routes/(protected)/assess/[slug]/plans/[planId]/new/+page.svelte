<script>
	import { appPath } from '$lib/shared/paths.js';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { findBySlug, itemPath } from '$lib/shared/slug.js';
	import { assessCrumbs } from '$lib/modules/assess/breadcrumbs.js';
	import MelPlanWizard from '$lib/modules/assess/components/MelPlanWizard.svelte';
	import MelImplementationWizard from '$lib/modules/assess/components/MelImplementationWizard.svelte';
	import { fetchMelPlan, fetchMelProjects } from '$lib/modules/assess/mel-api';

	let slug = $derived(page.params.slug);
	let planId = $derived(page.params.planId);
	let startAtAssets = $derived(page.url.searchParams.get('assets') === '1');
	let startAtForms = $derived(page.url.searchParams.get('forms') === '1');
	let startNewAsset = $derived(page.url.searchParams.get('new') === '1');
	let editAssetId = $derived(page.url.searchParams.get('asset') || '');
	let planStartStep = $derived.by(() => {
		const raw = page.url.searchParams.get('step');
		if (raw === 'assets' || raw === '1') return 1;
		if (raw === 'cm' || raw === '2') return 2;
		if (raw === 'export' || raw === '3') return 3;
		return 0;
	});
	let projects = $state([]);
	let project = $state(null);
	let plan = $state(null);
	let loading = $state(true);
	let error = $state('');

	const isImpl = $derived((plan?.kind || 'plan') === 'implementation');
	const crumbs = $derived(
		project && plan
			? assessCrumbs({
					projects,
					project,
					plan,
					tail: [
						{
							label: startNewAsset
								? 'Add asset'
								: editAssetId
									? 'Edit asset'
									: startAtAssets
										? 'Assets'
										: isImpl
											? 'Edit forms'
											: 'Design plan'
						}
					]
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
			goto(appPath('/assess'));
		}
	}
</script>

<svelte:head>
	<title>
		{isImpl ? 'Intervention' : 'Plan'} · {plan?.name || 'MEL'} · Assess
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
			<button type="button" class="action-btn mt-4" onclick={() => goto(appPath('/assess'))}>
				Back to Assess
			</button>
		</div>
	{:else if isImpl}
		{#key `${plan.id}:${editAssetId}:${startNewAsset}:${startAtForms}`}
			<MelImplementationWizard
				{onBack}
				{crumbs}
				projectId={project.id}
				planId={plan.id}
				projectName={project.name}
				planName={plan.name}
				interventionSlug={plan.intervention_slug}
				initialOutcomeIds={plan.plan_json?.outcome_ids || []}
				{startAtAssets}
				{startAtForms}
				{startNewAsset}
				{editAssetId}
			/>
		{/key}
	{:else}
		{#key plan.id}
			<MelPlanWizard
				{onBack}
				{crumbs}
				projectId={project.id}
				planId={plan.id}
				projectName={project.name}
				planName={plan.name}
				interventionSlug={plan.intervention_slug}
				initialOutcomeIds={plan.plan_json?.outcome_ids || []}
				initialPlanJson={plan.plan_json || null}
				startStep={planStartStep}
			/>
		{/key}
	{/if}
</div>
