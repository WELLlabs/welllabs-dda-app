<script>
	import { appPath } from '$lib/shared/paths.js';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { findBySlug } from '$lib/shared/slug.js';
	import MelFormExplore from '$lib/modules/assess/components/MelFormExplore.svelte';
	import { fetchMelPlan, fetchMelProjects } from '$lib/modules/assess/mel-api';

	let slug = $derived(page.params.slug);
	let planId = $derived(page.params.planId);
	let xmlFormId = $derived(decodeURIComponent(page.params.xmlFormId || ''));
	let projects = $state([]);
	let project = $state(null);
	let plan = $state(null);
	let loading = $state(true);
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
	<title>Form data · Assess</title>
</svelte:head>

<div class="min-h-screen bg-transparent">
	{#if loading}
		<p class="p-6 font-body text-brand-steel">Loading…</p>
	{:else if error || !project || !plan || !xmlFormId}
		<div class="mx-auto max-w-lg p-6">
			<p class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 font-body text-sm text-red-700">
				{error || 'Form not found'}
			</p>
			<button type="button" class="action-btn mt-4" onclick={() => goto(appPath('/assess'))}>
				Back to projects
			</button>
		</div>
	{:else}
		<MelFormExplore {project} {plan} {projects} {xmlFormId} />
	{/if}
</div>
