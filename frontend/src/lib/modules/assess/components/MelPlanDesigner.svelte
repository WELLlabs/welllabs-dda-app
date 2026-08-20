<script>
	import { onMount } from 'svelte';
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';
	import MelFormQrCard from '$lib/modules/assess/components/MelFormQrCard.svelte';
	import {
		createMelOdkForms,
		exportMelPlanPdf,
		fetchMelIntervention,
		fetchMelInterventions,
		fetchMelPackages,
		fetchMelPlan,
		fetchMelPlanForms
	} from '$lib/modules/assess/mel-api';

	/** @type {{ onBack: () => void, onFormCreated?: (payload: any) => void, projectId?: string, planId?: string, projectName?: string, planName?: string, lockedInterventionSlug?: string, odkFormsMode?: boolean, crumbs?: import('$lib/shared/components/ModuleHeader.svelte').Crumb[] }} */
	let {
		onBack,
		onFormCreated,
		projectId = '',
		planId = '',
		projectName = '',
		planName = '',
		lockedInterventionSlug = '',
		odkFormsMode = false,
		crumbs = []
	} = $props();

	const STEPS = $derived(
		lockedInterventionSlug
			? ['Outcomes', 'MEL types', 'Edit forms', 'Publish']
			: ['Intervention', 'Outcomes', 'MEL types', 'Edit forms', 'Publish']
	);
	const displayStep = $derived(lockedInterventionSlug ? step - 1 : step);

	function packageLabel(pkg) {
		return String(pkg?.title || pkg?.id || 'Form')
			.replace(/ · /g, ' ')
			.replace(/·/g, ' ')
			.replace(/\s+/g, ' ')
			.trim();
	}

	function odkFormTitle(pkg) {
		const parts = [projectName, planName, packageLabel(pkg)].filter(Boolean);
		return parts.join(' - ') || packageLabel(pkg);
	}

	const fieldClass =
		'w-full rounded border border-brand-navy/20 px-2 py-1.5 font-body text-sm text-brand-navy outline-none focus:border-brand-navy/40';

	const OUTCOME_CATEGORY_ORDER = [
		'Biophysical (plot / structure level)',
		'Socio-economic',
		'Watershed-level'
	];

	const MEL_FAMILY_ORDER = ['continuous', 'one_time', 'bme'];
	const MEL_FAMILY_LABELS = {
		continuous: 'Continuous monitoring',
		one_time: 'One-time',
		bme: 'BME survey'
	};

	let step = $state(0);
	let loading = $state(true);
	let saving = $state(false);
	let exportingPdf = $state(false);
	let error = $state('');

	let interventions = $state([]);
	let intervention = $state(null);
	let selectedInterventionSlug = $state('');
	let selectedOutcomeIds = $state([]);
	let expandedOutcomeIds = $state([]);

	let packagePayload = $state(null);
	/** @type {any[]} */
	let packages = $state([]);
	let selectedPackageIds = $state([]);
	let inputTypes = $state([]);
	/** @type {Record<string, any[]>} */
	let packageFields = $state({});
	/** @type {Record<string, string>} */
	let packageTitles = $state({});
	let activeEditPackageId = $state('');
	let createdForms = $state([]);
	/** @type {any} */
	let publishedCollectQr = $state(null);
	/** @type {Record<string, string>} packageId → existing ODK xmlFormId */
	let existingXmlFormByPackage = $state({});
	let customSeq = $state(1);

	const isUpdatingExisting = $derived(Object.keys(existingXmlFormByPackage).length > 0);

	function outcomeTitle(outcome) {
		return outcome.title ?? outcome.outcome;
	}

	function toggleExpanded(outcomeId) {
		if (expandedOutcomeIds.includes(outcomeId)) {
			expandedOutcomeIds = expandedOutcomeIds.filter((id) => id !== outcomeId);
		} else {
			expandedOutcomeIds = [...expandedOutcomeIds, outcomeId];
		}
	}

	function isExpanded(outcomeId) {
		return expandedOutcomeIds.includes(outcomeId);
	}

	function normalizeOptions(raw) {
		if (!raw) return [];
		if (!Array.isArray(raw)) return [];
		return raw
			.map((part, index) => {
				if (part && typeof part === 'object') {
					const label = String(part.label || part.value || '').trim();
					const value = String(part.value || '').trim() || `option_${index + 1}`;
					return label || value ? { value, label: label || value } : null;
				}
				const label = String(part || '').trim();
				return label ? { value: `option_${index + 1}`, label } : null;
			})
			.filter(Boolean);
	}

	function usesOptions(typeId) {
		return typeId === 'select_one' || typeId === 'select_multiple' || typeId === 'select_one_yes_no';
	}

	function defaultOptionsForType(typeId) {
		if (typeId === 'select_one_yes_no') {
			return [
				{ value: 'yes', label: 'Yes' },
				{ value: 'no', label: 'No' }
			];
		}
		return [
			{ value: 'option_a', label: 'Option A' },
			{ value: 'option_b', label: 'Option B' }
		];
	}

	function fieldNameFromLabel(label, fallbackIndex = 1) {
		const raw = String(label || '')
			.toLowerCase()
			.replace(/[^a-z0-9]+/g, '_')
			.replace(/^_+|_+$/g, '')
			.slice(0, 50);
		let slug = raw || `ind_${String(fallbackIndex).padStart(3, '0')}`;
		if (/^\d/.test(slug)) slug = `f_${slug}`;
		return slug;
	}

	function requiredMetaFields() {
		return [
			{
				id: '__meta_observation_date',
				field_name: 'observation_date',
				label: 'Date',
				hint: 'Date of this observation or survey.',
				input_type: 'date',
				indicator: 'Date',
				outcome: '',
				category_label: 'Metadata',
				assumptions: '',
				custom: false,
				locked: true,
				required: true,
				options: []
			},
			{
				id: '__meta_coordinates',
				field_name: 'coordinates',
				label: 'Coordinates',
				hint: 'Capture GPS location at the observation site.',
				input_type: 'geopoint',
				indicator: 'Coordinates',
				outcome: '',
				category_label: 'Metadata',
				assumptions: '',
				custom: false,
				locked: true,
				required: true,
				options: []
			}
		];
	}

	function ensureRequiredMetaFields(fields) {
		const list = [...(fields ?? [])];
		const types = new Set(list.map((f) => f.input_type));
		const names = new Set(list.map((f) => f.field_name));
		const missing = requiredMetaFields().filter(
			(meta) => !types.has(meta.input_type) && !names.has(meta.field_name)
		);
		return [...missing, ...list];
	}

	function cloneFields(fields) {
		const cloned = (fields ?? []).map((item, index) => {
			const inputType = item.input_type ?? 'decimal';
			let options = normalizeOptions(item.options ?? item.choices);
			if (usesOptions(inputType) && options.length === 0) {
				options = defaultOptionsForType(inputType);
			}
			const label = item.label ?? item.indicator ?? '';
			const locked = Boolean(item.locked);
			return {
				...item,
				label,
				hint: item.hint ?? '',
				input_type: inputType,
				field_name: locked && item.field_name
					? item.field_name
					: fieldNameFromLabel(label, index + 1),
				options,
				custom: Boolean(item.custom),
				locked,
				required: Boolean(item.required || locked)
			};
		});
		return ensureRequiredMetaFields(cloned);
	}

	onMount(async () => {
		loading = true;
		error = '';
		try {
			if (lockedInterventionSlug) {
				selectedInterventionSlug = lockedInterventionSlug;
				intervention = await fetchMelIntervention(lockedInterventionSlug);

				let storedOutcomeIds = [];
				/** @type {any[]} */
				let existingForms = [];
				let publishedPackageIds = [];

				if (projectId && planId) {
					const [planDetail, formsRes] = await Promise.all([
						fetchMelPlan(projectId, planId).catch(() => null),
						fetchMelPlanForms(projectId, planId).catch(() => ({ forms: [] }))
					]);
					const planJson = planDetail?.plan_json || {};
					storedOutcomeIds = Array.isArray(planJson.outcome_ids) ? planJson.outcome_ids : [];
					publishedPackageIds = Array.isArray(planJson.published_packages)
						? planJson.published_packages
						: [];
					existingForms = formsRes?.forms ?? [];
				}

				const mustIds = (intervention.outcomes ?? [])
					.filter((o) => o.must_measure)
					.map((o) => o.id);
				selectedOutcomeIds = [...new Set([...mustIds, ...storedOutcomeIds])];
				expandedOutcomeIds = [...selectedOutcomeIds];
				step = 1;

				if (odkFormsMode && existingForms.length > 0) {
					const byPackage = {};
					for (const form of existingForms) {
						if (form.packageId && form.xmlFormId) {
							byPackage[form.packageId] = form.xmlFormId;
						}
					}
					existingXmlFormByPackage = byPackage;

					const selectIds =
						Object.keys(byPackage).length > 0
							? Object.keys(byPackage)
							: publishedPackageIds;

					await hydratePackages({
						selectIds,
						jumpToStep: 3
					});
				} else if (odkFormsMode && storedOutcomeIds.length) {
					// Plan exists but no ODK forms yet — jump into MEL types after outcomes restored.
					await hydratePackages({ jumpToStep: 2 });
				}
			} else {
				const interventionRes = await fetchMelInterventions();
				interventions = interventionRes.interventions ?? [];
			}
		} catch (err) {
			error = String(err);
		} finally {
			loading = false;
		}
	});

	const groupedOutcomes = $derived.by(() => {
		if (!intervention?.outcomes) return [];
		const groups = new Map();
		for (const outcome of intervention.outcomes) {
			const key = outcome.category_label || 'Other';
			if (!groups.has(key)) groups.set(key, []);
			groups.get(key).push(outcome);
		}
		const entries = [...groups.entries()];
		entries.sort((a, b) => {
			const ai = OUTCOME_CATEGORY_ORDER.indexOf(a[0]);
			const bi = OUTCOME_CATEGORY_ORDER.indexOf(b[0]);
			return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
		});
		return entries;
	});

	const mustMeasureIds = $derived(
		(intervention?.outcomes ?? []).filter((o) => o.must_measure).map((o) => o.id)
	);

	const selectedCount = $derived(new Set([...selectedOutcomeIds, ...mustMeasureIds]).size);

	const selectedPackages = $derived(
		packages.filter((pkg) => selectedPackageIds.includes(pkg.id))
	);

	const familyGroups = $derived.by(() => {
		return MEL_FAMILY_ORDER.map((family) => ({
			family,
			label: MEL_FAMILY_LABELS[family],
			items: packages.filter((pkg) => pkg.family === family)
		})).filter((group) => group.items.length);
	});

	function selectIntervention(slug) {
		selectedInterventionSlug = slug;
		selectedOutcomeIds = [];
		packagePayload = null;
		packages = [];
		selectedPackageIds = [];
		packageFields = {};
		packageTitles = {};
		activeEditPackageId = '';
		createdForms = [];
		publishedCollectQr = null;
		existingXmlFormByPackage = {};
		error = '';
	}

	async function goToOutcomes() {
		if (!selectedInterventionSlug) return;
		loading = true;
		error = '';
		try {
			intervention = await fetchMelIntervention(selectedInterventionSlug);
			selectedOutcomeIds = (intervention.outcomes ?? [])
				.filter((o) => o.must_measure)
				.map((o) => o.id);
			expandedOutcomeIds = (intervention.outcomes ?? [])
				.filter((o) => o.must_measure)
				.map((o) => o.id);
			step = 1;
		} catch (err) {
			error = String(err);
		} finally {
			loading = false;
		}
	}

	function toggleOutcome(outcome) {
		if (outcome.must_measure) return;
		if (selectedOutcomeIds.includes(outcome.id)) {
			selectedOutcomeIds = selectedOutcomeIds.filter((id) => id !== outcome.id);
		} else {
			selectedOutcomeIds = [...selectedOutcomeIds, outcome.id];
		}
	}

	async function hydratePackages({ selectIds = null, jumpToStep = 2 } = {}) {
		packagePayload = await fetchMelPackages({
			interventionSlug: selectedInterventionSlug,
			outcomeIds: selectedOutcomeIds,
			projectId: projectId || undefined,
			planId: planId || undefined
		});
		packages = packagePayload.packages ?? [];
		inputTypes = packagePayload.input_types ?? [];
		const fields = {};
		const titles = {};
		for (const pkg of packages) {
			fields[pkg.id] = cloneFields(pkg.suggested_fields);
			titles[pkg.id] = odkFormTitle(pkg);
		}
		packageFields = fields;
		packageTitles = titles;
		createdForms = [];
		publishedCollectQr = null;

		if (Array.isArray(selectIds) && selectIds.length) {
			const available = new Set(packages.map((pkg) => pkg.id));
			selectedPackageIds = selectIds.filter((id) => available.has(id));
			if (!selectedPackageIds.length) {
				selectedPackageIds = packages.map((pkg) => pkg.id);
			}
		} else if (jumpToStep >= 3) {
			selectedPackageIds = packages.map((pkg) => pkg.id);
		} else {
			selectedPackageIds = [];
		}
		activeEditPackageId = selectedPackageIds[0] ?? '';
		step = jumpToStep;
	}

	async function goToPackages() {
		loading = true;
		error = '';
		try {
			await hydratePackages({ jumpToStep: 2 });
		} catch (err) {
			error = String(err);
		} finally {
			loading = false;
		}
	}

	function togglePackage(packageId) {
		if (selectedPackageIds.includes(packageId)) {
			selectedPackageIds = selectedPackageIds.filter((id) => id !== packageId);
			if (activeEditPackageId === packageId) {
				activeEditPackageId = selectedPackageIds[0] ?? '';
			}
		} else {
			selectedPackageIds = [...selectedPackageIds, packageId];
			if (!activeEditPackageId) activeEditPackageId = packageId;
		}
	}

	function goToEditForms() {
		if (!packages.length) {
			error = 'No MEL packages available to edit for ODK.';
			return;
		}
		error = '';
		step = 3;
	}

	function updatePackageField(packageId, fieldId, patch) {
		const list = packageFields[packageId] ?? [];
		packageFields = {
			...packageFields,
			[packageId]: list.map((field, index) => {
				if (field.id !== fieldId) return field;
				const next = { ...field, ...patch };
				if ('input_type' in patch && usesOptions(patch.input_type) && !(next.options?.length)) {
					next.options = defaultOptionsForType(patch.input_type);
				}
				if ('label' in patch) {
					if (!next.locked) {
						next.field_name = fieldNameFromLabel(next.label, index + 1);
					}
				}
				return next;
			})
		};
	}

	function moveField(packageId, fieldId, delta) {
		const list = [...(packageFields[packageId] ?? [])];
		const index = list.findIndex((field) => field.id === fieldId);
		if (index < 0) return;
		const nextIndex = index + delta;
		if (nextIndex < 0 || nextIndex >= list.length) return;
		const tmp = list[index];
		list[index] = list[nextIndex];
		list[nextIndex] = tmp;
		packageFields = { ...packageFields, [packageId]: list };
	}

	function addOption(packageId, fieldId) {
		const field = (packageFields[packageId] ?? []).find((item) => item.id === fieldId);
		if (!field) return;
		updatePackageField(packageId, fieldId, {
			options: [...(field.options ?? []), { value: '', label: '' }]
		});
	}

	function updateOption(packageId, fieldId, optIdx, key, val) {
		const field = (packageFields[packageId] ?? []).find((item) => item.id === fieldId);
		if (!field) return;
		updatePackageField(packageId, fieldId, {
			options: (field.options ?? []).map((opt, i) => (i === optIdx ? { ...opt, [key]: val } : opt))
		});
	}

	function removeOption(packageId, fieldId, optIdx) {
		const field = (packageFields[packageId] ?? []).find((item) => item.id === fieldId);
		if (!field) return;
		updatePackageField(packageId, fieldId, {
			options: (field.options ?? []).filter((_, i) => i !== optIdx)
		});
	}

	function removeField(packageId, fieldId) {
		const target = (packageFields[packageId] ?? []).find((field) => field.id === fieldId);
		if (target?.locked) return;
		packageFields = {
			...packageFields,
			[packageId]: (packageFields[packageId] ?? []).filter((field) => field.id !== fieldId)
		};
	}

	function addCustomField(packageId) {
		const n = customSeq;
		customSeq += 1;
		const list = packageFields[packageId] ?? [];
		const label = `Custom question ${n}`;
		packageFields = {
			...packageFields,
			[packageId]: [
				...list,
				{
					id: `custom_${packageId}_${Date.now()}_${n}`,
					field_name: fieldNameFromLabel(label, n),
					label,
					hint: '',
					input_type: 'text',
					options: [],
					indicator: '',
					outcome: 'Custom',
					category_label: 'Custom question',
					assumptions: '',
					custom: true
				}
			]
		};
	}

	function goToPublish() {
		if (!selectedPackageIds.length) {
			error = 'Select at least one MEL type to publish.';
			return;
		}
		for (const pkg of selectedPackages) {
			const fields = packageFields[pkg.id] ?? [];
			if (!fields.length) {
				error = `“${pkg.title}” needs at least one field.`;
				activeEditPackageId = pkg.id;
				return;
			}
			const blank = fields.find((field) => !(field.label || '').trim());
			if (blank) {
				error = `Every field in “${pkg.title}” needs a label.`;
				activeEditPackageId = pkg.id;
				return;
			}
			const badSelect = fields.find((field) => {
				if (!usesOptions(field.input_type)) return false;
				const filled = (field.options ?? []).filter((opt) => (opt.label || opt.value || '').trim());
				return filled.length < 2;
			});
			if (badSelect) {
				error = `“${badSelect.label}” in ${pkg.title} needs at least two options.`;
				activeEditPackageId = pkg.id;
				return;
			}
		}
		error = '';
		step = 4;
	}

	async function handlePublish() {
		saving = true;
		error = '';
		try {
			if (!projectId || !planId) {
				error = 'Missing MEL plan. Open the designer from a plan.';
				return;
			}
			const result = await createMelOdkForms({
				projectId,
				planId,
				interventionSlug: selectedInterventionSlug,
				outcomeIds: selectedOutcomeIds,
				packages: selectedPackages.map((pkg) => ({
					package_id: pkg.id,
					form_title: odkFormTitle(pkg),
					xml_form_id: existingXmlFormByPackage[pkg.id] || undefined,
					fields: (packageFields[pkg.id] ?? []).map((field, index) => ({
						id: field.id,
						label: field.label,
						hint: field.hint,
						input_type: field.input_type,
						field_name: field.locked
							? field.field_name
							: fieldNameFromLabel(field.label, index + 1),
						options: (field.options ?? [])
							.map((opt) => ({
								value: String(opt.value || '').trim(),
								label: String(opt.label || '').trim()
							}))
							.filter((opt) => opt.label || opt.value),
						indicator: field.indicator || field.label,
						outcome: field.outcome,
						category_label: field.category_label,
						assumptions: field.assumptions || '',
						custom: Boolean(field.custom),
						locked: Boolean(field.locked),
						required: Boolean(field.required || field.locked)
					}))
				}))
			});
			createdForms = result.forms ?? [];
			publishedCollectQr = result.collectQr ?? createdForms[0]?.collectQr ?? null;
			// Refresh local xmlFormId map after publish/update
			const nextMap = { ...existingXmlFormByPackage };
			for (const form of createdForms) {
				if (form.packageId && form.xmlFormId) {
					nextMap[form.packageId] = form.xmlFormId;
				}
			}
			existingXmlFormByPackage = nextMap;
			onFormCreated?.(result);
		} catch (err) {
			error = String(err);
		} finally {
			saving = false;
		}
	}

	async function handleExportPdf() {
		exportingPdf = true;
		error = '';
		try {
			const { blob, filename } = await exportMelPlanPdf({
				interventionSlug: selectedInterventionSlug,
				outcomeIds: selectedOutcomeIds,
				projectId: projectId || undefined,
				planId: planId || undefined
			});
			const url = URL.createObjectURL(blob);
			const anchor = document.createElement('a');
			anchor.href = url;
			anchor.download = filename;
			anchor.click();
			URL.revokeObjectURL(url);
		} catch (err) {
			error = String(err);
		} finally {
			exportingPdf = false;
		}
	}
</script>

<div class="relative min-h-screen bg-transparent font-body">
	<ModuleHeader title="Assess" titleHref="/assess" wide fullProjectTitle {crumbs}>
		<button type="button" onclick={onBack}>Back to project</button>
	</ModuleHeader>

	<main class="relative z-10 flex-1 overflow-auto p-6">
		<div class="mb-6 flex flex-wrap items-center gap-2">
			{#each STEPS as label, index}
				<div
					class="rounded-full px-3 py-1 font-mono text-[11px] font-semibold tracking-wide uppercase {index === displayStep ? 'bg-[#16a34a] text-white' : index < displayStep ? 'bg-[#dcfce7] text-[#14532d]' : 'bg-white text-brand-steel'}"
				>
					{index + 1}. {label}
				</div>
			{/each}
		</div>

		{#if error}
			<p class="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
		{/if}

		{#if loading}
			<p class="text-brand-steel">Loading…</p>
		{:else if step === 0 && !lockedInterventionSlug}
			<section class="rounded-2xl border border-brand-navy/10 bg-white p-5 shadow-sm">
				<h2 class="m-0 font-headline text-lg font-semibold text-brand-navy">1. Select an intervention</h2>
				<p class="mt-2 text-sm text-brand-steel">
					Choose the intervention you are monitoring. Outcomes marked “must measure” will be included automatically.
				</p>
				<div class="mt-5 grid gap-3 sm:grid-cols-2">
					{#each interventions as item (item.slug)}
						<button
							type="button"
							class="rounded-xl border p-4 text-left transition {selectedInterventionSlug === item.slug ? 'border-[#16a34a] bg-[#dcfce7]/60 shadow-sm' : 'border-brand-navy/10 bg-white hover:border-[#16a34a]/40'}"
							onclick={() => selectIntervention(item.slug)}
						>
							<h3 class="m-0 font-headline text-sm font-semibold text-brand-navy">{item.name}</h3>
							<p class="m-0 mt-2 text-xs text-brand-steel">{item.outcome_count} outcomes in catalog</p>
						</button>
					{/each}
				</div>
				<div class="mt-6 flex justify-end">
					<button
						type="button"
						class="rounded-lg bg-[#16a34a] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
						disabled={!selectedInterventionSlug}
						onclick={goToOutcomes}
					>
						Continue
					</button>
				</div>
			</section>
		{:else if step === 1 && intervention}
			<section class="rounded-2xl border border-brand-navy/10 bg-white p-5 shadow-sm">
				<h2 class="m-0 font-headline text-lg font-semibold text-brand-navy">
					2. Select outcomes for {intervention.name}
				</h2>
				<p class="mt-2 text-sm text-brand-steel">
					{selectedCount} outcome{selectedCount === 1 ? '' : 's'} selected. Must-measure outcomes are locked on.
					Choose across biophysical, socio-economic, and watershed-level columns.
				</p>

				<div class="mt-5 grid gap-4 lg:grid-cols-3">
					{#each groupedOutcomes as [label, outcomes] (label)}
						<div class="min-w-0 rounded-xl border border-brand-navy/10 bg-brand-sky/5 p-3">
							<h3 class="m-0 border-b border-brand-navy/10 pb-2 text-sm font-semibold text-brand-navy">
								{label}
								<span class="font-normal text-brand-steel">({outcomes.length})</span>
							</h3>
							<div class="mt-3 max-h-[28rem] space-y-2 overflow-y-auto pr-1">
								{#each outcomes as outcome (outcome.id)}
									<div
										class="overflow-hidden rounded-lg border transition {outcome.must_measure || selectedOutcomeIds.includes(outcome.id) ? 'border-[#16a34a]/40 bg-white' : 'border-brand-navy/10 bg-white'}"
									>
										<div class="flex items-start gap-2 p-3">
											<input
												type="checkbox"
												class="mt-1 shrink-0"
												checked={outcome.must_measure || selectedOutcomeIds.includes(outcome.id)}
												disabled={outcome.must_measure}
												onchange={() => toggleOutcome(outcome)}
											/>
											<button
												type="button"
												class="min-w-0 flex-1 cursor-pointer border-0 bg-transparent p-0 text-left"
												onclick={() => toggleExpanded(outcome.id)}
											>
												<span class="block text-sm font-medium text-brand-navy">{outcomeTitle(outcome)}</span>
												<div class="mt-1.5 flex flex-wrap items-center gap-2">
													{#if outcome.must_measure}
														<span class="inline-block rounded-full bg-brand-forest/10 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-brand-forest uppercase">
															Must measure
														</span>
													{/if}
													{#if outcome.indicators.length}
														<span class="text-xs text-brand-steel">
															{outcome.indicators.length} indicator{outcome.indicators.length === 1 ? '' : 's'}
														</span>
													{/if}
												</div>
											</button>
										</div>
										{#if isExpanded(outcome.id)}
											<div class="border-t border-brand-navy/8 px-3 pb-3 pl-9">
												{#if outcome.assumptions}
													<div class="mt-2">
														<h4 class="m-0 text-[11px] font-semibold tracking-wide text-brand-steel uppercase">Assumptions</h4>
														<p class="m-0 mt-1 whitespace-pre-line text-xs leading-relaxed text-brand-navy/90">{outcome.assumptions}</p>
													</div>
												{/if}
												{#if outcome.indicators.length}
													<div class="mt-2">
														<h4 class="m-0 text-[11px] font-semibold tracking-wide text-brand-steel uppercase">Indicators</h4>
														<ul class="m-0 mt-1 list-disc space-y-1 pl-4 text-xs text-brand-navy">
															{#each outcome.indicators as indicator (indicator)}
																<li>{indicator}</li>
															{/each}
														</ul>
													</div>
												{:else}
													<p class="m-0 mt-2 text-xs text-brand-steel">No indicators listed.</p>
												{/if}
											</div>
										{/if}
									</div>
								{/each}
							</div>
						</div>
					{/each}
				</div>
				<div class="mt-6 flex justify-between">
					<button
						type="button"
						class="action-btn"
						onclick={() => (lockedInterventionSlug ? onBack() : (step = 0))}
					>
						Back
					</button>
					<button
						type="button"
						class="rounded-lg bg-[#16a34a] px-4 py-2 text-sm font-medium text-white"
						onclick={goToPackages}
					>
						Continue to MEL types
					</button>
				</div>
			</section>
		{:else if step === 2}
			<section class="space-y-5">
				<div>
					<h2 class="m-0 font-headline text-lg font-semibold text-brand-navy">3. MEL types</h2>
					<p class="mt-1 text-sm text-brand-steel">
						Packages derived from your outcomes. Export the plan, or continue to choose forms for ODK.
					</p>
				</div>

				{#if packagePayload?.unmatched_indicators?.length}
					<div class="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
						<p class="m-0">
							{packagePayload.unmatched_indicators.length} indicator{packagePayload.unmatched_indicators.length === 1 ? '' : 's'}
							had no measurement recipe and will appear in the PDF only
							(not in auto-generated ODK packages):
						</p>
						<ul class="mb-0 mt-2 list-disc space-y-1 pl-5">
							{#each packagePayload.unmatched_indicators as ind (ind.id || ind.indicator)}
								<li>
									<span class="font-medium">{ind.indicator || ind.label || 'Untitled indicator'}</span>
									{#if ind.outcome}
										<span class="text-amber-800/80"> · {ind.outcome}</span>
									{/if}
								</li>
							{/each}
						</ul>
					</div>
				{/if}

				{#if packages.length === 0}
					<div class="rounded-xl border border-brand-navy/10 bg-gray-50 px-6 py-10 text-center text-sm text-brand-steel">
						No schedule packages could be built from the selected indicators. You can still export the MEL plan PDF.
					</div>
				{:else}
					<div class="grid gap-4 lg:grid-cols-3">
						{#each familyGroups as group (group.family)}
							<div class="min-w-0 rounded-xl border border-brand-navy/10 bg-white p-4">
								<h3 class="m-0 text-sm font-semibold text-brand-navy">
									{group.label}
									<span class="font-normal text-brand-steel">({group.items.length})</span>
								</h3>
								<div class="mt-3 space-y-3">
									{#each group.items as pkg (pkg.id)}
										<div class="rounded-lg border border-brand-navy/10 bg-brand-sky/5 p-3">
											<div class="flex flex-wrap items-center gap-2">
												<span class="text-sm font-semibold text-brand-navy">{pkg.title}</span>
												<span class="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-brand-steel uppercase">
													{pkg.suggested_fields?.length ?? 0} fields
												</span>
											</div>
											<p class="m-0 mt-1 text-xs text-brand-steel">{pkg.description}</p>
											<p class="m-0 mt-1 text-xs text-brand-steel">When: {pkg.frequency_label}</p>
											<ul class="m-0 mt-2 list-disc space-y-0.5 pl-4 text-xs text-brand-navy">
												{#each pkg.indicators as ind (ind.id + ind.indicator)}
													<li>{ind.indicator}</li>
												{/each}
											</ul>
										</div>
									{/each}
								</div>
							</div>
						{/each}
					</div>
				{/if}

				<div class="flex flex-wrap items-center justify-between gap-3 border-t border-brand-navy/10 pt-4">
					<button type="button" class="action-btn" onclick={() => (step = 1)}>Back</button>
					<div class="flex flex-wrap gap-2">
						<button
							type="button"
							class="rounded-lg border border-brand-navy/20 bg-white px-4 py-2 text-sm font-medium text-brand-navy hover:bg-brand-sky/15 disabled:opacity-50"
							disabled={exportingPdf || !selectedInterventionSlug}
							onclick={handleExportPdf}
						>
							{exportingPdf ? 'Exporting…' : 'Export MEL plan'}
						</button>
						<button
							type="button"
							class="rounded-lg bg-[#16a34a] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
							disabled={!packages.length}
							onclick={goToEditForms}
						>
							Edit forms for ODK
						</button>
					</div>
				</div>
			</section>
		{:else if step === 3}
			<section class="space-y-4">
				<div>
					<h2 class="m-0 font-headline text-lg font-semibold text-brand-navy">4. Select & edit ODK forms</h2>
					<p class="mt-1 text-sm text-brand-steel">
						Choose which MEL types to publish, then edit fields for each selected form.
					</p>
				</div>

				<div class="grid gap-4 lg:grid-cols-3">
					{#each familyGroups as group (group.family)}
						<div class="min-w-0 rounded-xl border border-brand-navy/10 bg-white p-4">
							<h3 class="m-0 text-sm font-semibold text-brand-navy">{group.label}</h3>
							<div class="mt-3 space-y-2">
								{#each group.items as pkg (pkg.id)}
									<label
										class="flex cursor-pointer gap-2 rounded-lg border p-3 transition {selectedPackageIds.includes(pkg.id) ? 'border-[#16a34a] bg-[#dcfce7]/50' : 'border-brand-navy/10'}"
									>
										<input
											type="checkbox"
											class="mt-0.5"
											checked={selectedPackageIds.includes(pkg.id)}
											onchange={() => togglePackage(pkg.id)}
										/>
										<span class="min-w-0">
											<span class="block text-sm font-semibold text-brand-navy">{pkg.title}</span>
											<span class="mt-0.5 block text-xs text-brand-steel">
												{pkg.suggested_fields?.length ?? 0} fields · {pkg.frequency_label}
											</span>
										</span>
									</label>
								{/each}
							</div>
						</div>
					{/each}
				</div>

				{#if selectedPackages.length}
					<div class="flex flex-wrap gap-2 border-t border-brand-navy/10 pt-4">
						{#each selectedPackages as pkg (pkg.id)}
							<button
								type="button"
								class="rounded-lg px-3 py-1.5 text-xs font-semibold tracking-wide uppercase {activeEditPackageId === pkg.id ? 'bg-[#16a34a] text-white' : 'border border-brand-navy/15 bg-white text-brand-navy'}"
								onclick={() => (activeEditPackageId = pkg.id)}
							>
								{pkg.title}
							</button>
						{/each}
					</div>
				{:else}
					<p class="rounded-lg border border-dashed border-brand-navy/20 bg-gray-50 px-4 py-6 text-center text-sm text-brand-steel">
						Select at least one MEL type above to edit its ODK form.
					</p>
				{/if}

				{#if activeEditPackageId && selectedPackageIds.includes(activeEditPackageId)}
					{@const pkg = packages.find((item) => item.id === activeEditPackageId)}
					{@const fields = packageFields[activeEditPackageId] ?? []}
					{#if pkg}
						<div class="rounded-xl border border-brand-navy/10 bg-white p-5 shadow-sm">
							<div class="mb-4 flex flex-wrap items-end justify-between gap-3">
								<div class="grid min-w-[240px] flex-1 gap-1 text-sm">
									<span class="font-medium text-brand-steel">ODK form name</span>
									<p
										class="m-0 rounded-lg border border-brand-navy/10 bg-brand-pale/40 px-2.5 py-2 text-sm text-brand-navy"
									>
										{odkFormTitle(pkg)}
									</p>
								</div>
								<button
									type="button"
									class="rounded-lg bg-[#16a34a] px-3 py-2 text-sm font-semibold text-white"
									onclick={() => addCustomField(pkg.id)}
								>
									+ Add field
								</button>
							</div>

							{#if fields.length === 0}
								<p class="text-sm text-brand-steel">No fields yet. Add a custom field.</p>
							{:else}
								<div class="space-y-4">
									{#each fields as field, index (field.id)}
										<div class="rounded-xl border border-brand-navy/10 bg-white p-4">
											<div class="mb-3 flex items-center justify-between gap-2">
												<div class="flex flex-wrap items-center gap-2">
													<span class="text-xs font-mono text-brand-steel">{index + 1}.</span>
													<span class="font-semibold text-brand-navy">{field.label || `Field ${index + 1}`}</span>
													{#if field.locked}
														<span class="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-800">required</span>
													{:else if field.custom}
														<span class="rounded bg-brand-forest/10 px-1.5 py-0.5 text-xs font-medium text-brand-forest">custom</span>
													{:else}
														<span class="rounded bg-brand-sky/30 px-1.5 py-0.5 text-xs font-medium text-brand-navy">catalog</span>
													{/if}
												</div>
												<div class="flex items-center gap-1">
													<button
														type="button"
														class="rounded border border-brand-navy/15 px-2 py-1 text-xs text-brand-navy hover:bg-brand-sky/15 disabled:opacity-40"
														disabled={index === 0}
														onclick={() => moveField(pkg.id, field.id, -1)}
														title="Move up"
													>
														↑
													</button>
													<button
														type="button"
														class="rounded border border-brand-navy/15 px-2 py-1 text-xs text-brand-navy hover:bg-brand-sky/15 disabled:opacity-40"
														disabled={index === fields.length - 1}
														onclick={() => moveField(pkg.id, field.id, 1)}
														title="Move down"
													>
														↓
													</button>
													{#if !field.locked}
														<button
															type="button"
															class="text-xs text-brand-steel hover:text-red-600"
															onclick={() => removeField(pkg.id, field.id)}
														>
															Remove
														</button>
													{/if}
												</div>
											</div>
											<div class="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-3">
												<label class="grid gap-1 text-sm">
													<span class="font-medium text-brand-steel">Display label</span>
													{#if field.locked}
														<p class="m-0 rounded-lg border border-brand-navy/10 bg-brand-pale/40 px-2.5 py-2 text-sm text-brand-navy">
															{field.label}
														</p>
													{:else}
														<input
															type="text"
															class={fieldClass}
															value={field.label}
															oninput={(e) =>
																updatePackageField(pkg.id, field.id, { label: e.currentTarget.value })}
														/>
													{/if}
												</label>
												<label class="grid gap-1 text-sm sm:col-span-full md:col-span-1">
													<span class="font-medium text-brand-steel">Field name</span>
													<p
														class="m-0 rounded-lg border border-brand-navy/10 bg-brand-pale/40 px-2.5 py-2 font-mono text-sm text-brand-steel"
														title="Generated from the display label"
													>
														{field.field_name || fieldNameFromLabel(field.label, index + 1)}
													</p>
												</label>
												<label class="grid gap-1 text-sm">
													<span class="font-medium text-brand-steel">Input type</span>
													{#if field.locked}
														<p class="m-0 rounded-lg border border-brand-navy/10 bg-brand-pale/40 px-2.5 py-2 text-sm text-brand-navy">
															{inputTypes.find((t) => t.id === field.input_type)?.label || field.input_type}
														</p>
													{:else}
														<select
															class={fieldClass}
															value={field.input_type}
															onchange={(e) => {
																const newType = e.currentTarget.value;
																const patch = { input_type: newType };
																if (usesOptions(newType) && !(field.options?.length)) {
																	patch.options = defaultOptionsForType(newType);
																}
																updatePackageField(pkg.id, field.id, patch);
															}}
														>
															{#each inputTypes as option (option.id)}
																<option value={option.id}>{option.label}</option>
															{/each}
														</select>
													{/if}
												</label>
												<label class="grid gap-1 text-sm">
													<span class="font-medium text-brand-steel">Hint</span>
													{#if field.locked}
														<p class="m-0 rounded-lg border border-brand-navy/10 bg-brand-pale/40 px-2.5 py-2 text-sm text-brand-steel">
															{field.hint || '—'}
														</p>
													{:else}
														<input
															type="text"
															class={fieldClass}
															value={field.hint}
															oninput={(e) =>
																updatePackageField(pkg.id, field.id, { hint: e.currentTarget.value })}
														/>
													{/if}
												</label>
											</div>

											{#if usesOptions(field.input_type)}
												<div class="mt-4 border-t border-brand-navy/8 pt-4">
													<p class="m-0 mb-2 text-xs font-semibold tracking-wide text-brand-steel uppercase">
														{field.input_type === 'select_multiple' ? 'Checkbox options' : 'Dropdown options'}
													</p>
													<div class="space-y-2">
														{#each field.options ?? [] as opt, oi}
															<div class="flex items-center gap-2">
																<input
																	type="text"
																	class="{fieldClass} flex-1"
																	placeholder="Stored value"
																	value={opt.value}
																	oninput={(e) =>
																		updateOption(pkg.id, field.id, oi, 'value', e.currentTarget.value)}
																/>
																<input
																	type="text"
																	class="{fieldClass} flex-1"
																	placeholder="Displayed label"
																	value={opt.label}
																	oninput={(e) =>
																		updateOption(pkg.id, field.id, oi, 'label', e.currentTarget.value)}
																/>
																<button
																	type="button"
																	class="shrink-0 text-brand-steel hover:text-red-600"
																	onclick={() => removeOption(pkg.id, field.id, oi)}
																>
																	✕
																</button>
															</div>
														{/each}
														<button
															type="button"
															class="mt-1 text-sm font-semibold text-[#16a34a] hover:underline"
															onclick={() => addOption(pkg.id, field.id)}
														>
															+ Add option
														</button>
													</div>
												</div>
											{/if}
										</div>
									{/each}
								</div>
							{/if}
						</div>
					{/if}
				{/if}

				<div class="flex justify-between pt-2">
					<button type="button" class="action-btn" onclick={() => (step = 2)}>Back</button>
					<button
						type="button"
						class="rounded-lg bg-[#16a34a] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
						disabled={!selectedPackageIds.length}
						onclick={goToPublish}
					>
						Continue to publish
					</button>
				</div>
			</section>
		{:else if step === 4}
			<section class="rounded-2xl border border-brand-navy/10 bg-white p-5 shadow-sm">
				<h2 class="m-0 font-headline text-lg font-semibold text-brand-navy">
					{isUpdatingExisting ? 'Publish updated forms' : 'Publish to ODK'}
				</h2>
				<p class="mt-2 text-sm text-brand-steel">
					{#if isUpdatingExisting}
						{selectedPackages.length} form{selectedPackages.length === 1 ? '' : 's'} will get a new
						version in ODK Central (same form id{selectedPackages.length === 1 ? '' : 's'}).
					{:else}
						{selectedPackages.length} form{selectedPackages.length === 1 ? '' : 's'} will be published
						into the configured ODK project.
					{/if}
				</p>

				{#if createdForms.length}
					<div class="mt-5 rounded-xl border border-brand-forest/25 bg-brand-forest/5 p-4">
						<p class="m-0 text-sm font-medium text-brand-forest">
							{createdForms.some((f) => f.updated)
								? 'Form versions published successfully.'
								: 'Forms published successfully.'}
						</p>
						<p class="m-0 mt-1 text-sm text-brand-steel">
							Scan a QR with ODK Collect to pull these forms onto a device.
						</p>
						<div class="mt-4 flex flex-col gap-3">
							{#each createdForms as form (form.xmlFormId)}
								<MelFormQrCard
									formName={form.name || form.packageTitle}
									packageTitle={form.packageTitle}
									xmlFormId={form.xmlFormId}
									fieldCount={form.fieldCount}
									collectQr={form.collectQr || publishedCollectQr}
								/>
							{/each}
						</div>
						<div class="mt-4 flex flex-wrap gap-2">
							<button type="button" class="action-btn" onclick={handleExportPdf} disabled={exportingPdf}>
								{exportingPdf ? 'Exporting…' : 'Export PDF'}
							</button>
							<button type="button" class="action-btn" onclick={onBack}>Back to plan</button>
						</div>
					</div>
				{:else}
					<ul class="mt-4 space-y-2">
						{#each selectedPackages as pkg (pkg.id)}
							<li class="rounded-lg border border-brand-navy/10 px-4 py-3 text-sm">
								<span class="font-semibold text-brand-navy">{odkFormTitle(pkg)}</span>
								<span class="text-brand-steel">
									· {(packageFields[pkg.id] ?? []).length} fields · {pkg.schedule}
									{#if existingXmlFormByPackage[pkg.id]}
										· update {existingXmlFormByPackage[pkg.id]}
									{/if}
								</span>
							</li>
						{/each}
					</ul>
					<div class="mt-6 flex justify-between">
						<button type="button" class="action-btn" onclick={() => (step = 3)}>Back</button>
						<button
							type="button"
							class="rounded-lg bg-[#16a34a] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
							disabled={saving}
							onclick={handlePublish}
						>
							{#if saving}
								Publishing…
							{:else if isUpdatingExisting}
								Publish new versions
							{:else}
								Publish selected forms
							{/if}
						</button>
					</div>
				{/if}
			</section>
		{/if}
	</main>
</div>

<style>
	.action-btn {
		cursor: pointer;
		border-radius: 0.5rem;
		border: 1px solid rgba(20, 40, 60, 0.12);
		background: white;
		padding: 0.4rem 0.75rem;
		font-family: inherit;
		font-size: 0.8125rem;
		font-weight: 500;
		color: #1a2530;
	}
</style>
