<script>
	import { onMount } from 'svelte';
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';
	import MelParamCardEditor from '$lib/modules/assess/components/MelParamCardEditor.svelte';
	import {
		exportMelPlanDocx,
		fetchMelIntervention,
		fetchMelPlan,
		saveMelPlan
	} from '$lib/modules/assess/mel-api';
	import {
		buildParamCards,
		includedCards,
		serializeParamCards,
		typeLabel,
		ASSET_SELECT_LOCK_IDS
	} from '$lib/modules/assess/mel-param-cards.js';

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

	let step = $state(Math.min(Math.max(Number(startStep) || 0, 0), 3));
	let loading = $state(true);
	let saving = $state(false);
	let exporting = $state(false);
	let error = $state('');
	let intervention = $state(null);
	let selectedOutcomeIds = $state([...initialOutcomeIds]);
	/** @type {any[]} */
	let otCards = $state([]);
	/** @type {any[]} */
	let cmCards = $state([]);

	const plotMode = $derived(interventionSlug === 'pmds' || interventionSlug === 'bio-mulching');
	const STEPS = $derived([
		{ id: 'outcomes', label: 'Outcomes & indicators' },
		{ id: 'assets', label: plotMode ? 'Farm-plot allocation' : 'Asset allocation' },
		{ id: 'cm', label: 'Continuous monitoring' },
		{ id: 'export', label: 'Export' }
	]);

	const selectedOutcomes = $derived(
		(intervention?.outcomes || []).filter((o) => selectedOutcomeIds.includes(o.id))
	);
	const includedOt = $derived(includedCards(otCards));
	const includedCm = $derived(includedCards(cmCards));

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
			if (Array.isArray(pj.outcome_ids) && pj.outcome_ids.length) {
				selectedOutcomeIds = [...pj.outcome_ids];
			}
			hydrateCards(intv, pj);
		} catch (err) {
			error = String(err);
		} finally {
			loading = false;
		}
	}

	function hydrateCards(intv, pj) {
		otCards = buildParamCards(intv?.one_time_questions || [], pj?.asset_allocation);
		cmCards = buildParamCards(intv?.cm_questions || [], pj?.cm_form, {
			lockIds: ASSET_SELECT_LOCK_IDS
		});
	}

	function planPayload() {
		return {
			outcome_ids: selectedOutcomeIds,
			asset_allocation: serializeParamCards(otCards),
			cm_form: serializeParamCards(cmCards)
		};
	}

	function toggleOutcome(id) {
		if (selectedOutcomeIds.includes(id)) {
			selectedOutcomeIds = selectedOutcomeIds.filter((x) => x !== id);
		} else {
			selectedOutcomeIds = [...selectedOutcomeIds, id];
		}
	}

	async function persist(nextStep = null) {
		saving = true;
		error = '';
		try {
			await saveMelPlan(projectId, planId, {
				outcomeIds: selectedOutcomeIds,
				planJson: planPayload()
			});
			if (nextStep != null) step = nextStep;
		} catch (err) {
			error = String(err);
		} finally {
			saving = false;
		}
	}

	async function goFromOutcomes() {
		if (!selectedOutcomeIds.length) {
			error = 'Select at least one outcome.';
			return;
		}
		await persist(1);
	}

	async function goFromAssets() {
		if (!includedOt.length) {
			error = plotMode
				? 'Include at least one farm-plot allocation parameter.'
				: 'Include at least one asset allocation parameter.';
			return;
		}
		await persist(2);
	}

	async function goFromCm() {
		if (!includedCm.length) {
			error = 'Include at least one continuous monitoring parameter.';
			return;
		}
		await persist(3);
	}

	async function jumpTo(i) {
		if (i === step) return;
		if (i > step) {
			// only allow forward via Continue after validation
			return;
		}
		error = '';
		step = i;
	}

	async function handleExport() {
		exporting = true;
		error = '';
		try {
			await saveMelPlan(projectId, planId, {
				outcomeIds: selectedOutcomeIds,
				planJson: planPayload()
			});
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

		<nav class="crumb-trail shrink-0" aria-label="MEL plan phases">
			{#each STEPS as s, i}
				{#if i > 0}
					<span class="crumb-sep" aria-hidden="true">/</span>
				{/if}
				<button
					type="button"
					class="crumb"
					class:active={i === step}
					class:done={i < step}
					disabled={i > step}
					onclick={() => jumpTo(i)}
				>
					<span class="crumb-num">{i + 1}</span>
					<span class="crumb-label">{s.label}</span>
				</button>
			{/each}
		</nav>

		{#if error}
			<p class="m-0 shrink-0 rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs text-red-700">
				{error}
			</p>
		{/if}

		{#if loading}
			<p class="text-sm text-brand-steel">Loading catalog…</p>
		{:else if step === 0}
			<section class="phase-panel">
				<header class="phase-head">
					<div>
						<h2>Outcomes & indicators</h2>
						<p>Select outcomes. System indicators for the selection are listed below.</p>
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
						onclick={goFromOutcomes}
					>
						{saving
							? 'Saving…'
							: plotMode
								? 'Continue to farm-plot allocation'
								: 'Continue to asset allocation'}
					</button>
				</footer>
			</section>
		{:else if step === 1}
			<section class="phase-panel">
				<header class="phase-head">
					<div>
						<h2>{plotMode ? 'Farm-plot allocation' : 'Asset allocation'}</h2>
						<p>
							Review one-time fields. Click Edit on a card to change labels, types, or options.
						</p>
					</div>
					<span class="badge">{includedOt.length} included</span>
				</header>
				<div class="phase-body scroll">
					<MelParamCardEditor
						cards={otCards}
						onChange={(next) => (otCards = next)}
						title=""
						subtitle=""
						emptyLabel={plotMode
							? 'No farm-plot allocation questions in the catalog.'
							: 'No asset allocation questions in the catalog.'}
					/>
				</div>
				<footer class="phase-foot">
					<button type="button" class="btn" onclick={() => (step = 0)}>Back</button>
					<button type="button" class="btn" disabled={saving} onclick={() => persist()}>
						{saving ? 'Saving…' : 'Save'}
					</button>
					<button
						type="button"
						class="btn primary"
						disabled={saving || !includedOt.length}
						onclick={goFromAssets}
					>
						{saving ? 'Saving…' : 'Continue to continuous monitoring'}
					</button>
				</footer>
			</section>
		{:else if step === 2}
			<section class="phase-panel">
				<header class="phase-head">
					<div>
						<h2>Continuous monitoring</h2>
						<p>
							Review CM fields. Click Edit on a card to change labels, types, or options.
						</p>
					</div>
					<span class="badge">{includedCm.length} included</span>
				</header>
				<div class="phase-body scroll">
					<MelParamCardEditor
						cards={cmCards}
						onChange={(next) => (cmCards = next)}
						title=""
						subtitle=""
						emptyLabel="No continuous monitoring questions in the catalog."
					/>
				</div>
				<footer class="phase-foot">
					<button type="button" class="btn" onclick={() => (step = 1)}>Back</button>
					<button type="button" class="btn" disabled={saving} onclick={() => persist()}>
						{saving ? 'Saving…' : 'Save'}
					</button>
					<button
						type="button"
						class="btn primary"
						disabled={saving || !includedCm.length}
						onclick={goFromCm}
					>
						{saving ? 'Saving…' : 'Continue to export'}
					</button>
				</footer>
			</section>
		{:else}
			<section class="phase-panel">
				<header class="phase-head">
					<div>
						<h2>Export MEL plan</h2>
						<p>
							Download a Word document with {selectedOutcomes.length} outcomes,
							{includedOt.length}
							{plotMode ? 'farm-plot' : 'asset'} allocation parameters, and {includedCm.length} CM parameters
							for {projectName || 'this project'}.
						</p>
					</div>
				</header>
				<div class="phase-body">
					<div class="summary-grid">
						<div class="summary-card">
							<p class="summary-kicker">Outcomes</p>
							<ul>
								{#each selectedOutcomes as o}
									<li>{o.title}</li>
								{/each}
							</ul>
						</div>
						<div class="summary-card">
							<p class="summary-kicker">Asset allocation</p>
							<ul>
								{#each includedOt as c}
									<li>{c.label} <span>· {typeLabel(c.input_type)}</span></li>
								{/each}
							</ul>
						</div>
						<div class="summary-card">
							<p class="summary-kicker">Continuous monitoring</p>
							<ul>
								{#each includedCm as c}
									<li>{c.label} <span>· {typeLabel(c.input_type)}</span></li>
								{/each}
							</ul>
						</div>
					</div>
				</div>
				<footer class="phase-foot">
					<button type="button" class="btn" onclick={() => (step = 2)}>Back</button>
					<button type="button" class="btn primary" disabled={exporting} onclick={handleExport}>
						{exporting ? 'Exporting…' : 'Export .docx'}
					</button>
					<button type="button" class="btn" onclick={onBack}>Done</button>
				</footer>
			</section>
		{/if}
	</main>
</div>

<style>
	.crumb-trail {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.35rem 0.45rem;
	}
	.crumb {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		border: none;
		background: transparent;
		cursor: pointer;
		padding: 0.2rem 0.15rem;
		color: var(--color-brand-steel, #56646f);
	}
	.crumb:disabled {
		cursor: default;
		opacity: 0.55;
	}
	.crumb.active {
		color: var(--color-brand-navy, #1a2530);
	}
	.crumb.done {
		color: #1565c0;
	}
	.crumb-num {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.25rem;
		height: 1.25rem;
		border-radius: 999px;
		font-size: 0.68rem;
		font-weight: 700;
		background: color-mix(in srgb, var(--color-brand-navy, #1a2530) 8%, white);
		color: inherit;
	}
	.crumb.active .crumb-num {
		background: #1b75e0;
		color: white;
	}
	.crumb.done .crumb-num {
		background: color-mix(in srgb, #1b75e0 18%, white);
		color: #1565c0;
	}
	.crumb-label {
		font-size: 0.78rem;
		font-weight: 600;
	}
	.crumb-sep {
		color: color-mix(in srgb, var(--color-brand-navy, #1a2530) 25%, transparent);
		font-size: 0.75rem;
	}
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
	.badge {
		flex-shrink: 0;
		border-radius: 999px;
		background: color-mix(in srgb, #1b75e0 12%, white);
		padding: 0.2rem 0.55rem;
		font-size: 0.7rem;
		font-weight: 600;
		color: #1565c0;
	}
	.phase-body {
		min-height: 0;
		flex: 1;
		padding: 0.85rem 1rem;
	}
	.phase-body.scroll {
		overflow-y: auto;
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
	.summary-grid {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 0.75rem;
	}
	.summary-card {
		border-radius: 0.65rem;
		border: 1px solid color-mix(in srgb, var(--color-brand-navy, #1a2530) 10%, transparent);
		padding: 0.75rem;
	}
	.summary-kicker {
		margin: 0 0 0.45rem;
		font-size: 0.65rem;
		font-weight: 600;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--color-brand-steel, #56646f);
	}
	.summary-card ul {
		margin: 0;
		padding: 0;
		list-style: none;
		display: grid;
		gap: 0.3rem;
	}
	.summary-card li {
		font-size: 0.78rem;
		color: var(--color-brand-navy, #1a2530);
	}
	.summary-card li span {
		color: var(--color-brand-steel, #56646f);
	}
	@media (max-width: 860px) {
		.phase-body.two-col,
		.summary-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
