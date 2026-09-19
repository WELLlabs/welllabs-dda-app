<script>
	import { appPath } from '$lib/shared/paths.js';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { findBySlug, itemPath } from '$lib/shared/slug.js';
	import MelImplHome from '$lib/modules/assess/components/MelImplHome.svelte';
	import { fetchMelPlan, fetchMelProjects } from '$lib/modules/assess/mel-api';

	let slug = $derived(page.params.slug);
	let planId = $derived(page.params.planId);
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
			// MEL plans open in the designer doc view — no intermediate home screen.
			if (plan && (plan.kind || 'plan') !== 'implementation') {
				const hasOutcomes = Array.isArray(plan.plan_json?.outcome_ids) && plan.plan_json.outcome_ids.length;
				const step = hasOutcomes ? 'plan' : '0';
				await goto(
					`${itemPath('/assess', project, projects)}/plans/${plan.id}/new?step=${step}`,
					{ replaceState: true }
				);
			}
		} catch (err) {
			error = String(err);
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>{plan?.name || 'MEL'} · Assess</title>
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
	{:else if (plan.kind || 'plan') === 'implementation'}
		<MelImplHome {project} {plan} {projects} />
	{/if}
</div>
