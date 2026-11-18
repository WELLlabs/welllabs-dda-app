<script>
	import { page } from '$app/state';
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';
	import SolutionDesigner from '$lib/modules/design/components/SolutionDesigner.svelte';
	import { fetchDesignProject, fetchDesignProjects } from '$lib/modules/design/api.js';
	import { findBySlug } from '$lib/shared/slug.js';
	import { appPath } from '$lib/shared/paths.js';

	const slug = $derived(page.params.slug);

	let project = $state(/** @type {any} */ (null));
	let loading = $state(true);
	let loadError = $state('');
	let loadGen = 0;

	async function load(slugValue) {
		const gen = ++loadGen;
		loading = true;
		loadError = '';
		project = null;
		try {
			const list = await fetchDesignProjects();
			if (gen !== loadGen) return;
			const match = findBySlug(list.projects ?? [], slugValue);
			if (!match) {
				loadError = 'Project not found';
				return;
			}
			const full = await fetchDesignProject(match.id);
			if (gen !== loadGen) return;
			project = full;
		} catch (err) {
			if (gen !== loadGen) return;
			loadError = err instanceof Error ? err.message : String(err);
		} finally {
			if (gen === loadGen) loading = false;
		}
	}

	$effect(() => {
		void load(slug);
	});

	const sourceLabel = $derived(
		!project
			? ''
			: project.aoi_source === 'diagnosis' && project.source_diagnosis_name
				? `AOI from PD: ${project.source_diagnosis_name}`
				: project.aoi_name || ''
	);
</script>

<svelte:head>
	<title>{project?.name ?? 'Design'} · Water Security Toolbox</title>
</svelte:head>

<div class="flex min-h-screen flex-col bg-white font-body md:h-screen md:min-h-0 md:overflow-hidden">
	<ModuleHeader title="Design" titleHref="/design" project={project?.name ?? ''} subtitle={sourceLabel} wide />

	{#if loading}
		<p class="p-6 text-brand-steel">Loading project…</p>
	{:else if loadError}
		<div class="p-6">
			<p class="m-0 text-red-600">{loadError}</p>
			<a class="mt-2 inline-block text-sm text-brand-blue" href={appPath("/design")}>Back to design projects</a>
		</div>
	{:else if project}
		{#key project.id}
			<SolutionDesigner {project} />
		{/key}
	{/if}
</div>
