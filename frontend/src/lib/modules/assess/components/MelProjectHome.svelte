<script>
	import { appPath } from '$lib/shared/paths.js';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';
	import { itemPath } from '$lib/shared/slug.js';
	import { assessCrumbs } from '$lib/modules/assess/breadcrumbs.js';
	import {
		createMelPlan,
		deleteMelPlan,
		fetchMelInterventions,
		fetchMelPlans
	} from '$lib/modules/assess/mel-api';

	/** @type {{ project: any, projects?: any[] }} */
	let { project, projects = [] } = $props();

	let plans = $state([]);
	let interventions = $state([]);
	let loading = $state(true);
	let error = $state('');
	let mounted = $state(false);
	let showCreate = $state(false);
	let planName = $state('');
	let interventionSlug = $state('');
	let creating = $state(false);
	let deletingId = $state(null);
	let openMenuId = $state(null);

	const ASSESS_BLUE = '#1b75e0';
	const slugBase = $derived(itemPath('/assess', project, projects));
	const crumbs = $derived(assessCrumbs({ projects, project }));

	onMount(() => {
		mounted = true;
		load();
		document.addEventListener('click', () => (openMenuId = null));
	});

	async function load() {
		loading = true;
		error = '';
		try {
			const [plansRes, intRes] = await Promise.all([
				fetchMelPlans(project.id),
				fetchMelInterventions()
			]);
			plans = plansRes.plans ?? [];
			interventions = intRes.interventions ?? [];
			if (!interventionSlug && interventions.length) {
				interventionSlug = interventions[0].slug;
			}
		} catch (err) {
			error = String(err);
		} finally {
			loading = false;
		}
	}

	function interventionName(slug) {
		return interventions.find((i) => i.slug === slug)?.name || slug || '—';
	}

	function planPath(plan) {
		return `${slugBase}/plans/${plan.id}`;
	}

	function openCreate() {
		showCreate = true;
		error = '';
		planName = '';
	}

	/** @param {PointerEvent & { currentTarget: HTMLElement }} e */
	function handlePointer(e) {
		const rect = e.currentTarget.getBoundingClientRect();
		e.currentTarget.style.setProperty('--mx', `${e.clientX - rect.left}px`);
		e.currentTarget.style.setProperty('--my', `${e.clientY - rect.top}px`);
	}

	async function handleCreate() {
		if (!planName.trim() || !interventionSlug) return;
		creating = true;
		error = '';
		try {
			const plan = await createMelPlan(project.id, {
				name: planName.trim(),
				interventionSlug
			});
			showCreate = false;
			planName = '';
			await load();
			goto(`${planPath(plan)}/new`);
		} catch (err) {
			error = String(err);
		} finally {
			creating = false;
		}
	}

	async function handleDelete(plan) {
		if (!confirm(`Delete MEL plan “${plan.name}”? Forms under it will be removed from this project.`))
			return;
		deletingId = plan.id;
		error = '';
		try {
			await deleteMelPlan(project.id, plan.id);
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
		fullProjectTitle
		{crumbs}
	>
		<button type="button" onclick={() => goto(appPath('/assess'))}>All projects</button>
		<button type="button" onclick={() => goto(`${slugBase}/members`)}>Members</button>
	</ModuleHeader>

	<main class="relative z-10 flex-1 overflow-auto p-6">
		<div class="page-head mb-6 flex flex-wrap items-center justify-between gap-3">
			<div>
				<h1 class="m-0 font-display text-2xl text-[#1a2530]">{project.name}</h1>
				<p class="m-0 mt-1 font-body text-sm text-[#56646f]">
					One plan per intervention · {plans.length} plan{plans.length === 1 ? '' : 's'}
				</p>
			</div>
			<button type="button" class="add-btn" onclick={openCreate}>Add MEL plan</button>
		</div>

		{#if error}
			<p class="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 font-body text-sm text-red-700">
				{error}
			</p>
		{/if}

		{#if loading}
			<p class="font-body text-brand-steel">Loading plans…</p>
		{:else if plans.length === 0}
			<div
				class="rounded-xl border border-dashed border-brand-navy/20 bg-gray-50 px-6 py-10 text-center font-body text-sm text-[#56646f]"
			>
				No MEL plans yet.
				<button type="button" class="text-[#1b75e0] underline" onclick={openCreate}>Add a plan</button>
				to get started.
			</div>
		{:else}
			<div
				class="grid gap-6"
				style="grid-template-columns: repeat(auto-fill, minmax(min(100%, 20rem), 1fr));"
			>
				{#each plans as plan, i (plan.id)}
					<div
						class="card group"
						class:in={mounted}
						style="--accent: {ASSESS_BLUE}; --delay: {i * 70}ms;"
						role="button"
						tabindex="0"
						onpointermove={handlePointer}
						onclick={() => goto(planPath(plan))}
						onkeydown={(e) => {
							if (e.key === 'Enter' || e.key === ' ') {
								e.preventDefault();
								goto(planPath(plan));
							}
						}}
					>
						<span class="card-spotlight" aria-hidden="true"></span>
						<span class="card-topline" aria-hidden="true"></span>
						<div class="relative z-10 flex w-full flex-col items-start gap-3">
							<div class="flex w-full items-start justify-between gap-2">
								<div class="icon-wrap">
									<span class="text-sm font-semibold text-[color:var(--accent)]">MEL</span>
								</div>
								<button
									type="button"
									class="menu-btn"
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
									class="absolute top-12 right-4 z-20 min-w-[120px] rounded-lg border border-brand-navy/10 bg-white py-1 shadow-lg"
									role="menu"
									tabindex="-1"
									onclick={(e) => e.stopPropagation()}
								>
									<button
										type="button"
										class="menu-item"
										role="menuitem"
										disabled={deletingId === plan.id}
										onclick={() => handleDelete(plan)}
									>
										{deletingId === plan.id ? 'Deleting…' : 'Delete'}
									</button>
								</div>
							{/if}
							<h3 class="card-title m-0 font-display text-xl">{plan.name}</h3>
							<p class="card-desc m-0 text-sm">{interventionName(plan.intervention_slug)}</p>
							<p class="m-0 text-xs text-brand-steel">
								{plan.form_count ?? 0} form{(plan.form_count ?? 0) === 1 ? '' : 's'}
								· Updated {formatDate(plan.updated_at)}
							</p>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</main>
</div>

{#if showCreate}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-brand-navy/40 p-4">
		<div class="w-full max-w-2xl rounded-xl bg-white p-6 shadow-sm">
			<h2 class="m-0 mb-1 font-headline text-lg font-semibold text-brand-navy">New MEL plan</h2>
			<p class="m-0 mb-4 font-body text-sm text-brand-steel">Each plan is bound to one intervention.</p>
			<label class="mb-1 block font-body text-sm font-medium text-brand-navy" for="mel-plan-name">
				Plan name
			</label>
			<input
				id="mel-plan-name"
				type="text"
				class="mb-4 w-full rounded border border-brand-navy/20 px-3 py-2 font-body outline-none focus:border-[#1b75e0] focus:ring-2 focus:ring-[#1b75e0]/20"
				placeholder="e.g. Check dams – Kolar"
				bind:value={planName}
			/>
			<label class="mb-1 block font-body text-sm font-medium text-brand-navy" for="mel-plan-int">
				Intervention
			</label>
			<select
				id="mel-plan-int"
				class="mb-5 w-full rounded border border-brand-navy/20 px-2 py-1.5 font-body text-sm text-brand-navy outline-none focus:border-brand-navy/40"
				bind:value={interventionSlug}
			>
				{#each interventions as item (item.slug)}
					<option value={item.slug}>{item.name}</option>
				{/each}
			</select>
			<div class="flex justify-end gap-2">
				<button type="button" class="action-btn" onclick={() => (showCreate = false)}>Cancel</button>
				<button
					type="button"
					class="rounded bg-[#1b75e0] px-4 py-2 font-body text-sm font-medium text-white hover:bg-[#1565c0] disabled:opacity-50"
					disabled={creating || !planName.trim() || !interventionSlug}
					onclick={handleCreate}
				>
					{creating ? 'Creating…' : 'Continue to design'}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.add-btn {
		cursor: pointer;
		border-radius: 0.5rem;
		border: 1px solid color-mix(in srgb, #1b75e0 40%, transparent);
		background: #1b75e0;
		padding: 0.55rem 1rem;
		font-family: var(--font-body);
		font-size: 0.875rem;
		font-weight: 600;
		color: white;
	}
	.add-btn:hover {
		background: #1565c0;
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
		color: #1a2530;
	}
	.menu-item {
		display: block;
		width: 100%;
		border: 0;
		background: transparent;
		padding: 0.5rem 0.75rem;
		text-align: left;
		font-family: var(--font-body);
		font-size: 0.875rem;
		color: #b91c1c;
		cursor: pointer;
	}
	.menu-item:hover {
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
