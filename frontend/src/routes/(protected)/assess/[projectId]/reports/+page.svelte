<script>
	import { onDestroy } from 'svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';
	import ReportEmbed from '$lib/modules/assess/components/ReportEmbed.svelte';
	import { fetchProjectReport } from '$lib/modules/assess/api';

	let projectId = $derived(page.params.projectId);

	/** status: 'loading' | 'ready' | 'empty' | 'error' */
	let status = $state('loading');
	let report = $state(null);
	let projectName = $state('');
	let errorMessage = $state('');

	let refreshTimer;

	async function load() {
		try {
			const data = await fetchProjectReport(projectId);
			projectName = data.project_name ?? '';
			if (!data.configured) {
				status = 'empty';
				clearTimeout(refreshTimer);
				return;
			}
			report = data;
			status = 'ready';
			scheduleRefresh(data.expires_at);
		} catch (err) {
			errorMessage = err?.message ?? 'Could not load the report.';
			status = 'error';
		}
	}

	/** Re-fetch a fresh token ~1 min before the current one expires. */
	function scheduleRefresh(expiresAt) {
		clearTimeout(refreshTimer);
		if (!expiresAt) return;
		const ms = Math.max(30_000, (expiresAt - Math.floor(Date.now() / 1000) - 60) * 1000);
		refreshTimer = setTimeout(() => load().catch(() => {}), ms);
	}

	// Reload whenever the project in the URL changes.
	$effect(() => {
		if (projectId) {
			status = 'loading';
			load();
		}
	});

	onDestroy(() => clearTimeout(refreshTimer));
</script>

<svelte:head>
	<title>{projectName ? `${projectName} · Reports` : 'Reports · Assess'}</title>
</svelte:head>

<div class="flex min-h-screen flex-col bg-brand-pale/20">
	<ModuleHeader title="Assess" project={projectName} subtitle="Project analytics dashboard." />

	<main class="relative z-10 flex flex-1 flex-col p-6">
		<button
			class="mb-4 inline-flex w-fit items-center gap-1 rounded-full border border-brand-navy/15 bg-white px-3 py-1.5 font-body text-sm text-brand-navy transition hover:border-brand-blue hover:text-brand-blue"
			onclick={() => goto('/assess')}
		>
			<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="h-4 w-4"><path d="M19 12H5M11 6l-6 6 6 6" stroke-linecap="round" stroke-linejoin="round" /></svg>
			Projects
		</button>

		{#if status === 'loading'}
			<div class="flex flex-1 items-center justify-center text-brand-steel">Loading report…</div>
		{:else if status === 'error'}
			<div class="flex flex-1 flex-col items-center justify-center gap-2 text-center">
				<p class="font-medium text-red-600">Couldn't load the report</p>
				<p class="text-sm text-brand-steel">{errorMessage}</p>
			</div>
		{:else if status === 'empty'}
			<div class="flex flex-1 flex-col items-center justify-center gap-2 text-center">
				<div class="flex h-12 w-12 items-center justify-center rounded-full bg-brand-navy/5 text-brand-steel">
					<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" class="h-6 w-6"><path d="M4 4v16h16M8 16l3-4 3 3 4-6" stroke-linecap="round" stroke-linejoin="round" /></svg>
				</div>
				<p class="font-medium text-brand-navy">No report configured for this project yet</p>
				<p class="max-w-sm text-sm text-brand-steel">
					Once a dashboard is created in Metabase and linked to this project, it will appear here.
				</p>
			</div>
		{:else if status === 'ready'}
			<div class="min-h-0 flex-1 overflow-hidden rounded-xl border border-brand-navy/10 bg-white">
				{#key report.dashboard_id}
					<ReportEmbed {report} />
				{/key}
			</div>
		{/if}
	</main>
</div>
