<script>
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { findBySlug } from '$lib/shared/slug.js';
	import MelProjectHome from '$lib/modules/assess/components/MelProjectHome.svelte';
	import { fetchMelProjects } from '$lib/modules/assess/mel-api';

	let slug = $derived(page.params.slug);
	let projects = $state([]);
	let project = $state(null);
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
			}
		} catch (err) {
			error = String(err);
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>{project?.name || 'MEL project'} · Assess</title>
</svelte:head>

<div class="min-h-screen bg-transparent">
	{#if loading}
		<p class="p-6 font-body text-brand-steel">Loading…</p>
	{:else if error || !project}
		<div class="mx-auto max-w-lg p-6">
			<p class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 font-body text-sm text-red-700">
				{error || 'Project not found'}
			</p>
			<button type="button" class="action-btn mt-4" onclick={() => goto('/assess')}>
				Back to projects
			</button>
		</div>
	{:else}
		<MelProjectHome {project} {projects} />
	{/if}
</div>
