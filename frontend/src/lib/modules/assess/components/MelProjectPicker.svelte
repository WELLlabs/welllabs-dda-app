<script>
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';
	import { itemPath } from '$lib/shared/slug.js';
	import { session } from '$lib/shared/session.svelte.js';
	import { assessCrumbs } from '$lib/modules/assess/breadcrumbs.js';
	import { createMelProject, deleteMelProject, fetchMelProjects } from '$lib/modules/assess/mel-api';

	const ASSESS_BLUE = '#1b75e0';

	let projects = $state([]);
	let loading = $state(true);
	let error = $state('');
	let mounted = $state(false);
	let showCreate = $state(false);
	let openMenuId = $state(null);
	let name = $state('');
	let creating = $state(false);
	let deletingId = $state(null);

	onMount(() => {
		mounted = true;
		load();
		document.addEventListener('click', closeMenu);
		return () => document.removeEventListener('click', closeMenu);
	});

	function closeMenu() {
		openMenuId = null;
	}

	async function load() {
		loading = true;
		error = '';
		try {
			const projRes = await fetchMelProjects();
			projects = projRes.projects ?? [];
		} catch (err) {
			error = String(err);
		} finally {
			loading = false;
		}
	}

	function openProject(project) {
		goto(itemPath('/assess', project, projects));
	}

	function isOwner(project) {
		return session.user && project.owner_id === session.user.id;
	}

	function openCreate() {
		showCreate = true;
		error = '';
		name = '';
	}

	/** @param {PointerEvent & { currentTarget: HTMLElement }} e */
	function handlePointer(e) {
		const rect = e.currentTarget.getBoundingClientRect();
		e.currentTarget.style.setProperty('--mx', `${e.clientX - rect.left}px`);
		e.currentTarget.style.setProperty('--my', `${e.clientY - rect.top}px`);
	}

	async function handleCreate() {
		if (!name.trim()) return;
		creating = true;
		error = '';
		try {
			const project = await createMelProject({ name: name.trim() });
			showCreate = false;
			name = '';
			await load();
			openProject(project);
		} catch (err) {
			error = String(err);
		} finally {
			creating = false;
		}
	}

	async function handleDelete(project) {
		if (!confirm(`Delete MEL project “${project.name}”? This cannot be undone.`)) return;
		deletingId = project.id;
		error = '';
		try {
			await deleteMelProject(project.id);
			openMenuId = null;
			await load();
		} catch (err) {
			error = String(err);
		} finally {
			deletingId = null;
		}
	}

	function formatDate(iso) {
		if (!iso) return '—';
		try {
			return new Date(iso).toLocaleDateString(undefined, {
				year: 'numeric',
				month: 'short',
				day: 'numeric'
			});
		} catch {
			return iso;
		}
	}
</script>

<div class="relative min-h-screen bg-transparent font-body">
	<ModuleHeader
		title="Assess"
		titleHref="/assess"
		wide
		crumbs={assessCrumbs({})}
	/>

	<main class="relative z-10 flex-1 overflow-auto p-6">
		{#if error && !showCreate}
			<p class="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 font-body text-sm text-red-700">{error}</p>
		{/if}

		{#if loading}
			<p class="font-body text-brand-steel">Loading projects…</p>
		{:else}
			<div
				class="grid gap-6"
				style="grid-template-columns: repeat(auto-fill, minmax(min(100%, 20rem), 1fr));"
			>
				<button
					type="button"
					class="card card-new group"
					class:in={mounted}
					style="--accent: {ASSESS_BLUE}; --delay: 0ms;"
					onpointermove={handlePointer}
					onclick={openCreate}
				>
					<span class="card-spotlight" aria-hidden="true"></span>
					<span class="card-topline" aria-hidden="true"></span>
					<div class="relative z-10 flex w-full flex-col items-start gap-4">
						<div class="icon-wrap icon-wrap-dashed">
							<span class="text-2xl leading-none text-[color:var(--accent)]">+</span>
						</div>
						<h3 class="card-title m-0 font-display text-xl">New MEL project</h3>
						<p class="card-desc m-0 font-body text-[13.5px] leading-relaxed">
							Create a project, then add MEL plans and publish ODK forms.
						</p>
						<span class="cta mt-1 font-mono text-[12px]">
							Create
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="2"
								class="arrow h-3.5 w-3.5"
							>
								<path d="M5 12h14M13 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round" />
							</svg>
						</span>
					</div>
				</button>

				{#each projects as project, i (project.id)}
					<div
						class="card group"
						class:in={mounted}
						style="--accent: {ASSESS_BLUE}; --delay: {(i + 1) * 70}ms;"
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
						<div class="relative z-10 flex w-full flex-col items-start gap-3">
							<div class="flex w-full items-start justify-between gap-2">
								<div class="icon-wrap">
									<svg
										xmlns="http://www.w3.org/2000/svg"
										viewBox="0 0 24 24"
										fill="none"
										stroke="currentColor"
										stroke-width="1.75"
										class="h-5 w-5 text-[color:var(--accent)]"
										aria-hidden="true"
									>
										<path
											d="M4 19V5M4 19h16M8 15l3-4 3 2 4-6"
											stroke-linecap="round"
											stroke-linejoin="round"
										/>
									</svg>
								</div>
								{#if isOwner(project)}
									<button
										type="button"
										class="menu-btn"
										aria-label="Project actions"
										onclick={(e) => {
											e.stopPropagation();
											openMenuId = openMenuId === project.id ? null : project.id;
										}}
									>
										···
									</button>
								{/if}
							</div>
							{#if openMenuId === project.id}
								<div
									class="menu-panel"
									role="menu"
									tabindex="-1"
									onclick={(e) => e.stopPropagation()}
									onkeydown={(e) => e.stopPropagation()}
								>
									<button
										type="button"
										class="menu-item menu-item-danger"
										role="menuitem"
										disabled={deletingId === project.id}
										onclick={() => handleDelete(project)}
									>
										{deletingId === project.id ? 'Deleting…' : 'Delete'}
									</button>
								</div>
							{/if}
							<h3 class="card-title m-0 font-display text-xl">{project.name}</h3>
							<p class="card-desc m-0 text-sm">
								{project.plan_count ?? 0} plan{(project.plan_count ?? 0) === 1 ? '' : 's'}
								· {project.form_count ?? 0} form{(project.form_count ?? 0) === 1 ? '' : 's'}
								{#if !isOwner(project)}
									· Shared
								{/if}
							</p>
							<p class="m-0 font-mono text-[11px] tracking-wide text-[#6b7885]">
								Updated {formatDate(project.updated_at)}
							</p>
							<span class="cta mt-1 font-mono text-[12px]">
								Open project
								<svg
									xmlns="http://www.w3.org/2000/svg"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="2"
									class="arrow h-3.5 w-3.5"
								>
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

{#if showCreate}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-brand-navy/40 p-4">
		<div class="w-full max-w-2xl rounded-xl bg-white p-6 shadow-sm">
			<h2 class="m-0 mb-1 font-headline text-lg font-semibold text-brand-navy">New MEL project</h2>
			<p class="m-0 mb-4 font-body text-sm text-brand-steel">
				You will own this project and can add members and MEL plans later.
			</p>
			{#if error}
				<p class="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 font-body text-sm text-red-700">{error}</p>
			{/if}
			<label class="mb-1 block font-body text-sm font-medium text-brand-navy" for="mel-proj-name">
				Project name
			</label>
			<input
				id="mel-proj-name"
				type="text"
				class="mb-5 w-full rounded border border-brand-navy/20 px-3 py-2 font-body outline-none focus:border-[#1b75e0] focus:ring-2 focus:ring-[#1b75e0]/20"
				placeholder="e.g. Kolar watershed MEL"
				bind:value={name}
				onkeydown={(e) => {
					if (e.key === 'Enter') {
						e.preventDefault();
						handleCreate();
					}
				}}
			/>
			<div class="flex justify-end gap-2">
				<button type="button" class="action-btn" onclick={() => (showCreate = false)}>Cancel</button>
				<button
					type="button"
					class="rounded bg-[#1b75e0] px-4 py-2 font-body text-sm font-medium text-white hover:bg-[#1565c0] disabled:opacity-50"
					disabled={creating || !name.trim()}
					onclick={handleCreate}
				>
					{creating ? 'Creating…' : 'Create'}
				</button>
			</div>
		</div>
	</div>
{/if}

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
		box-shadow:
			0 1px 0 rgba(255, 255, 255, 0.8) inset,
			0 12px 28px -20px rgba(20, 40, 60, 0.35);
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
		background: color-mix(in srgb, var(--accent) 10%, white);
	}
	.menu-panel {
		position: absolute;
		top: 3.25rem;
		right: 1rem;
		z-index: 20;
		min-width: 140px;
		border-radius: 12px;
		border: 1px solid rgba(20, 40, 60, 0.1);
		background: white;
		padding: 0.25rem 0;
		box-shadow: 0 12px 28px -16px rgba(20, 40, 60, 0.4);
	}
	.menu-item {
		display: block;
		width: 100%;
		border: 0;
		background: transparent;
		padding: 0.5rem 0.75rem;
		text-align: left;
		font-size: 0.875rem;
		cursor: pointer;
	}
	.menu-item-danger {
		color: #b91c1c;
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
