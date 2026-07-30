<script>
	import { onMount } from 'svelte';
	import { fade, scale } from 'svelte/transition';
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';
	import { fetchProjects, importProjects } from '$lib/modules/assess/api';

	/** @type {{ onOpen: (project: any) => void }} */
	let { onOpen } = $props();

	let projects = $state([]);
	let loading = $state(true);
	let error = $state('');
	let importing = $state(false);
	let importMsg = $state('');

	onMount(loadProjects);

	async function loadProjects() {
		loading = true;
		error = '';
		try {
			const data = await fetchProjects();
			projects = data.projects ?? [];
		} catch (err) {
			error = String(err);
		} finally {
			loading = false;
		}
	}

	async function handleImport() {
		if (importing) return;
		importing = true;
		importMsg = '';
		error = '';
		try {
			const res = await importProjects();
			const count = res?.synced?.length ?? res?.data?.length ?? 0;
			importMsg = `Synced ${count} project${count === 1 ? '' : 's'} from ODK Central.`;
			await loadProjects();
		} catch (err) {
			error = String(err);
		} finally {
			importing = false;
		}
	}

	function initials(name) {
		return (name ?? '?')
			.split(/\s+/)
			.filter(Boolean)
			.slice(0, 2)
			.map((w) => w[0].toUpperCase())
			.join('');
	}

	function formatDate(iso) {
		if (!iso) return '—';
		const d = new Date(iso);
		if (Number.isNaN(d.getTime())) return '—';
		const day = d.getDate();
		const suffix =
			day % 10 === 1 && day !== 11
				? 'st'
				: day % 10 === 2 && day !== 12
					? 'nd'
					: day % 10 === 3 && day !== 13
						? 'rd'
						: 'th';
		return `${day}${suffix} ${d.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })}`;
	}
</script>

<div class="relative min-h-screen bg-transparent font-body">
	<ModuleHeader title="Assess" subtitle="Select a project to view its forms and field submissions." />

	<main class="relative z-10 flex-1 overflow-auto p-6">
		{#if importMsg}
			<div in:fade class="mb-4 flex items-center gap-2 rounded-lg border border-brand-forest/25 bg-brand-forest/5 px-4 py-2.5 font-body text-sm text-brand-forest">
				<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4 shrink-0"><path fill-rule="evenodd" d="M16.7 5.3a1 1 0 0 1 0 1.4l-7.5 7.5a1 1 0 0 1-1.4 0L3.3 9.7a1 1 0 1 1 1.4-1.4L8.5 12l6.8-6.7a1 1 0 0 1 1.4 0z" clip-rule="evenodd" /></svg>
				{importMsg}
			</div>
		{/if}

		{#if error}
			<p class="mb-4 text-sm text-red-600">{error}</p>
		{/if}

		{#if loading}
			<p class="text-brand-steel">Loading projects…</p>
		{:else}
			<div class="grid gap-5" style="grid-template-columns: repeat(auto-fill, minmax(min(100%, 20rem), 1fr));">
				<!-- Import tile (mirrors diagnose "New project") -->
				<button
					class="flex min-h-[7rem] cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-brand-blue/50 bg-white p-4 text-brand-blue shadow-sm transition hover:border-brand-blue hover:bg-brand-sky/15 disabled:cursor-not-allowed disabled:opacity-60"
					disabled={importing}
					onclick={handleImport}
				>
					<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" class="h-7 w-7 {importing ? 'animate-spin' : ''}">
						<path d="M21 12a9 9 0 1 1-3-6.7L21 8" stroke-linecap="round" stroke-linejoin="round" /><path d="M21 3v5h-5" stroke-linecap="round" stroke-linejoin="round" />
					</svg>
					<span class="mt-2 font-body font-medium">{importing ? 'Syncing…' : 'Import from ODK'}</span>
				</button>

				{#each projects as project, i (project.id)}
					<button
						in:scale={{ start: 0.97, duration: 240, delay: Math.min(i, 8) * 35 }}
						class="group relative flex cursor-pointer flex-col rounded-2xl border border-brand-navy/10 bg-white text-left shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-brand-blue/40 hover:shadow-md"
						onclick={() => onOpen(project)}
					>
						<div class="flex items-center gap-3 p-3">
							<div class="assess-avatar flex h-11 w-11 shrink-0 items-center justify-center rounded-full font-headline text-sm font-semibold text-white">
								{initials(project.name)}
							</div>
							<div class="min-w-0 flex-1">
								<h3 class="m-0 break-words font-headline text-sm font-semibold tracking-tight text-brand-navy">{project.name}</h3>
								<p class="m-0 mt-0.5 truncate font-body text-[11px] text-brand-steel">ODK project #{project.odk_project_id}</p>
							</div>
							<span class="shrink-0 self-start rounded-full px-2 py-0.5 font-body text-[9px] font-semibold tracking-wide uppercase {project.status === 'active' ? 'bg-brand-forest/10 text-brand-forest' : 'bg-brand-steel/10 text-brand-steel'}">
								{project.status ?? 'active'}
							</span>
						</div>

						<div class="flex items-center justify-between gap-3 border-t border-brand-navy/10 bg-gray-50 px-3 py-2">
							<div class="flex min-w-0 items-center gap-2">
								<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" class="h-3.5 w-3.5 shrink-0 text-brand-steel"><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M8 3v4M16 3v4M3 10h18" stroke-linecap="round" /></svg>
								<p class="m-0 font-body text-[9px] leading-snug font-medium tracking-wide text-brand-steel">{formatDate(project.updated_at ?? project.created_at)}</p>
							</div>
							<span class="flex shrink-0 items-center gap-1 font-body text-xs font-medium text-brand-blue opacity-0 transition-opacity duration-200 group-hover:opacity-100">
								View forms
								<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="h-3.5 w-3.5"><path d="M5 12h14M13 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round" /></svg>
							</span>
						</div>
					</button>
				{/each}
			</div>

			{#if projects.length === 0}
				<p class="mt-4 font-body text-sm text-brand-steel">No projects yet. Import from ODK to get started.</p>
			{/if}
		{/if}
	</main>
</div>

<style>
	.assess-avatar {
		background: linear-gradient(135deg, #3969a7, #1b75e0);
		box-shadow: 0 8px 18px -8px rgba(27, 117, 224, 0.6);
	}
</style>
