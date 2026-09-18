<script>
	import { appPath } from '$lib/shared/paths.js';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { findBySlug } from '$lib/shared/slug.js';
	import MelAssetDashboard from '$lib/modules/assess/components/MelAssetDashboard.svelte';
	import MelPlotDashboard from '$lib/modules/assess/components/MelPlotDashboard.svelte';
	import { fetchMelPlan, fetchMelProjects } from '$lib/modules/assess/mel-api';

	let slug = $derived(page.params.slug);
	let planId = $derived(page.params.planId);
	let assetId = $derived(page.params.assetId);
	let projects = $state([]);
	let project = $state(null);
	let plan = $state(null);
	let loading = $state(true);
	let isPlot = $derived(['pmds', 'bio-mulching'].includes(String(plan?.intervention_slug || '').toLowerCase()));
	let error = $state('');

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
</script>

<svelte:head>
	<title>{isPlot ? 'Plot dashboard' : 'Asset dashboard'} · Assess</title>
</svelte:head>

<div class="min-h-screen bg-transparent">
	{#if loading}
		<p class="p-6 font-body text-brand-steel">Loading…</p>
	{:else if error || !project || !plan}
		<div class="mx-auto max-w-lg p-6">
			<p class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 font-body text-sm text-red-700">
				{error || 'Not found'}
			</p>
			<button type="button" class="action-btn mt-4" onclick={() => goto(appPath('/assess'))}>
				Back to Assess
			</button>
		</div>
	{:else}
		{#if isPlot}
			<MelPlotDashboard {project} {plan} {assetId} {projects} />
		{:else}
			<MelAssetDashboard {project} {plan} {assetId} {projects} />
		{/if}
	{/if}
</div>
