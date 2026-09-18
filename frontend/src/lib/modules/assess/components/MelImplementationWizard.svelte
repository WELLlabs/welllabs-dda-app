<script>
	import { onMount } from 'svelte';
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';
	import MelParamCardEditor from '$lib/modules/assess/components/MelParamCardEditor.svelte';
	import {
		createMelAsset,
		createMelOdkForms,
		deleteMelAsset,
		fetchMappingPackages,
		fetchMelAssets,
		fetchMelFormCollectQr,
		fetchMelIntervention,
		fetchMelPlan,
		fetchMelPlanForms,
		fetchOneTimeQuestions,
		saveMelPlan,
		updateMelAsset
	} from '$lib/modules/assess/mel-api';
	import {
		ASSET_SELECT_LOCK_IDS,
		buildParamCards,
		includedCards,
		isAssetSelectId,
		serializeParamCards
	} from '$lib/modules/assess/mel-param-cards.js';
	import MelFormQrCard from '$lib/modules/assess/components/MelFormQrCard.svelte';

	/** @type {{
	 *   onBack: () => void,
	 *   crumbs?: any[],
	 *   projectId: string,
	 *   planId: string,
	 *   projectName?: string,
	 *   planName?: string,
	 *   interventionSlug: string,
	 *   initialOutcomeIds?: string[],
	 *   startAtAssets?: boolean,
	 *   startAtForms?: boolean,
	 *   startNewAsset?: boolean,
	 *   editAssetId?: string
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
		startAtAssets = false,
		startAtForms = false,
		startNewAsset = false,
		editAssetId = ''
	} = $props();

	let step = $state(startAtForms ? 2 : startAtAssets ? 1 : 0);
	let loading = $state(true);
	let saving = $state(false);
	let error = $state('');
	let intervention = $state(null);
	let selectedOutcomeIds = $state([...initialOutcomeIds]);
	/** @type {any[]} */
	let otCards = $state([]); // editable asset-allocation schema cards
	/** @type {any[]} */
	let cmCards = $state([]); // editable CM form cards
	/** @type {any[]} */
	let assets = $state([]);
	/** @type {Record<string, any>} */
	let answers = $state({});
	/** @type {any[]} */
	let publishedForms = $state([]);
	let publishing = $state(false);
	let editingAssetId = $state(null);
	let showAssetForm = $state(startNewAsset || Boolean(editAssetId));
	let collectQr = $state(null);

	const formsMode = $derived(startAtForms && !startNewAsset);
	const addAssetMode = $derived(
		Boolean(editAssetId) || startNewAsset || (startAtAssets && !startAtForms)
	);

	const visibleOtCards = $derived(
		otCards.filter((c) => c.included && evaluateSkip(c.skip_logic, answers))
	);

	/** Control-plot options for treatment→control pairing (value = asset id). */
	const controlPairOptions = $derived.by(() => {
		return (assets || [])
			.filter((a) => a.id !== editingAssetId)
			.map((a) => {
				const ot = a.ot_answers || a.otAnswers || {};
				const role = String(ot.bm_ot_plot_role || '').trim().toLowerCase();
				return {
					value: String(a.id),
					label: a.label || String(a.id),
					isControl: role === 'control'
				};
			})
			.sort((a, b) => Number(b.isControl) - Number(a.isControl) || a.label.localeCompare(b.label));
	});

	const includedCmCards = $derived(includedCards(cmCards));
	const plotMode = $derived(interventionSlug === 'pmds' || interventionSlug === 'bio-mulching');
	const assetNoun = $derived(plotMode ? 'farm plot' : 'asset');
	const assetNouns = $derived(plotMode ? 'farm plots' : 'assets');
	const STEPS = $derived(
		plotMode
			? ['Outcomes', 'Farm-plot allocation', 'CM form', 'Publish']
			: ['Outcomes', 'Asset allocation', 'CM form', 'Publish']
	);

	onMount(() => {
		void bootstrap();
	});

	async function bootstrap() {
		loading = true;
		error = '';
		try {
			const [intv, ot, assetRes, formsRes, plan] = await Promise.all([
				fetchMelIntervention(interventionSlug),
				fetchOneTimeQuestions(projectId, planId),
				fetchMelAssets(projectId, planId),
				fetchMelPlanForms(projectId, planId),
				fetchMelPlan(projectId, planId).catch(() => null)
			]);
			intervention = intv;
			const pj = plan?.plan_json || {};
			if (Array.isArray(pj.outcome_ids) && pj.outcome_ids.length && !selectedOutcomeIds.length) {
				selectedOutcomeIds = [...pj.outcome_ids];
			}
			otCards = buildParamCards(ot.questions ?? intv?.one_time_questions ?? [], pj.asset_allocation);
			assets = assetRes.assets ?? [];
			publishedForms = formsRes.forms ?? [];
			const editing = editAssetId
				? (assets.find((a) => a.id === editAssetId) || null)
				: null;
			if (editing) {
				startEditAsset(editing);
			} else {
				showAssetForm = startNewAsset || (addAssetMode && assets.length === 0);
			}
			if (formsMode && !selectedOutcomeIds.length && (intv?.outcomes || []).length) {
				selectedOutcomeIds = intv.outcomes.map((o) => o.id);
			}

			if (formsMode || startAtForms || step >= 2) {
				await loadCmCards({ advance: false, planJson: pj });
			}
			await refreshQr();
		} catch (err) {
			error = String(err);
		} finally {
			loading = false;
		}
	}

	function evaluateSkip(skipLogic, vals) {
		if (!skipLogic) return true;
		const m = String(skipLogic).match(/show\s+if\s+([a-z0-9_]+)\s+(=|includes)\s+(.+)/i);
		if (!m) return true;
		const [, varName, op, rawExpected] = m;
		const expected = rawExpected.trim();
		const actual = vals[varName];
		if (op === '=') return String(actual ?? '') === expected;
		const list = Array.isArray(actual) ? actual : String(actual || '').split(/\s+/);
		return list.map(String).includes(expected);
	}

	function toggleOutcome(id) {
		if (selectedOutcomeIds.includes(id)) {
			selectedOutcomeIds = selectedOutcomeIds.filter((x) => x !== id);
		} else {
			selectedOutcomeIds = [...selectedOutcomeIds, id];
		}
	}

	function setAnswer(id, value) {
		answers = { ...answers, [id]: value };
	}

	function toggleMulti(id, option) {
		const cur = Array.isArray(answers[id]) ? [...answers[id]] : [];
		const idx = cur.indexOf(option);
		if (idx >= 0) cur.splice(idx, 1);
		else cur.push(option);
		setAnswer(id, cur);
	}

	function planPayload() {
		return {
			outcome_ids: selectedOutcomeIds,
			asset_allocation: serializeParamCards(otCards),
			cm_form: serializeParamCards(cmCards)
		};
	}

	async function refreshQr() {
		const form =
			publishedForms.find((f) => f.packageId === 'cm-mapping') || publishedForms[0] || null;
		if (!form?.xmlFormId) {
			collectQr = null;
			return;
		}
		try {
			const res = await fetchMelFormCollectQr(projectId, planId, form.xmlFormId);
			collectQr = res.collectQr ?? null;
		} catch {
			collectQr = null;
		}
	}

	async function saveForms() {
		saving = true;
		error = '';
		try {
			await saveMelPlan(projectId, planId, {
				outcomeIds: selectedOutcomeIds,
				planJson: planPayload()
			});
		} catch (err) {
			error = String(err);
		} finally {
			saving = false;
		}
	}

	async function saveOutcomesAndNext() {
		if (!selectedOutcomeIds.length) {
			error = 'Select at least one outcome.';
			return;
		}
		saving = true;
		error = '';
		try {
			await saveMelPlan(projectId, planId, {
				outcomeIds: selectedOutcomeIds,
				planJson: planPayload()
			});
			step = 1;
		} catch (err) {
			error = String(err);
		} finally {
			saving = false;
		}
	}

	function startNewAssetForm() {
		editingAssetId = null;
		answers = {};
		showAssetForm = true;
	}

	function startEditAsset(asset) {
		editingAssetId = asset.id;
		answers = { ...(asset.ot_answers || asset.otAnswers || {}) };
		showAssetForm = true;
	}

	async function saveAsset() {
		saving = true;
		error = '';
		try {
			const payload = {};
			for (const c of visibleOtCards) {
				payload[c.id] = answers[c.id] ?? '';
			}
			// Always persist pairing fields when present on cards (even if skip-hidden).
			const roleCard = otCards.find((c) => c.id === 'bm_ot_plot_role');
			if (roleCard?.included) {
				payload.bm_ot_plot_role = answers.bm_ot_plot_role ?? payload.bm_ot_plot_role ?? '';
			}
			const pairCard = otCards.find((c) => c.id === 'bm_ot_paired_control_asset_id');
			if (pairCard?.included) {
				const role = String(payload.bm_ot_plot_role || answers.bm_ot_plot_role || '')
					.trim()
					.toLowerCase();
				payload.bm_ot_paired_control_asset_id =
					role === 'treatment' ? answers.bm_ot_paired_control_asset_id || '' : '';
			}
			if (editingAssetId) {
				await updateMelAsset(projectId, planId, editingAssetId, { otAnswers: payload });
			} else {
				await createMelAsset(projectId, planId, { otAnswers: payload });
			}
			answers = {};
			editingAssetId = null;
			showAssetForm = false;
			const assetRes = await fetchMelAssets(projectId, planId);
			assets = assetRes.assets ?? [];
		} catch (err) {
			error = String(err);
		} finally {
			saving = false;
		}
	}

	async function removeAsset(id) {
		if (!confirm(plotMode ? 'Delete this farm plot?' : 'Delete this asset?')) return;
		try {
			await deleteMelAsset(projectId, planId, id);
			assets = assets.filter((a) => a.id !== id);
			if (editingAssetId === id) {
				editingAssetId = null;
				answers = {};
				showAssetForm = assets.length === 0;
			}
		} catch (err) {
			error = String(err);
		}
	}

	async function loadCmCards({ advance = true, planJson = null } = {}) {
		saving = true;
		error = '';
		try {
			await saveMelPlan(projectId, planId, {
				outcomeIds: selectedOutcomeIds,
				planJson: planPayload()
			});
			const res = await fetchMappingPackages({
				interventionSlug,
				projectId,
				planId,
				outcomeIds: selectedOutcomeIds
			});
			const pkg = (res.packages || [])[0];
			const fields = (pkg?.fields || []).map((f, i) => {
				const rawOpts = f.options || f.choices || f.selectors || [];
				const selectors = rawOpts.map((o) =>
					typeof o === 'string' ? o : o?.label || o?.value || ''
				).filter(Boolean);
				return {
					variable_name: f.id || f.field_name || `field-${i}`,
					question: f.label || `Field ${i + 1}`,
					input_type: f.input_type || 'text',
					selectors,
					options: selectors,
					skip_logic: f.hint || ''
				};
			});
			const pj = planJson || {};
			const built = buildParamCards(fields, pj.cm_form, {
				lockIds: ASSET_SELECT_LOCK_IDS
			});
			const liveAssets = (assets || []).map((a) => a.label || String(a.id));
			cmCards = built.map((c) => {
				const src = (pkg?.fields || []).find((f) => (f.id || f.field_name) === c.id) || {};
				const isAsset = isAssetSelectId(c.id);
				const options = isAsset && liveAssets.length ? liveAssets : c.options;
				return {
					...c,
					field_name: src.field_name || c.id,
					hint: c.hint || c.skip_logic || src.hint || '',
					required: !!src.required || c.locked,
					options,
					selectors: options,
					choices: options
				};
			});
			if (advance) step = 2;
		} catch (err) {
			error = String(err);
		} finally {
			saving = false;
		}
	}

	async function publish() {
		if (!includedCmCards.length) {
			error = 'Include at least one CM field before publishing.';
			return;
		}
		publishing = true;
		error = '';
		try {
			await saveMelPlan(projectId, planId, {
				outcomeIds: selectedOutcomeIds,
				planJson: planPayload()
			});
			const existing = publishedForms.find((f) => f.packageId === 'cm-mapping');
			await createMelOdkForms({
				projectId,
				planId,
				interventionSlug,
				outcomeIds: selectedOutcomeIds,
				packages: [
					{
						package_id: 'cm-mapping',
						form_title: `${projectName} - ${planName} - CM`.replace(/\s+/g, ' ').trim(),
						fields: includedCmCards.map((c) => {
							const opts =
								isAssetSelectId(c.id) && assets.length
									? assets.map((a) => ({
											value: String(a.id),
											label: a.label || String(a.id)
										}))
									: (c.options || c.selectors || []).map((o) =>
											typeof o === 'string' ? { value: o, label: o } : o
										);
							return {
								id: c.id,
								field_name: c.field_name || c.id,
								label: c.label,
								input_type: c.input_type,
								hint: c.hint || c.skip_logic || '',
								required: c.required || c.locked,
								options: opts,
								choices: opts.map((o) => o.label || o.value),
								custom: false
							};
						}),
						xml_form_id: existing?.xmlFormId || null
					}
				]
			});
			const formsRes = await fetchMelPlanForms(projectId, planId);
			publishedForms = formsRes.forms ?? [];
			await refreshQr();
			if (!formsMode) step = 3;
		} catch (err) {
			error = String(err);
		} finally {
			publishing = false;
		}
	}
</script>

<div class="min-h-screen bg-transparent font-body">
	<ModuleHeader title="Assess" titleHref="/assess" wide {crumbs} />

	<main class="mx-auto max-w-5xl p-6">
		<div class="mb-4 flex items-center justify-between gap-3">
			<div class="min-w-0">
				<p class="m-0 text-xs uppercase tracking-wide text-brand-steel">
					{formsMode
						? 'Edit forms'
						: editAssetId || editingAssetId
							? plotMode
								? 'Edit farm plot'
								: 'Edit asset'
							: addAssetMode
								? plotMode
									? 'Add farm plot'
									: 'Add asset'
								: 'Intervention'}
				</p>
				<h1 class="m-0 truncate font-headline text-xl font-semibold text-brand-navy">{planName}</h1>
			</div>
			<button type="button" class="shrink-0 text-sm text-brand-blue underline" onclick={onBack}
				>Back</button
			>
		</div>

		{#if !formsMode && !addAssetMode}
			<ol class="mb-5 flex list-none flex-wrap gap-2 p-0 text-xs">
				{#each STEPS as label, i}
					<li
						class="rounded-full px-3 py-1 {i === step
							? 'bg-brand-blue text-white'
							: i < step
								? 'bg-brand-sky/40 text-brand-navy'
								: 'bg-brand-navy/5 text-brand-steel'}"
					>
						{label}
					</li>
				{/each}
			</ol>
		{/if}

		{#if error}
			<p class="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
		{/if}

		{#if loading}
			<p class="text-brand-steel">Loading…</p>
		{:else if formsMode}
			<section class="space-y-5">
				<div class="rounded-xl border border-brand-navy/10 bg-white p-5">
					<div class="flex flex-wrap items-start justify-between gap-3">
						<div>
							<h2 class="m-0 text-base font-semibold text-brand-navy">
								{plotMode ? 'Farm-plot allocation' : 'Asset allocation'}
							</h2>
							<p class="mt-1 text-sm text-brand-steel">
								Review one-time fields. Click Edit on a card to change labels, types, or options.
							</p>
						</div>
						<span class="rounded-full bg-brand-sky/30 px-2.5 py-0.5 text-xs font-medium text-brand-navy">
							{otCards.filter((c) => c.included).length} included
						</span>
					</div>
					<div class="mt-4">
						<MelParamCardEditor
							cards={otCards}
							onChange={(next) => (otCards = next)}
							title=""
							subtitle=""
						/>
					</div>
				</div>

				<div class="rounded-xl border border-brand-navy/10 bg-white p-5">
					<div class="flex flex-wrap items-start justify-between gap-3">
						<div>
							<h2 class="m-0 text-base font-semibold text-brand-navy">CM form</h2>
							<p class="mt-1 text-sm text-brand-steel">
								Review CM fields. Click Edit on a card to change labels, types, or options.
							</p>
						</div>
						<span class="rounded-full bg-brand-sky/30 px-2.5 py-0.5 text-xs font-medium text-brand-navy">
							{includedCmCards.length} fields
						</span>
					</div>
					<div class="mt-4">
						<MelParamCardEditor
							cards={cmCards}
							onChange={(next) => (cmCards = next)}
							title=""
							subtitle=""
							emptyLabel="No CM fields loaded."
						/>
					</div>
				</div>

				{#if publishedForms.length}
					<MelFormQrCard
						formName={publishedForms.find((f) => f.packageId === 'cm-mapping')?.name ||
							publishedForms[0]?.name ||
							'CM form'}
						packageTitle="Continuous monitoring"
						xmlFormId={publishedForms.find((f) => f.packageId === 'cm-mapping')?.xmlFormId ||
							publishedForms[0]?.xmlFormId}
						collectQr={collectQr}
					/>
				{/if}

				<div class="flex flex-wrap gap-2">
					<button
						type="button"
						class="rounded-lg border border-brand-navy/20 px-4 py-2 text-sm disabled:opacity-50"
						disabled={saving}
						onclick={saveForms}
					>
						{saving ? 'Saving…' : 'Save'}
					</button>
					<button
						type="button"
						class="rounded-lg bg-brand-blue px-4 py-2 text-sm text-white disabled:opacity-50"
						disabled={publishing || !includedCmCards.length}
						onclick={publish}
					>
						{publishing ? 'Publishing…' : 'Publish CM form to ODK'}
					</button>
					<button
						type="button"
						class="rounded-lg border border-brand-navy/20 px-4 py-2 text-sm"
						onclick={onBack}
					>
						View intervention
					</button>
				</div>
			</section>
		{:else if step === 0}
			<section class="rounded-xl border border-brand-navy/10 bg-white p-5">
				<h2 class="m-0 text-base font-semibold text-brand-navy">Select outcomes</h2>
				<ul class="mt-4 m-0 list-none space-y-2 p-0">
					{#each intervention?.outcomes || [] as outcome (outcome.id)}
						<li>
							<label class="flex cursor-pointer gap-3 rounded-lg border border-brand-navy/10 p-3">
								<input
									type="checkbox"
									checked={selectedOutcomeIds.includes(outcome.id)}
									onchange={() => toggleOutcome(outcome.id)}
								/>
								<span class="font-medium text-brand-navy">{outcome.title}</span>
							</label>
						</li>
					{/each}
				</ul>
				<button
					type="button"
					class="mt-4 rounded-lg bg-brand-blue px-4 py-2 text-sm text-white disabled:opacity-50"
					disabled={saving || !selectedOutcomeIds.length}
					onclick={saveOutcomesAndNext}
				>
					{saving ? 'Saving…' : plotMode ? 'Continue to farm-plot allocation' : 'Continue to asset allocation'}
				</button>
			</section>
		{:else if addAssetMode || step === 1}
			<section class="space-y-5">
				{#if !addAssetMode}
				<div class="rounded-xl border border-brand-navy/10 bg-white p-5">
					<div class="flex flex-wrap items-start justify-between gap-3">
						<div>
							<h2 class="m-0 text-base font-semibold text-brand-navy">
								{plotMode ? 'Farm-plot allocation' : 'Asset allocation'}
							</h2>
							<p class="mt-1 text-sm text-brand-steel">
								Review one-time fields. Click Edit on a card to change labels, types, or options.
							</p>
						</div>
						<span class="rounded-full bg-brand-sky/30 px-2.5 py-0.5 text-xs font-medium text-brand-navy">
							{otCards.filter((c) => c.included).length} included
						</span>
					</div>

					<div class="mt-4">
						<MelParamCardEditor
							cards={otCards}
							onChange={(next) => (otCards = next)}
							title=""
							subtitle=""
						/>
					</div>
				</div>
				{/if}

				<div class="rounded-xl border border-brand-navy/10 bg-white p-5">
					<div class="flex flex-wrap items-center justify-between gap-3">
						<div>
							<h2 class="m-0 text-base font-semibold text-brand-navy">
								Registered {assetNouns}
							</h2>
							<p class="mt-1 text-sm text-brand-steel">
								Fill the included parameters to add or edit a {assetNoun}.
							</p>
						</div>
						<button
							type="button"
							class="rounded-lg bg-brand-blue px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-deep"
							onclick={startNewAssetForm}
						>
							Add {assetNoun}
						</button>
					</div>

					{#if assets.length}
						<ul class="mt-3 m-0 grid list-none gap-2 p-0 sm:grid-cols-2">
							{#each assets as asset (asset.id)}
								{@const ot = asset.ot_answers || {}}
								{@const role = String(ot.bm_ot_plot_role || '').trim()}
								{@const pairId = String(ot.bm_ot_paired_control_asset_id || '').trim()}
								{@const pairLabel = pairId
									? assets.find((a) => String(a.id) === pairId)?.label || pairId.slice(0, 8)
									: null}
								<li
									class="flex items-center justify-between gap-2 rounded-xl border border-brand-navy/10 px-3 py-3"
								>
									<span class="min-w-0">
										<span class="block truncate text-sm font-medium text-brand-navy"
											>{asset.label || (plotMode ? 'Farm plot' : 'Asset')}</span
										>
										{#if plotMode && (role || pairLabel)}
											<span class="mt-0.5 block truncate text-[11px] text-brand-steel">
												{role || 'Unassigned role'}{#if pairLabel} · Control: {pairLabel}{/if}
											</span>
										{/if}
									</span>
									<span class="flex shrink-0 gap-2 text-xs">
										<button
											type="button"
											class="text-brand-blue underline"
											onclick={() => startEditAsset(asset)}>Edit</button
										>
										<button
											type="button"
											class="text-red-600 underline"
											onclick={() => removeAsset(asset.id)}>Remove</button
										>
									</span>
								</li>
							{/each}
						</ul>
					{:else}
						<p class="mt-3 text-sm text-brand-steel">
							{plotMode ? 'No farm plots yet.' : 'No assets yet.'}
						</p>
					{/if}

					{#if showAssetForm}
						<div class="mt-5 border-t border-brand-navy/10 pt-4">
							<h3 class="m-0 text-sm font-semibold text-brand-navy">
								{editingAssetId
									? plotMode
										? 'Edit farm-plot answers'
										: 'Edit asset answers'
									: plotMode
										? 'New farm-plot answers'
										: 'New asset answers'}
							</h3>
							<div class="mt-3 grid gap-3 sm:grid-cols-2">
								{#each visibleOtCards as card (card.id)}
									<label class="block rounded-xl border border-brand-navy/10 bg-brand-pale/20 p-3 text-sm">
										<span class="font-medium text-brand-navy">{card.label}</span>
										{#if card.metric}
											<span class="mt-0.5 block text-[11px] text-brand-steel">{card.metric}</span>
										{/if}
										{#if card.id === 'bm_ot_paired_control_asset_id'}
											<select
												class="mt-2 w-full rounded-lg border border-brand-navy/20 px-2.5 py-1.5"
												value={answers[card.id] ?? ''}
												onchange={(e) => setAnswer(card.id, e.currentTarget.value)}
											>
												<option value="">Select control plot…</option>
												{#each controlPairOptions as opt}
													<option value={opt.value}
														>{opt.label}{opt.isControl ? '' : ' (not marked control)'}</option
													>
												{/each}
											</select>
											{#if !controlPairOptions.length}
												<span class="mt-1 block text-[11px] text-amber-700"
													>Add a control farm plot first, then link it here.</span
												>
											{/if}
										{:else if card.input_type === 'select_one' || card.input_type === 'select_one_yes_no'}
											<select
												class="mt-2 w-full rounded-lg border border-brand-navy/20 px-2.5 py-1.5"
												value={answers[card.id] ?? ''}
												onchange={(e) => setAnswer(card.id, e.currentTarget.value)}
											>
												<option value="">Select…</option>
												{#each card.options || card.selectors || [] as opt}
													<option value={opt}>{opt}</option>
												{/each}
											</select>
										{:else if card.input_type === 'select_multiple'}
											<div class="mt-2 flex flex-wrap gap-2">
												{#each card.options || card.selectors || [] as opt}
													<label class="flex items-center gap-1 text-xs">
														<input
															type="checkbox"
															checked={(answers[card.id] || []).includes(opt)}
															onchange={() => toggleMulti(card.id, opt)}
														/>
														{opt}
													</label>
												{/each}
											</div>
										{:else if card.input_type === 'date'}
											<input
												type="date"
												class="mt-2 w-full rounded-lg border border-brand-navy/20 px-2.5 py-1.5"
												value={answers[card.id] ?? ''}
												onchange={(e) => setAnswer(card.id, e.currentTarget.value)}
											/>
										{:else if card.input_type === 'decimal' || card.input_type === 'integer'}
											<input
												type="number"
												step={card.input_type === 'integer' ? '1' : 'any'}
												class="mt-2 w-full rounded-lg border border-brand-navy/20 px-2.5 py-1.5"
												value={answers[card.id] ?? ''}
												onchange={(e) => setAnswer(card.id, e.currentTarget.value)}
											/>
										{:else if card.input_type === 'geopoint'}
											<input
												type="text"
												placeholder="lat, long"
												class="mt-2 w-full rounded-lg border border-brand-navy/20 px-2.5 py-1.5"
												value={answers[card.id] ?? ''}
												onchange={(e) => setAnswer(card.id, e.currentTarget.value)}
											/>
										{:else if card.input_type === 'note'}
											<p class="mt-2 text-xs text-brand-steel">{card.hint || 'Instruction only'}</p>
										{:else}
											<input
												type="text"
												class="mt-2 w-full rounded-lg border border-brand-navy/20 px-2.5 py-1.5"
												value={answers[card.id] ?? ''}
												onchange={(e) => setAnswer(card.id, e.currentTarget.value)}
											/>
										{/if}
									</label>
								{/each}
							</div>
							<div class="mt-4 flex flex-wrap gap-2">
								<button
									type="button"
									class="rounded-lg border border-brand-blue/40 bg-brand-sky/20 px-4 py-2 text-sm disabled:opacity-50"
									disabled={saving || !visibleOtCards.length}
									onclick={saveAsset}
								>
									{saving
										? 'Saving…'
										: editingAssetId
											? plotMode
												? 'Update farm plot'
												: 'Update asset'
											: plotMode
												? 'Save farm plot'
												: 'Save asset'}
								</button>
								{#if assets.length}
									<button
										type="button"
										class="rounded-lg border border-brand-navy/20 px-4 py-2 text-sm"
										onclick={() => {
											showAssetForm = false;
											editingAssetId = null;
											answers = {};
										}}
									>
										Cancel
									</button>
								{/if}
							</div>
						</div>
					{/if}
				</div>

				<div class="flex flex-wrap gap-2">
					{#if addAssetMode}
						<button
							type="button"
							class="rounded-lg border border-brand-navy/20 px-4 py-2 text-sm"
							onclick={onBack}>View intervention</button
						>
					{:else}
						<button
							type="button"
							class="rounded-lg border border-brand-navy/20 px-4 py-2 text-sm"
							onclick={() => (step = 0)}>Back</button
						>
						<button
							type="button"
							class="rounded-lg bg-brand-blue px-4 py-2 text-sm text-white disabled:opacity-50"
							disabled={!assets.length || saving}
							onclick={() => loadCmCards()}
						>
							{saving ? 'Loading…' : 'Continue to CM form'}
						</button>
					{/if}
				</div>
			</section>
		{:else if step === 2}
			<section class="rounded-xl border border-brand-navy/10 bg-white p-5">
				<div class="flex flex-wrap items-start justify-between gap-3">
					<div>
						<h2 class="m-0 text-base font-semibold text-brand-navy">Continuous monitoring</h2>
						<p class="mt-1 text-sm text-brand-steel">
							Review CM fields. Click Edit on a card to change labels, types, or options.
						</p>
					</div>
					<span class="rounded-full bg-brand-sky/30 px-2.5 py-0.5 text-xs font-medium text-brand-navy">
						{includedCmCards.length} fields
					</span>
				</div>

				<div class="mt-4">
					<MelParamCardEditor
						cards={cmCards}
						onChange={(next) => (cmCards = next)}
						title=""
						subtitle=""
						emptyLabel="No CM fields loaded."
					/>
				</div>

				<div class="mt-5 flex flex-wrap gap-2">
					<button
						type="button"
						class="rounded-lg border border-brand-navy/20 px-4 py-2 text-sm"
						onclick={() => (step = 1)}>Back</button
					>
					<button
						type="button"
						class="rounded-lg bg-brand-blue px-4 py-2 text-sm text-white disabled:opacity-50"
						disabled={publishing || !includedCmCards.length}
						onclick={publish}
					>
						{publishing ? 'Publishing…' : 'Publish CM form to ODK'}
					</button>
				</div>
			</section>
		{:else}
			<section class="rounded-xl border border-brand-navy/10 bg-white p-5">
				<h2 class="m-0 text-base font-semibold text-brand-navy">Published</h2>
				<p class="mt-2 text-sm text-brand-steel">
					CM form is on ODK Central. You can return anytime to edit
					{plotMode ? 'farm-plot' : 'asset'} allocation or the CM form.
				</p>
				<ul class="mt-3 m-0 list-none space-y-2 p-0">
					{#each publishedForms as form (form.id)}
						<li class="rounded-lg border border-brand-navy/10 px-3 py-2 text-sm">{form.name}</li>
					{/each}
				</ul>
				<div class="mt-5 flex flex-wrap gap-2">
					<button
						type="button"
						class="rounded-lg border border-brand-navy/20 px-4 py-2 text-sm"
						onclick={() => (step = 1)}
						>{plotMode ? 'Edit farm-plot allocation' : 'Edit asset allocation'}</button
					>
					>
					<button
						type="button"
						class="rounded-lg border border-brand-navy/20 px-4 py-2 text-sm"
						onclick={() => (step = 2)}>Edit CM form</button
					>
					<button
						type="button"
						class="rounded-lg bg-brand-blue px-4 py-2 text-sm text-white"
						onclick={onBack}>View intervention</button
					>
				</div>
			</section>
		{/if}
	</main>
</div>
