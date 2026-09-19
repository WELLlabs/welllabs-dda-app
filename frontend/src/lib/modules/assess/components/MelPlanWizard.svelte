<script>
	import { onMount } from 'svelte';
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';
	import {
		exportMelPlanDocx,
		fetchMelIntervention,
		fetchMelLogframe,
		fetchMelPlan,
		saveMelPlan
	} from '$lib/modules/assess/mel-api';
	import MelLogFrameView from '$lib/modules/assess/components/MelLogFrameView.svelte';

	/** @type {{
	 *   onBack: () => void,
	 *   crumbs?: any[],
	 *   projectId: string,
	 *   planId: string,
	 *   projectName?: string,
	 *   planName?: string,
	 *   interventionSlug: string,
	 *   initialOutcomeIds?: string[],
	 *   initialPlanJson?: Record<string, any>,
	 *   startStep?: number
	 * }} */
	let {
		onBack,
		crumbs = [],
		projectId,
		planId,
		projectName = '',
		planName = '',
		interventionSlug,
		initialOutcomeIds = [],
		initialPlanJson = null,
		startStep = 0
	} = $props();

	/** 0 = choose outcomes, 1 = full plan */
	let step = $state(Number(startStep) > 0 ? 1 : 0);
	let loading = $state(true);
	let saving = $state(false);
	let exporting = $state(false);
	let loadingPlan = $state(false);
	let error = $state('');
	let intervention = $state(null);
	let selectedOutcomeIds = $state([...initialOutcomeIds]);
	/** @type {Record<string, any>} */
	let savedPlanJson = $state({ ...(initialPlanJson || {}) });
	/** @type {any} */
	let logframe = $state(null);

	const selectedOutcomes = $derived(
		(intervention?.outcomes || []).filter((o) => selectedOutcomeIds.includes(o.id))
	);

	onMount(() => {
		void load();
	});

	async function load() {
		loading = true;
		error = '';
		try {
			const [intv, plan] = await Promise.all([
				fetchMelIntervention(interventionSlug),
				fetchMelPlan(projectId, planId).catch(() => null)
			]);
			intervention = intv;
			const pj = plan?.plan_json || initialPlanJson || {};
			savedPlanJson = { ...pj };
			if (Array.isArray(pj.outcome_ids) && pj.outcome_ids.length) {
				selectedOutcomeIds = [...pj.outcome_ids];
			}
			if (step === 1 && selectedOutcomeIds.length) {
				await loadLogframe();
			} else {
				step = 0;
			}
		} catch (err) {
			error = String(err);
		} finally {
			loading = false;
		}
	}

	function planPayload() {
		return {
			...savedPlanJson,
			outcome_ids: selectedOutcomeIds
		};
	}

	function toggleOutcome(id) {
		if (selectedOutcomeIds.includes(id)) {
			selectedOutcomeIds = selectedOutcomeIds.filter((x) => x !== id);
		} else {
			selectedOutcomeIds = [...selectedOutcomeIds, id];
		}
	}

	async function loadLogframe() {
		loadingPlan = true;
		try {
			const res = await fetchMelLogframe({
				interventionSlug,
				outcomeIds: selectedOutcomeIds,
				projectId,
				planId
			});
			logframe = res?.logframe || null;
		} catch {
			logframe = null;
		} finally {
			loadingPlan = false;
		}
	}

	async function goToPlan() {
		if (!selectedOutcomeIds.length) {
			error = 'Select at least one outcome.';
			return;
		}
		saving = true;
		error = '';
		try {
			const payload = planPayload();
			await saveMelPlan(projectId, planId, {
				outcomeIds: selectedOutcomeIds,
				planJson: payload
			});
			savedPlanJson = payload;
			step = 1;
			await loadLogframe();
		} catch (err) {
			error = String(err);
		} finally {
			saving = false;
		}
	}

	async function handleExport() {
		exporting = true;
		error = '';
		try {
			const payload = planPayload();
			await saveMelPlan(projectId, planId, {
				outcomeIds: selectedOutcomeIds,
				planJson: payload
			});
			savedPlanJson = payload;
			const { blob, filename } = await exportMelPlanDocx(projectId, planId);
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = filename;
			document.body.appendChild(a);
			a.click();
			a.remove();
			URL.revokeObjectURL(url);
		} catch (err) {
			error = String(err);
		} finally {
			exporting = false;
		}
	}
</script>

<div class="flex h-svh max-h-svh flex-col overflow-hidden bg-transparent font-body">
	<ModuleHeader title="Assess" titleHref="/assess" wide {crumbs} />

	{#if step === 0}
		<main class="mx-auto flex min-h-0 w-full max-w-6xl flex-1 flex-col gap-3 px-4 py-3 sm:px-6">
			<div class="flex shrink-0 items-center justify-between gap-3">
				<div class="min-w-0">
					<p class="m-0 text-[10px] uppercase tracking-wide text-brand-steel">MEL Plan</p>
					<h1 class="m-0 truncate font-headline text-lg font-semibold text-brand-navy">{planName}</h1>
					<p class="m-0 truncate text-xs text-brand-steel">{intervention?.name || interventionSlug}</p>
				</div>
				<button type="button" class="shrink-0 text-sm text-brand-blue underline" onclick={onBack}
					>Back</button
				>
			</div>

			{#if error}
				<p
					class="m-0 shrink-0 rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs text-red-700"
				>
					{error}
				</p>
			{/if}

			{#if loading}
				<p class="text-sm text-brand-steel">Loading catalog…</p>
			{:else}
				<section class="phase-panel">
					<header class="phase-head">
						<div>
							<h2>Select outcomes</h2>
							<p>Choose outcomes for this MEL plan. Indicators for the selection are listed on the right.</p>
						</div>
					</header>
					<div class="phase-body two-col">
						<div>
							<p class="section-label">Outcomes</p>
							<ul class="outcome-list">
								{#each intervention?.outcomes || [] as outcome (outcome.id)}
									<li>
										<label class="outcome-row">
											<input
												type="checkbox"
												checked={selectedOutcomeIds.includes(outcome.id)}
												onchange={() => toggleOutcome(outcome.id)}
											/>
											<span>
												<span class="outcome-title">{outcome.title}</span>
												{#if outcome.assumptions}
													<span class="outcome-sub">{outcome.assumptions}</span>
												{/if}
											</span>
										</label>
									</li>
								{/each}
							</ul>
						</div>
						<div>
							<p class="section-label">Indicators for selection</p>
							{#if !selectedOutcomes.length}
								<p class="muted">Select outcomes to preview indicators.</p>
							{:else}
								{#each selectedOutcomes as outcome (outcome.id)}
									<div class="ind-block">
										<p class="ind-title">{outcome.title}</p>
										{#if outcome.indicators?.length}
											<ul class="ind-list">
												{#each outcome.indicators as ind}
													<li>{ind.title}</li>
												{/each}
											</ul>
										{:else}
											<p class="muted">No indicators listed</p>
										{/if}
									</div>
								{/each}
							{/if}
						</div>
					</div>
					<footer class="phase-foot">
						<button
							type="button"
							class="btn primary"
							disabled={saving || !selectedOutcomeIds.length}
							onclick={goToPlan}
						>
							{saving ? 'Saving…' : 'Continue to MEL plan'}
						</button>
					</footer>
				</section>
			{/if}
		</main>
	{:else}
		<main class="plan-shell">
			<header class="plan-top">
				<div class="plan-top-left">
					<button type="button" class="text-btn" onclick={() => (step = 0)}>← Edit outcomes</button>
					<div class="min-w-0">
						<p class="m-0 text-[10px] uppercase tracking-wide text-brand-steel">MEL Plan</p>
						<h1 class="m-0 truncate font-headline text-lg font-semibold text-brand-navy">
							{planName}
						</h1>
						<p class="m-0 truncate text-xs text-brand-steel">
							{intervention?.name || interventionSlug}
							{#if projectName}
								· {projectName}
							{/if}
						</p>
					</div>
				</div>
				<div class="plan-top-actions">
					<button type="button" class="btn primary" disabled={exporting || loadingPlan} onclick={handleExport}>
						{exporting ? 'Exporting…' : 'Export .docx'}
					</button>
				</div>
			</header>

			{#if error}
				<p class="plan-error">{error}</p>
			{/if}

			<div class="plan-scroll">
				{#if loadingPlan}
					<p class="muted pad">Building MEL plan…</p>
				{:else if logframe}
					<MelLogFrameView {logframe} {projectName} {planName} />
				{:else}
					<p class="muted pad">Could not load the MEL plan for this selection.</p>
				{/if}
			</div>
		</main>
	{/if}
</div>

<style>
	.phase-panel {
		display: flex;
		min-height: 0;
		flex: 1;
		flex-direction: column;
		overflow: hidden;
		border-radius: 1rem;
		border: 1px solid color-mix(in srgb, #00296b 12%, white);
		background: #f4f7fb;
		color: #00296b;
	}
	.phase-head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 0.75rem;
		flex-shrink: 0;
		padding: 0.85rem 1rem;
		border-bottom: 1px solid color-mix(in srgb, #00296b 12%, white);
		background: white;
	}
	.phase-head h2 {
		margin: 0;
		font-family: var(--font-headline);
		font-size: 1rem;
		font-weight: 600;
		color: #00296b;
	}
	.phase-head p {
		margin: 0.3rem 0 0;
		font-size: 0.8rem;
		line-height: 1.4;
		color: color-mix(in srgb, #00296b 55%, white);
	}
	.phase-body {
		min-height: 0;
		flex: 1;
		padding: 0.85rem 1rem;
	}
	.phase-body.two-col {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 1rem;
		overflow-y: auto;
	}
	.phase-foot {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		flex-shrink: 0;
		padding: 0.75rem 1rem;
		border-top: 1px solid color-mix(in srgb, var(--color-brand-navy, #1a2530) 8%, transparent);
	}
	.btn {
		border-radius: 0.5rem;
		border: 1px solid color-mix(in srgb, var(--color-brand-navy, #1a2530) 18%, transparent);
		background: white;
		padding: 0.45rem 0.9rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--color-brand-navy, #1a2530);
		cursor: pointer;
	}
	.btn.primary {
		border-color: color-mix(in srgb, #1b75e0 40%, transparent);
		background: #1b75e0;
		color: white;
	}
	.btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.text-btn {
		border: none;
		background: transparent;
		padding: 0;
		font-size: 0.8rem;
		font-weight: 600;
		color: #1b75e0;
		cursor: pointer;
		text-align: left;
	}
	.section-label {
		margin: 0 0 0.55rem;
		font-size: 0.68rem;
		font-weight: 600;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--color-brand-steel, #56646f);
	}
	.outcome-list {
		margin: 0;
		padding: 0;
		list-style: none;
		display: grid;
		gap: 0.45rem;
	}
	.outcome-row {
		display: flex;
		gap: 0.55rem;
		align-items: flex-start;
		border-radius: 0.65rem;
		border: 1px solid color-mix(in srgb, var(--color-brand-navy, #1a2530) 10%, transparent);
		padding: 0.65rem 0.75rem;
		cursor: pointer;
	}
	.outcome-title {
		display: block;
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--color-brand-navy, #1a2530);
	}
	.outcome-sub {
		display: block;
		margin-top: 0.2rem;
		font-size: 0.72rem;
		line-height: 1.35;
		color: var(--color-brand-steel, #56646f);
	}
	.ind-block + .ind-block {
		margin-top: 0.75rem;
		padding-top: 0.65rem;
		border-top: 1px solid color-mix(in srgb, var(--color-brand-navy, #1a2530) 8%, transparent);
	}
	.ind-title {
		margin: 0 0 0.3rem;
		font-size: 0.8rem;
		font-weight: 600;
		color: var(--color-brand-navy, #1a2530);
	}
	.ind-list {
		margin: 0;
		padding: 0;
		list-style: none;
		display: grid;
		gap: 0.2rem;
	}
	.ind-list li {
		position: relative;
		padding-left: 0.7rem;
		font-size: 0.78rem;
		color: var(--color-brand-steel, #56646f);
	}
	.ind-list li::before {
		content: '•';
		position: absolute;
		left: 0;
		color: #1b75e0;
	}
	.muted {
		margin: 0;
		font-size: 0.8rem;
		color: var(--color-brand-steel, #56646f);
	}
	.muted.pad {
		padding: 1.5rem 1.25rem;
	}

	.plan-shell {
		display: flex;
		min-height: 0;
		flex: 1;
		flex-direction: column;
		width: 100%;
		background: #f4f7fb;
	}
	.plan-top {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-start;
		justify-content: space-between;
		gap: 0.75rem 1rem;
		flex-shrink: 0;
		padding: 0.85rem 1.25rem;
		border-bottom: 1px solid color-mix(in srgb, #00296b 12%, white);
		background: white;
	}
	.plan-top-left {
		display: flex;
		flex-direction: column;
		gap: 0.45rem;
		min-width: 0;
	}
	.plan-top-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		align-items: center;
	}
	.plan-error {
		margin: 0;
		flex-shrink: 0;
		padding: 0.55rem 1.25rem;
		font-size: 0.78rem;
		color: #b91c1c;
		background: #fef2f2;
		border-bottom: 1px solid #fecaca;
	}
	.plan-scroll {
		min-height: 0;
		flex: 1;
		overflow-y: auto;
		padding: 1rem 1rem 2rem;
		width: 100%;
	}

	@media (max-width: 860px) {
		.phase-body.two-col {
			grid-template-columns: 1fr;
		}
	}
</style>
