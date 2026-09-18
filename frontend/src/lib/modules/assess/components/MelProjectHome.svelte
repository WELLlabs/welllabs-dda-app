<script>
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';
	import { itemPath } from '$lib/shared/slug.js';
	import { assessCrumbs } from '$lib/modules/assess/breadcrumbs.js';
	import {
		createMelPlan,
		deleteMelPlan,
		fetchImplementationDashboard,
		fetchMelInterventions,
		fetchMelPlans,
		saveMelPlan,
		updateMelProject
	} from '$lib/modules/assess/mel-api';

	/** @type {{ project: any, projects?: any[] }} */
	let { project, projects = [] } = $props();

	let plans = $state([]);
	let implementations = $state([]);
	let interventions = $state([]);
	let loading = $state(true);
	let error = $state('');
	let mounted = $state(false);
	/** @type {null | 'plan' | 'implementation'} */
	let createKind = $state(null);
	let itemName = $state('');
	let interventionSlug = $state('farm-pond');
	let creating = $state(false);
	let saving = $state(false);
	let deletingId = $state(null);
	/** @type {string | null} */
	let openMenuId = $state(null);
	/** @type {null | { type: 'project' } | { type: 'plan', plan: any }} */
	let editing = $state(null);
	let editName = $state('');
	let editDescription = $state('');
	let implStats = $state({
		intervention_count: 0,
		asset_count: 0,
		volumetric_storage_m3: 0,
		sm_water_savings_m3: 0,
		cumulative_rainfall_mm: 0
	});

	const PLAN_ACCENT = '#1b75e0';
	const IMPL_ACCENT = '#0f766e';
	const slugBase = $derived(itemPath('/assess', project, projects));
	const crumbs = $derived(assessCrumbs({ projects, project }));
	const tab = $derived(
		page.url.searchParams.get('tab') === 'implementation' ? 'implementation' : 'plans'
	);

	onMount(() => {
		mounted = true;
		load();
	});

	async function load() {
		loading = true;
		error = '';
		try {
			const [plansRes, intRes] = await Promise.all([
				fetchMelPlans(project.id),
				fetchMelInterventions()
			]);
			const all = plansRes.plans ?? [];
			plans = all.filter((p) => (p.kind || 'plan') === 'plan');
			implementations = all.filter((p) => p.kind === 'implementation');
			interventions = (intRes.interventions ?? []).filter(
				(i) => i.from_mapping && (i.outcome_count || 0) > 0
			);
			const farm = interventions.find((i) => i.slug === 'farm-pond');
			if (farm) interventionSlug = farm.slug;
			else if (interventions.length) interventionSlug = interventions[0].slug;
			void refreshStats(implementations);
		} catch (err) {
			error = String(err);
		} finally {
			loading = false;
		}
	}

	/** @param {any[]} impls */
	async function refreshStats(impls) {
		implStats = {
			intervention_count: impls.length,
			asset_count: impls.reduce((sum, p) => sum + (p.asset_count || 0), 0),
			volumetric_storage_m3: 0,
			sm_water_savings_m3: 0,
			cumulative_rainfall_mm: 0
		};
		if (!impls.length) return;
		const dashes = await Promise.all(
			impls.map((p) => fetchImplementationDashboard(project.id, p.id).catch(() => null))
		);
		let storage = 0;
		let smSavings = 0;
		let rain = 0;
		let assets = 0;
		for (const dash of dashes) {
			if (!dash?.totals) continue;
			assets += dash.totals.asset_count || 0;
			storage += dash.totals.volumetric_storage_m3 || 0;
			smSavings += dash.totals.sm_water_savings_m3 || 0;
			rain += dash.totals.cumulative_rainfall_mm || 0;
		}
		implStats = {
			intervention_count: impls.length,
			asset_count: assets,
			volumetric_storage_m3: storage,
			sm_water_savings_m3: smSavings,
			cumulative_rainfall_mm: rain
		};
	}

	function interventionName(slug) {
		return interventions.find((i) => i.slug === slug)?.name || slug || '—';
	}

	function planPath(plan) {
		return `${slugBase}/plans/${plan.id}`;
	}

	function setTab(next) {
		createKind = null;
		editing = null;
		openMenuId = null;
		goto(`${slugBase}?tab=${next}`, { replaceState: true, noScroll: true, keepFocus: true });
	}

	function openCreate(kind) {
		createKind = kind;
		editing = null;
		error = '';
		itemName = '';
		openMenuId = null;
	}

	async function handleCreate() {
		if (!itemName.trim() || !interventionSlug || !createKind) return;
		const kind = createKind;
		creating = true;
		error = '';
		try {
			const plan = await createMelPlan(project.id, {
				name: itemName.trim(),
				interventionSlug,
				kind
			});
			createKind = null;
			itemName = '';
			goto(kind === 'implementation' ? `${planPath(plan)}/new?forms=1` : `${planPath(plan)}/new`);
		} catch (err) {
			error = String(err);
		} finally {
			creating = false;
		}
	}

	function openEditProject() {
		createKind = null;
		openMenuId = null;
		editing = { type: 'project' };
		editName = project.name || '';
		editDescription = project.description || '';
		error = '';
	}

	function openEditPlan(plan) {
		createKind = null;
		openMenuId = null;
		editing = { type: 'plan', plan };
		editName = plan.name || '';
		editDescription = '';
		error = '';
	}

	function closeEdit() {
		editing = null;
		editName = '';
		editDescription = '';
	}

	async function handleSaveEdit() {
		if (!editing || !editName.trim() || saving) return;
		saving = true;
		error = '';
		try {
			if (editing.type === 'project') {
				const updated = await updateMelProject(project.id, {
					name: editName.trim(),
					description: editDescription.trim()
				});
				closeEdit();
				const nextProjects = projects.map((p) => (p.id === updated.id ? { ...p, ...updated } : p));
				goto(itemPath('/assess', updated, nextProjects) + `?tab=${tab}`, { replaceState: true });
			} else {
				await saveMelPlan(project.id, editing.plan.id, { name: editName.trim() });
				closeEdit();
				await load();
			}
		} catch (err) {
			error = String(err);
		} finally {
			saving = false;
		}
	}

	async function handleDelete(plan) {
		const label = plan.kind === 'implementation' ? 'intervention' : 'MEL plan';
		if (!confirm(`Delete ${label} “${plan.name}”?`)) return;
		deletingId = plan.id;
		openMenuId = null;
		error = '';
		try {
			await deleteMelPlan(project.id, plan.id);
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

	function fmt(v, digits = 2) {
		if (v == null || Number.isNaN(Number(v))) return '—';
		return Number(v).toLocaleString(undefined, { maximumFractionDigits: digits });
	}

	function handlePointer(e) {
		const el = e.currentTarget;
		if (!(el instanceof HTMLElement)) return;
		const rect = el.getBoundingClientRect();
		el.style.setProperty('--mx', `${e.clientX - rect.left}px`);
		el.style.setProperty('--my', `${e.clientY - rect.top}px`);
	}

	function openItem(plan) {
		openMenuId = null;
		goto(planPath(plan));
	}
</script>

<div class="flex h-svh max-h-svh flex-col overflow-hidden bg-transparent font-body">
	<ModuleHeader title="Assess" titleHref="/assess" wide crumbs={crumbs}>
		<button type="button" onclick={() => goto(`${slugBase}/members`)}>Members</button>
		<button type="button" onclick={openEditProject}>Edit project</button>
		{#if tab === 'plans'}
			<button type="button" class="filled" onclick={() => openCreate('plan')}>New plan</button>
		{:else}
			<button type="button" class="filled" onclick={() => openCreate('implementation')}
				>Add intervention</button
			>
		{/if}
	</ModuleHeader>

	<div class="hub min-h-0 flex-1">
		<aside class="hub-nav" aria-label="Project sections">
			<button
				type="button"
				class="hub-tab"
				class:active={tab === 'plans'}
				onclick={() => setTab('plans')}
			>
				Plans
			</button>
			<button
				type="button"
				class="hub-tab"
				class:active={tab === 'implementation'}
				onclick={() => setTab('implementation')}
			>
				Implementation
			</button>
		</aside>

		<main class="hub-main">
			{#if error && !createKind && !editing}
				<p class="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
					{error}
				</p>
			{/if}

			{#if loading}
				<p class="text-brand-steel">Loading…</p>
			{:else if editing}
				<section
					class="mx-auto max-w-lg rounded-[22px] border border-[rgba(20,40,60,0.08)] bg-white/90 p-6 shadow-sm"
				>
					<h2 class="m-0 font-display text-xl text-brand-navy">
						{editing.type === 'project'
							? 'Edit project'
							: editing.plan.kind === 'implementation'
								? 'Edit intervention'
								: 'Edit plan'}
					</h2>
					{#if error}
						<p class="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
							{error}
						</p>
					{/if}
					<label class="mt-4 block text-sm font-medium text-brand-navy" for="mel-edit-name">Name</label>
					<input
						id="mel-edit-name"
						class="mt-1 w-full rounded-lg border border-brand-navy/20 px-3 py-2 text-sm"
						bind:value={editName}
					/>
					{#if editing.type === 'project'}
						<label class="mt-3 block text-sm font-medium text-brand-navy" for="mel-edit-desc"
							>Description</label
						>
						<textarea
							id="mel-edit-desc"
							class="mt-1 w-full rounded-lg border border-brand-navy/20 px-3 py-2 text-sm"
							rows="3"
							bind:value={editDescription}
						></textarea>
					{/if}
					<div class="mt-5 flex gap-2">
						<button
							type="button"
							class="rounded-lg bg-brand-blue px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
							disabled={saving || !editName.trim()}
							onclick={handleSaveEdit}
						>
							{saving ? 'Saving…' : 'Save'}
						</button>
						<button
							type="button"
							class="rounded-lg border border-brand-navy/20 px-4 py-2 text-sm"
							onclick={closeEdit}
						>
							Cancel
						</button>
					</div>
				</section>
			{:else if createKind}
				<section
					class="mx-auto max-w-lg rounded-[22px] border border-[rgba(20,40,60,0.08)] bg-white/90 p-6 shadow-sm"
				>
					<h2 class="m-0 font-display text-xl text-brand-navy">
						{createKind === 'implementation' ? 'Add intervention' : 'New plan'}
					</h2>
					{#if error}
						<p class="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
							{error}
						</p>
					{/if}
					<label class="mt-4 block text-sm font-medium text-brand-navy" for="mel-item-name">Name</label>
					<input
						id="mel-item-name"
						class="mt-1 w-full rounded-lg border border-brand-navy/20 px-3 py-2 text-sm"
						bind:value={itemName}
						placeholder={createKind === 'implementation'
							? interventionSlug === 'pmds'
								? 'e.g. Medak PMDS plots'
								: 'e.g. Medak farm pond'
							: interventionSlug === 'pmds'
								? 'e.g. PMDS MEL plan'
								: 'e.g. Farm pond MEL plan'}
					/>
					<label class="mt-3 block text-sm font-medium text-brand-navy" for="mel-intervention"
						>Intervention type</label
					>
					<select
						id="mel-intervention"
						class="mt-1 w-full rounded-lg border border-brand-navy/20 px-3 py-2 text-sm"
						bind:value={interventionSlug}
					>
						{#each interventions as i (i.slug)}
							<option value={i.slug}>{i.name}</option>
						{/each}
					</select>
					<div class="mt-5 flex gap-2">
						<button
							type="button"
							class="rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
							style="background: {createKind === 'implementation' ? IMPL_ACCENT : PLAN_ACCENT}"
							disabled={creating || !itemName.trim()}
							onclick={handleCreate}
						>
							{creating ? 'Creating…' : 'Continue'}
						</button>
						<button
							type="button"
							class="rounded-lg border border-brand-navy/20 px-4 py-2 text-sm"
							onclick={() => (createKind = null)}
						>
							Cancel
						</button>
					</div>
				</section>
			{:else if tab === 'plans'}
				<header class="pane-intro">
					<p class="pane-kicker" style="color: {PLAN_ACCENT}">Plans</p>
					<h1 class="pane-title">{project.name}</h1>
					<p class="pane-sub">MEL plans in this project.</p>
				</header>

				<div
					class="grid gap-6"
					style="grid-template-columns: repeat(auto-fill, minmax(min(100%, 20rem), 1fr));"
				>
					{#each plans as plan, i (plan.id)}
						<div
							class="card group"
							class:in={mounted}
							style="--accent: {PLAN_ACCENT}; --delay: {i * 70}ms;"
							role="button"
							tabindex="0"
							onpointermove={handlePointer}
							onclick={() => openItem(plan)}
							onkeydown={(e) => {
								if (e.key === 'Enter' || e.key === ' ') {
									e.preventDefault();
									openItem(plan);
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
											<path d="M7 3h7l3 3v15H7V3z" stroke-linecap="round" stroke-linejoin="round" />
											<path d="M9 9h6M9 13h6M9 17h4" stroke-linecap="round" />
										</svg>
									</div>
									<button
										type="button"
										class="menu-btn"
										aria-label="Plan actions"
										onclick={(e) => {
											e.stopPropagation();
											openMenuId = openMenuId === plan.id ? null : plan.id;
										}}
									>
										···
									</button>
								</div>
								{#if openMenuId === plan.id}
									<div
										class="menu-panel"
										role="menu"
										tabindex="-1"
										onclick={(e) => e.stopPropagation()}
										onkeydown={(e) => e.stopPropagation()}
									>
										<button
											type="button"
											class="menu-item"
											role="menuitem"
											onclick={() => openEditPlan(plan)}
										>
											Edit
										</button>
										<button
											type="button"
											class="menu-item"
											role="menuitem"
											onclick={() => goto(`${planPath(plan)}/new`)}
										>
											Edit plan
										</button>
										<button
											type="button"
											class="menu-item menu-item-danger"
											role="menuitem"
											disabled={deletingId === plan.id}
											onclick={() => handleDelete(plan)}
										>
											{deletingId === plan.id ? 'Deleting…' : 'Delete'}
										</button>
									</div>
								{/if}
								<p class="kind-pill kind-plan m-0">Plan</p>
								<h3 class="card-title m-0 font-display text-xl">{plan.name}</h3>
								<p class="card-desc m-0 text-sm">{interventionName(plan.intervention_slug)}</p>
								<p class="m-0 font-mono text-[11px] tracking-wide text-[#6b7885]">
									Updated {formatDate(plan.updated_at)}
								</p>
								<span class="cta mt-1 font-mono text-[12px]">
									Open plan
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

				{#if plans.length === 0}
					<p class="mt-4 text-sm text-[#56646f]">No plans yet. Use New plan to create one.</p>
				{/if}
			{:else}
				<header class="pane-intro">
					<p class="pane-kicker" style="color: {IMPL_ACCENT}">Implementation</p>
					<h1 class="pane-title">{project.name}</h1>
					<p class="pane-sub">Interventions being monitored in this project.</p>
				</header>

				<div class="impl-split">
					<aside class="stats-col" aria-label="Project stats">
						<div class="stat-card">
							<p class="stat-label">Interventions</p>
							<p class="stat-value">{implStats.intervention_count}</p>
						</div>
						<div class="stat-card">
							<p class="stat-label">Assets</p>
							<p class="stat-value">{implStats.asset_count}</p>
						</div>
						<div class="stat-card">
							<p class="stat-label">Volumetric storage</p>
							<p class="stat-value">{fmt(implStats.volumetric_storage_m3)} m³</p>
						</div>
						<div class="stat-card">
							<p class="stat-label">SM water savings</p>
							<p class="stat-value">{fmt(implStats.sm_water_savings_m3)} m³</p>
						</div>
						<div class="stat-card">
							<p class="stat-label">Cumulative rainfall</p>
							<p class="stat-value">{fmt(implStats.cumulative_rainfall_mm)} mm</p>
						</div>
					</aside>

					<div class="assets-col">
						<div
							class="grid gap-6"
							style="grid-template-columns: repeat(auto-fill, minmax(min(100%, 20rem), 1fr));"
						>
					{#each implementations as plan, i (plan.id)}
						<div
							class="card group"
							class:in={mounted}
							style="--accent: {IMPL_ACCENT}; --delay: {i * 70}ms;"
							role="button"
							tabindex="0"
							onpointermove={handlePointer}
							onclick={() => openItem(plan)}
							onkeydown={(e) => {
								if (e.key === 'Enter' || e.key === ' ') {
									e.preventDefault();
									openItem(plan);
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
									<button
										type="button"
										class="menu-btn"
										aria-label="Intervention actions"
										onclick={(e) => {
											e.stopPropagation();
											openMenuId = openMenuId === plan.id ? null : plan.id;
										}}
									>
										···
									</button>
								</div>
								{#if openMenuId === plan.id}
									<div
										class="menu-panel"
										role="menu"
										tabindex="-1"
										onclick={(e) => e.stopPropagation()}
										onkeydown={(e) => e.stopPropagation()}
									>
										<button
											type="button"
											class="menu-item"
											role="menuitem"
											onclick={() => openEditPlan(plan)}
										>
											Edit
										</button>
										<button
											type="button"
											class="menu-item"
											role="menuitem"
											onclick={() => goto(`${planPath(plan)}/new?forms=1`)}
										>
											Edit forms
										</button>
										<button
											type="button"
											class="menu-item menu-item-danger"
											role="menuitem"
											disabled={deletingId === plan.id}
											onclick={() => handleDelete(plan)}
										>
											{deletingId === plan.id ? 'Deleting…' : 'Delete'}
										</button>
									</div>
								{/if}
								<p class="kind-pill kind-impl m-0">Intervention</p>
								<h3 class="card-title m-0 font-display text-xl">{plan.name}</h3>
								<p class="card-desc m-0 text-sm">
									{interventionName(plan.intervention_slug)} · {plan.asset_count || 0} assets
								</p>
								<p class="m-0 font-mono text-[11px] tracking-wide text-[#6b7885]">
									Updated {formatDate(plan.updated_at)}
								</p>
								<span class="cta mt-1 font-mono text-[12px]">
									View assets
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

				{#if implementations.length === 0}
					<p class="mt-4 text-sm text-[#56646f]">
						No interventions yet. Use Add intervention to start monitoring.
					</p>
				{/if}
					</div>
				</div>
			{/if}
		</main>
	</div>
</div>

<style>
	.hub {
		display: grid;
		grid-template-columns: 13.5rem minmax(0, 1fr);
		min-height: 0;
	}
	.hub-nav {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		padding: 1rem 0.75rem 1.25rem 1rem;
		border-right: 1px solid rgba(20, 40, 60, 0.08);
		background: rgba(255, 255, 255, 0.55);
	}
	.hub-tab {
		display: block;
		width: 100%;
		cursor: pointer;
		border: 0;
		border-radius: 0.7rem;
		background: transparent;
		padding: 0.65rem 0.8rem;
		text-align: left;
		font-size: 0.9rem;
		font-weight: 600;
		color: #56646f;
	}
	.hub-tab:hover {
		background: color-mix(in srgb, #1b75e0 8%, white);
		color: #1a2530;
	}
	.hub-tab.active {
		background: color-mix(in srgb, #1b75e0 14%, white);
		color: #0d2c4c;
	}
	.hub-main {
		min-width: 0;
		overflow: auto;
		padding: 1.25rem 1.5rem 2rem;
	}
	.pane-intro {
		margin-bottom: 1.15rem;
	}
	.pane-kicker {
		margin: 0;
		font-size: 0.7rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
	}
	.pane-title {
		margin: 0.2rem 0 0;
		font-family: var(--font-headline);
		font-size: 1.35rem;
		font-weight: 650;
		color: #1a2530;
	}
	.pane-sub {
		margin: 0.2rem 0 0;
		font-size: 0.85rem;
		color: #56646f;
	}
	.impl-split {
		display: grid;
		grid-template-columns: minmax(13rem, 15.5rem) minmax(0, 1fr);
		gap: 1rem;
		align-items: start;
		min-height: 0;
	}
	.stats-col {
		display: flex;
		flex-direction: column;
		gap: 0.65rem;
		min-width: 0;
	}
	.assets-col {
		min-width: 0;
	}
	.stat-card {
		border-radius: 0.9rem;
		border: 1px solid rgba(20, 40, 60, 0.08);
		background: white;
		padding: 0.85rem 1rem;
	}
	.stat-label {
		margin: 0;
		font-size: 0.68rem;
		font-weight: 700;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		color: #56646f;
	}
	.stat-value {
		margin: 0.25rem 0 0;
		font-size: 1.2rem;
		font-weight: 700;
		color: #1a2530;
		font-variant-numeric: tabular-nums;
	}
	.kind-pill {
		display: inline-flex;
		border-radius: 999px;
		padding: 0.15rem 0.5rem;
		font-size: 0.65rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
	}
	.kind-plan {
		background: color-mix(in srgb, #1b75e0 14%, white);
		color: #1565c0;
	}
	.kind-impl {
		background: color-mix(in srgb, #0f766e 14%, white);
		color: #0f766e;
	}
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
	.card-desc {
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
		color: #1a2530;
	}
	.menu-item:hover {
		background: #f4f7fa;
	}
	.menu-item-danger {
		color: #b91c1c;
	}
	.menu-item-danger:hover {
		background: #fef2f2;
	}
	@media (max-width: 900px) {
		.hub {
			grid-template-columns: 1fr;
			grid-template-rows: auto minmax(0, 1fr);
		}
		.hub-nav {
			flex-direction: row;
			border-right: 0;
			border-bottom: 1px solid rgba(20, 40, 60, 0.08);
			padding: 0.65rem 1rem;
		}
		.hub-tab {
			width: auto;
		}
		.impl-split {
			grid-template-columns: 1fr;
		}
		.stats-col {
			display: grid;
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.card {
			transition: none;
			opacity: 1;
			transform: none;
		}
	}
</style>
