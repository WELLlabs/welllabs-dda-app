<script>
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';
	import LocationPicker from '$lib/shared/components/LocationPicker.svelte';
	import WatershedThumb from '$lib/shared/components/WatershedThumb.svelte';
	import { itemPath } from '$lib/shared/slug.js';
	import { session } from '$lib/shared/session.svelte.js';
	import FieldNoteIcon from '$lib/modules/diagnose/components/icons/FieldNoteIcon.svelte';
	import ObservationZoneIcon from '$lib/modules/diagnose/components/icons/ObservationZoneIcon.svelte';
	import { createProject, deleteProject, fetchProjects, lookupWatershed } from '$lib/modules/diagnose/api';

	let projects = $state([]);
	let loading = $state(true);
	let error = $state('');
	let showCreate = $state(false);
	let openMenuId = $state(null);
	let name = $state('');
	let lng = $state(77.2);
	let lat = $state(28.6);
	let watershedPreview = $state(null);
	let previewLoading = $state(false);
	let creating = $state(false);
	let deletingId = $state(null);
	let mounted = $state(false);

	onMount(() => {
		loadProjects();
		mounted = true;
		document.addEventListener('click', closeMenu);
		return () => document.removeEventListener('click', closeMenu);
	});

	function handlePointer(event) {
		const el = event.currentTarget;
		const rect = el.getBoundingClientRect();
		el.style.setProperty('--mx', `${event.clientX - rect.left}px`);
		el.style.setProperty('--my', `${event.clientY - rect.top}px`);
	}

	function closeMenu() {
		openMenuId = null;
	}

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

	async function previewWatershed() {
		previewLoading = true;
		watershedPreview = null;
		try {
			watershedPreview = await lookupWatershed(lng, lat);
		} catch (err) {
			watershedPreview = { error: String(err) };
		} finally {
			previewLoading = false;
		}
	}

	function openProject(project) {
		goto(itemPath('/diagnose', project, projects));
	}

	async function handleCreate() {
		if (!name.trim()) return;
		creating = true;
		error = '';
		try {
			const project = await createProject(name.trim(), lng, lat);
			showCreate = false;
			name = '';
			watershedPreview = null;
			await loadProjects();
			openProject(project);
		} catch (err) {
			error = String(err);
		} finally {
			creating = false;
		}
	}

	function openCreate() {
		showCreate = true;
		error = '';
		watershedPreview = null;
	}

	function formatProjectDate(iso) {
		const d = new Date(iso);
		const day = d.getDate();
		const suffix =
			day % 10 === 1 && day !== 11
				? 'st'
				: day % 10 === 2 && day !== 12
					? 'nd'
					: day % 10 === 3 && day !== 13
						? 'rd'
						: 'th';
		const monthYear = d.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });
		return `${day}${suffix} ${monthYear}`;
	}

	function toggleMenu(e, projectId) {
		e.stopPropagation();
		openMenuId = openMenuId === projectId ? null : projectId;
	}

	function isOwner(project) {
		return session.user && project.owner_id === session.user.id;
	}

	function handleManageMembers(e, project) {
		e.stopPropagation();
		openMenuId = null;
		goto(`${itemPath('/diagnose', project, projects)}/members`);
	}

	async function handleDeleteProject(e, project) {
		e.stopPropagation();
		openMenuId = null;
		if (!confirm(`Delete project "${project.name}"? This cannot be undone.`)) return;
		deletingId = project.id;
		error = '';
		try {
			await deleteProject(project.id);
			await loadProjects();
		} catch (err) {
			error = String(err);
		} finally {
			deletingId = null;
		}
	}
</script>

<div class="relative min-h-screen bg-transparent font-body">
	<ModuleHeader title="Diagnose" titleHref="/diagnose" subtitle="Select a project or create a new one to begin mapping." />

	<main class="relative z-10 flex-1 overflow-auto p-6">
		{#if loading}
			<p class="text-brand-steel">Loading projects…</p>
		{:else if showCreate}
			<div class="mx-auto max-w-2xl rounded-xl bg-white p-6 shadow-sm">
				<h2 class="m-0 mb-4 font-headline text-lg font-semibold text-brand-navy">New project</h2>

				<label class="mb-1 block font-body text-sm font-medium text-brand-navy" for="proj-name"
					>Project name</label
				>
				<input
					id="proj-name"
					type="text"
					class="mb-4 w-full rounded border border-brand-navy/20 px-3 py-2 font-body"
					bind:value={name}
					placeholder="e.g. North basin survey"
				/>

				<div class="mb-4 h-80">
					<LocationPicker bind:lng bind:lat onPick={previewWatershed} />
				</div>

				<div class="mb-4 rounded-lg bg-brand-sky/20 p-3 font-body text-sm">
					{#if previewLoading}
						<p class="m-0 text-brand-steel">Looking up watershed…</p>
					{:else if watershedPreview?.error}
						<p class="m-0 text-red-600">{watershedPreview.error}</p>
					{:else if watershedPreview}
						<p class="m-0 font-medium text-brand-navy">Watershed: {watershedPreview.watershed_name}</p>
						<p class="m-0 mt-1 text-brand-steel">ID: {watershedPreview.watershed_id}</p>
					{:else}
						<p class="m-0 text-brand-steel">
							Click the map to detect the watershed at that location.
						</p>
					{/if}
				</div>

				{#if error}
					<p class="mb-3 text-sm text-red-600">{error}</p>
				{/if}

				<div class="flex gap-2">
					<button
						class="cursor-pointer rounded bg-brand-blue px-4 py-2 font-body text-white disabled:opacity-60"
						disabled={creating || !name.trim()}
						onclick={handleCreate}
					>
						{creating ? 'Creating…' : 'Create project'}
					</button>
					<button
						class="cursor-pointer rounded bg-brand-steel px-4 py-2 font-body text-white hover:bg-brand-navy"
						onclick={() => (showCreate = false)}
					>
						Cancel
					</button>
				</div>
			</div>
		{:else}
			{#if error}
				<p class="mb-4 text-sm text-red-600">{error}</p>
			{/if}

			<div
				class="grid gap-6"
				style="grid-template-columns: repeat(auto-fill, minmax(min(100%, 20rem), 1fr));"
			>
				<button
					type="button"
					class="card card-new group"
					class:in={mounted}
					style="--accent: #0FB3A3; --delay: 0ms;"
					onpointermove={handlePointer}
					onclick={openCreate}
				>
					<span class="card-spotlight" aria-hidden="true"></span>
					<span class="card-topline" aria-hidden="true"></span>
					<div class="relative z-10 flex w-full flex-col items-start gap-4">
						<div class="icon-wrap icon-wrap-dashed">
							<span class="text-2xl leading-none text-[color:var(--accent)]">+</span>
						</div>
						<h3 class="card-title m-0 font-display text-xl">New project</h3>
						<p class="card-desc m-0 font-body text-[13.5px] leading-relaxed">
							Create a watershed project and start mapping.
						</p>
						<span class="cta mt-1 font-mono text-[12px]">
							Create
							<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="arrow h-3.5 w-3.5">
								<path d="M5 12h14M13 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round" />
							</svg>
						</span>
					</div>
				</button>

				{#each projects as project, i (project.id)}
					<div
						class="card group"
						class:in={mounted}
						style="--accent: #0FB3A3; --delay: {(i + 1) * 70}ms;"
						role="button"
						tabindex="0"
						onpointermove={handlePointer}
						onclick={() => openProject(project)}
						onkeydown={(e) => {
							if (e.key === 'Enter' || e.key === ' ') {
								e.preventDefault();
								openProject(project);
							}
						}}
					>
						<span class="card-spotlight" aria-hidden="true"></span>
						<span class="card-topline" aria-hidden="true"></span>

						<div class="relative z-10 flex w-full flex-col items-start gap-4">
							<div class="flex w-full items-start justify-between gap-2">
								<div class="icon-wrap icon-wrap-thumb">
									<WatershedThumb geometry={project.watershed_geometry} circular />
								</div>

								<div class="relative shrink-0" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
									<button
										type="button"
										class="menu-btn"
										aria-label="Project actions"
										disabled={deletingId === project.id}
										onclick={(e) => toggleMenu(e, project.id)}
									>
										<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="h-5 w-5">
											<circle cx="12" cy="5" r="1.5" />
											<circle cx="12" cy="12" r="1.5" />
											<circle cx="12" cy="19" r="1.5" />
										</svg>
									</button>
									{#if openMenuId === project.id}
										<div class="menu-panel">
											{#if isOwner(project)}
												<button
													type="button"
													class="menu-item"
													onclick={(e) => handleManageMembers(e, project)}
												>
													Members
												</button>
												<button
													type="button"
													class="menu-item menu-item-danger"
													disabled={deletingId === project.id}
													onclick={(e) => handleDeleteProject(e, project)}
												>
													{deletingId === project.id ? 'Deleting…' : 'Delete'}
												</button>
											{:else}
												<p class="m-0 px-3 py-2 text-left font-body text-xs text-[#6b7885]">
													Shared with you
												</p>
											{/if}
										</div>
									{/if}
								</div>
							</div>

							<h3 class="card-title m-0 min-w-0 break-words font-display text-xl">
								{project.name}
							</h3>

							<div class="card-meta flex w-full flex-wrap items-center justify-between gap-3">
								<div class="flex min-w-0 items-center gap-2 text-[#6b7885]">
									<svg
										xmlns="http://www.w3.org/2000/svg"
										viewBox="0 0 24 24"
										fill="none"
										stroke="currentColor"
										stroke-width="1.75"
										class="h-3.5 w-3.5 shrink-0"
										aria-hidden="true"
									>
										<rect x="3" y="5" width="18" height="16" rx="2" />
										<path d="M8 3v4M16 3v4M3 10h18" stroke-linecap="round" />
									</svg>
									<span class="font-mono text-[11px] tracking-wide">
										{formatProjectDate(project.updated_at ?? project.created_at)}
									</span>
								</div>

								<div class="flex shrink-0 items-center gap-3">
									<div
										class="flex items-center gap-1.5"
										aria-label="{project.observation_zone_count ?? 0} observation zones"
									>
										<ObservationZoneIcon size="sm" />
										<span class="font-display text-sm font-semibold text-[#1a2530]">
											{project.observation_zone_count ?? 0}
										</span>
									</div>
									<div class="h-4 w-px bg-[rgba(20,40,60,0.12)]" aria-hidden="true"></div>
									<div
										class="flex items-center gap-1.5"
										aria-label="{project.field_note_count ?? 0} field notes"
									>
										<FieldNoteIcon size="sm" />
										<span class="font-display text-sm font-semibold text-[#1a2530]">
											{project.field_note_count ?? 0}
										</span>
									</div>
								</div>
							</div>

							<span class="cta mt-1 font-mono text-[12px]">
								Open project
								<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="arrow h-3.5 w-3.5">
									<path d="M5 12h14M13 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round" />
								</svg>
							</span>
						</div>
					</div>
				{/each}
			</div>

			{#if projects.length === 0}
				<p class="mt-4 font-body text-sm text-[#56646f]">No projects yet. Create one to get started.</p>
			{/if}
		{/if}
	</main>
</div>

<style>
	.card {
		position: relative;
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		overflow: visible;
		border-radius: 22px;
		border: 1px solid rgba(20, 40, 60, 0.08);
		background: rgba(255, 255, 255, 0.85);
		padding: 1.6rem;
		text-align: left;
		cursor: pointer;
		backdrop-filter: blur(6px);
		box-shadow: 0 1px 0 rgba(255, 255, 255, 0.8) inset, 0 12px 28px -20px rgba(20, 40, 60, 0.35);
		opacity: 0;
		transform: translateY(24px);
		transition:
			transform 0.35s cubic-bezier(0.2, 0.8, 0.2, 1),
			box-shadow 0.35s ease,
			border-color 0.35s ease,
			opacity 0.6s ease;
	}
	.card.in {
		opacity: 1;
		transform: translateY(0);
		transition-delay: var(--delay);
	}
	.card:hover {
		transform: translateY(-6px);
		border-color: color-mix(in srgb, var(--accent) 45%, transparent);
		box-shadow:
			0 1px 0 rgba(255, 255, 255, 0.9) inset,
			0 24px 44px -22px color-mix(in srgb, var(--accent) 50%, transparent);
	}
	.card:active {
		transform: translateY(-2px) scale(0.995);
	}
	.card:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 3px;
	}

	.card-new {
		border-style: dashed;
		border-color: color-mix(in srgb, var(--accent) 40%, transparent);
		background: color-mix(in srgb, var(--accent) 4%, white);
	}

	.card-spotlight {
		position: absolute;
		inset: 0;
		z-index: 0;
		overflow: hidden;
		border-radius: inherit;
		opacity: 0;
		transition: opacity 0.3s ease;
		background: radial-gradient(
			320px circle at var(--mx, 50%) var(--my, 0%),
			color-mix(in srgb, var(--accent) 14%, transparent),
			transparent 60%
		);
		pointer-events: none;
	}
	.card:hover .card-spotlight {
		opacity: 1;
	}

	.card-topline {
		position: absolute;
		top: 0;
		left: 0;
		z-index: 1;
		height: 3px;
		width: 100%;
		transform: scaleX(0);
		transform-origin: left;
		border-radius: 22px 22px 0 0;
		background: linear-gradient(90deg, var(--accent), transparent);
		transition: transform 0.4s cubic-bezier(0.2, 0.8, 0.2, 1);
		pointer-events: none;
	}
	.card:hover .card-topline {
		transform: scaleX(1);
	}

	.card-title {
		color: #1a2530;
	}
	.card-desc,
	.card-meta {
		color: #56646f;
	}

	.icon-wrap {
		display: flex;
		height: 3rem;
		width: 3rem;
		align-items: center;
		justify-content: center;
		overflow: hidden;
		border-radius: 14px;
		border: 1px solid rgba(20, 40, 60, 0.06);
		background: color-mix(in srgb, var(--accent) 12%, white);
		transition:
			transform 0.35s cubic-bezier(0.2, 0.8, 0.2, 1),
			box-shadow 0.35s ease;
	}
	.icon-wrap-thumb {
		height: 3.5rem;
		width: 3.5rem;
		padding: 0.15rem;
	}
	.icon-wrap-dashed {
		border-style: dashed;
		border-color: color-mix(in srgb, var(--accent) 40%, transparent);
	}
	.card:hover .icon-wrap {
		transform: scale(1.08) rotate(-4deg);
		box-shadow: 0 10px 24px -12px color-mix(in srgb, var(--accent) 60%, transparent);
	}

	.cta {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		color: color-mix(in srgb, var(--accent) 80%, black);
	}
	.cta .arrow {
		transition: transform 0.3s ease;
	}
	.card:hover .cta .arrow {
		transform: translateX(4px);
	}

	.menu-btn {
		display: flex;
		height: 2rem;
		width: 2rem;
		cursor: pointer;
		align-items: center;
		justify-content: center;
		border: 0;
		border-radius: 0.5rem;
		background: transparent;
		color: #6b7885;
	}
	.menu-btn:hover {
		background: color-mix(in srgb, var(--accent) 12%, white);
		color: #1a2530;
	}
	.menu-panel {
		position: absolute;
		right: 0;
		z-index: 30;
		margin-top: 0.25rem;
		min-width: 8rem;
		overflow: hidden;
		border-radius: 0.75rem;
		border: 1px solid rgba(20, 40, 60, 0.1);
		background: white;
		box-shadow: 0 12px 28px -16px rgba(20, 40, 60, 0.4);
	}
	.menu-item {
		display: block;
		width: 100%;
		cursor: pointer;
		border: 0;
		background: white;
		padding: 0.55rem 0.85rem;
		text-align: left;
		font-family: inherit;
		font-size: 0.875rem;
		color: #1a2530;
	}
	.menu-item:hover {
		background: color-mix(in srgb, var(--accent) 10%, white);
	}
	.menu-item-danger {
		color: #dc2626;
	}
	.menu-item-danger:hover {
		background: #fef2f2;
	}

	@media (prefers-reduced-motion: reduce) {
		.card {
			transition: none;
			opacity: 1;
			transform: none;
		}
	}
</style>
