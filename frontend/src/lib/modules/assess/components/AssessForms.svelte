<script>
	import { fade, scale } from 'svelte/transition';
	import { goto } from '$app/navigation';
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';
	import { fetchForms } from '$lib/modules/assess/api';

	/** @type {{ project: any, onOpen: (form: any) => void, onBack: () => void }} */
	let { project, onOpen, onBack } = $props();

	let forms = $state([]);
	let loading = $state(true);
	let error = $state('');

	$effect(() => {
		if (project?.id) loadForms(project.id);
	});

	async function loadForms(projectId) {
		loading = true;
		error = '';
		forms = [];
		try {
			const data = await fetchForms(projectId);
			forms = Array.isArray(data) ? data : (data?.value ?? []);
		} catch (err) {
			error = String(err);
		} finally {
			loading = false;
		}
	}

	function formatDate(iso) {
		if (!iso) return '—';
		const d = new Date(iso);
		if (Number.isNaN(d.getTime())) return '—';
		return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
	}
</script>

<div class="relative min-h-screen bg-transparent font-body">
	<ModuleHeader title="Assess" project={project?.name} subtitle="Select a form to browse its submissions." />

	<main class="relative z-10 flex-1 overflow-auto p-6">
		<div class="mb-4 flex items-center justify-between gap-3">
			<button
				class="inline-flex items-center gap-1 rounded-full border border-brand-navy/15 bg-white px-3 py-1.5 font-body text-sm text-brand-navy transition hover:border-brand-blue hover:text-brand-blue"
				onclick={onBack}
			>
				<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="h-4 w-4"><path d="M19 12H5M11 6l-6 6 6 6" stroke-linecap="round" stroke-linejoin="round" /></svg>
				Projects
			</button>

			{#if project?.id}
				<button
					class="inline-flex items-center gap-1.5 rounded-full border border-brand-blue/30 bg-brand-blue/5 px-3 py-1.5 font-body text-sm font-medium text-brand-blue transition hover:border-brand-blue hover:bg-brand-blue/10"
					onclick={() => goto(`/assess/${project.id}/reports`)}
				>
					<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="h-4 w-4"><path d="M4 4v16h16M8 16l3-4 3 3 4-6" stroke-linecap="round" stroke-linejoin="round" /></svg>
					Reports
				</button>
			{/if}
		</div>

		{#if error}
			<p class="mb-4 text-sm text-red-600">{error}</p>
		{/if}

		{#if loading}
			<p class="text-brand-steel">Loading forms…</p>
		{:else if forms.length === 0}
			<p class="font-body text-sm text-brand-steel">This project has no published forms yet.</p>
		{:else}
			<div class="grid gap-5" style="grid-template-columns: repeat(auto-fill, minmax(min(100%, 22rem), 1fr));">
				{#each forms as form, i (form.xmlFormId)}
					<button
						in:scale={{ start: 0.97, duration: 240, delay: Math.min(i, 8) * 35 }}
						class="group relative flex cursor-pointer items-center gap-4 rounded-2xl border border-brand-navy/10 bg-white p-4 text-left shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-brand-blue/40 hover:shadow-md"
						onclick={() => onOpen(form)}
					>
						<div class="form-icon flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-white">
							<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" class="h-5 w-5"><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 8h8M8 12h8M8 16h5" stroke-linecap="round" /></svg>
						</div>
						<div class="min-w-0 flex-1">
							<h3 class="m-0 truncate font-headline text-sm font-semibold text-brand-navy">{form.name ?? form.xmlFormId}</h3>
							<p class="m-0 mt-0.5 truncate font-mono text-[11px] text-brand-steel">{form.xmlFormId}</p>
							<div class="mt-1.5 flex flex-wrap items-center gap-2 font-body text-[11px] text-brand-steel">
								{#if form.version}<span class="rounded bg-brand-navy/[0.05] px-1.5 py-0.5">v{form.version}</span>{/if}
								{#if form.state}<span class="rounded px-1.5 py-0.5 {form.state === 'open' ? 'bg-brand-forest/10 text-brand-forest' : 'bg-brand-steel/10 text-brand-steel'}">{form.state}</span>{/if}
								<span>Updated {formatDate(form.updatedAt ?? form.createdAt)}</span>
							</div>
						</div>
						<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="h-5 w-5 shrink-0 text-brand-steel/40 transition-all duration-200 group-hover:translate-x-0.5 group-hover:text-brand-blue"><path d="M9 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round" /></svg>
					</button>
				{/each}
			</div>
		{/if}
	</main>
</div>

<style>
	.form-icon {
		background: linear-gradient(135deg, #3969a7, #1b75e0);
		box-shadow: 0 8px 18px -8px rgba(27, 117, 224, 0.55);
	}
</style>
