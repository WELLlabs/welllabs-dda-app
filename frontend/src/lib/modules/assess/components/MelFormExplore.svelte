<script>
	import { onMount } from 'svelte';
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';
	import { assessCrumbs } from '$lib/modules/assess/breadcrumbs.js';
	import { fetchMelFormSubmissions } from '$lib/modules/assess/mel-api';
	import {
		groupSites,
		loadExplorePrefs,
		numericColumns,
		pickExploreDefaults,
		saveExplorePrefs,
		SITE_COORD_COLUMN,
		sitePickerColumns,
		sitePickerValues
	} from '$lib/modules/assess/form-explore.js';
	import FormExploreTable from './FormExploreTable.svelte';
	import FormExploreMap from './FormExploreMap.svelte';

	/** @type {{ project: any, plan: any, projects?: any[], xmlFormId: string }} */
	let { project, plan, projects = [], xmlFormId } = $props();

	let loading = $state(true);
	let error = $state('');
	let formName = $state('');
	let columns = $state([]);
	let rows = $state([]);
	let tab = $state('map');
	/** @type {any} */
	let prefs = $state(null);
	let selectedSiteKey = $state(null);
	let pickerColumn = $state(SITE_COORD_COLUMN);

	const headerTitle = $derived(formName || xmlFormId || 'Form');
	const crumbs = $derived(assessCrumbs({ projects, project, plan, form: headerTitle }));
	const nums = $derived(numericColumns(columns));
	const sites = $derived(groupSites(rows));
	const hasCoords = $derived(sites.length > 0);
	const pickerColumns = $derived(sitePickerColumns(sites, columns));
	const pickerValues = $derived(sitePickerValues(sites, pickerColumn));
	const selectedPickerValue = $derived.by(() => {
		const match = pickerValues.find((v) => v.siteKey === selectedSiteKey);
		return match?.value ?? '';
	});

	$effect(() => {
		if (!selectedSiteKey && sites.length) selectedSiteKey = sites[0].key;
	});

	$effect(() => {
		const names = new Set(pickerColumns.map((c) => c.name));
		if (!names.has(pickerColumn)) pickerColumn = SITE_COORD_COLUMN;
	});

	onMount(load);

	async function load() {
		loading = true;
		error = '';
		try {
			const data = await fetchMelFormSubmissions(project.id, plan.id, xmlFormId);
			columns = data.columns ?? [];
			rows = data.rows ?? [];
			formName = data.formName || xmlFormId;
			const defaults = pickExploreDefaults(columns, rows);
			const saved = loadExplorePrefs(xmlFormId) || {};
			prefs = {
				...defaults,
				...saved,
				dateField: saved.dateField || defaults.dateField,
				barField: saved.barField || defaults.barField,
				lineField: saved.lineField || defaults.lineField,
				boxField: saved.boxField || defaults.boxField,
				timeGrain: saved.timeGrain || defaults.timeGrain,
				lineTimeGrain: saved.lineTimeGrain || defaults.lineTimeGrain,
				boxTimeGrain: saved.boxTimeGrain || defaults.boxTimeGrain
			};
			if (!prefs.barField && nums[0]) prefs.barField = nums[0].name;
			if (!prefs.boxField && (prefs.barField || nums[0])) {
				prefs.boxField = prefs.barField || nums[0].name;
			}
		} catch (err) {
			error = String(err);
		} finally {
			loading = false;
		}
	}

	function patchPrefs(patch) {
		prefs = { ...prefs, ...patch };
		saveExplorePrefs(xmlFormId, prefs);
	}

	function onPickerColumnChange(e) {
		pickerColumn = e.currentTarget.value || SITE_COORD_COLUMN;
		const values = sitePickerValues(sites, pickerColumn);
		if (!values.some((v) => v.siteKey === selectedSiteKey) && values.length) {
			selectedSiteKey = values[0].siteKey;
		}
	}

	function onPickerValueChange(e) {
		const value = e.currentTarget.value;
		const match = pickerValues.find((v) => v.value === value);
		if (match) selectedSiteKey = match.siteKey;
	}
</script>

<div class="relative flex min-h-screen flex-col bg-transparent font-body">
	<ModuleHeader title="Assess" titleHref="/assess" wide fullProjectTitle {crumbs}>
		<button
			type="button"
			class="icon-btn"
			disabled={loading}
			onclick={load}
			aria-label={loading ? 'Refreshing' : 'Refresh'}
			title={loading ? 'Refreshing…' : 'Refresh'}
		>
			<svg
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				stroke-width="2"
				class="h-4 w-4 {loading ? 'animate-spin' : ''}"
				aria-hidden="true"
			>
				<path
					d="M21 12a9 9 0 1 1-2.64-6.36"
					stroke-linecap="round"
					stroke-linejoin="round"
				/>
				<path d="M21 3v6h-6" stroke-linecap="round" stroke-linejoin="round" />
			</svg>
		</button>
	</ModuleHeader>

	{#if error}
		<p class="mx-6 mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 font-body text-sm text-red-700">
			{error}
		</p>
	{/if}

	{#if loading}
		<p class="p-6 font-body text-brand-steel">Loading submissions…</p>
	{:else if rows.length === 0}
		<div class="m-6 rounded-xl border border-dashed border-brand-navy/20 bg-gray-50 px-6 py-12 text-center font-body text-sm text-[#56646f]">
			No submissions yet for this form. Collect data in ODK Collect, then refresh.
		</div>
	{:else if prefs}
		<div class="explore-layout">
			<aside class="explore-nav">
				<p class="nav-label">Form data</p>
				<p class="nav-meta">
					{rows.length} submission{rows.length === 1 ? '' : 's'}
					{#if hasCoords}
						· {sites.length} site{sites.length === 1 ? '' : 's'}
					{/if}
				</p>
				<nav class="nav-tabs" aria-label="Form data views">
					<button
						type="button"
						class="nav-tab"
						class:active={tab === 'map'}
						onclick={() => (tab = 'map')}
					>
						Map
					</button>
					<button
						type="button"
						class="nav-tab"
						class:active={tab === 'table'}
						onclick={() => (tab = 'table')}
					>
						Table
					</button>
				</nav>
			</aside>

			<section class="explore-main" class:scrollable={tab === 'table'}>
				{#if tab === 'table'}
					<FormExploreTable {columns} {rows} />
				{:else if !hasCoords}
					<div
						class="rounded-xl border border-dashed border-brand-navy/20 bg-gray-50 px-6 py-10 text-center font-body text-sm text-[#56646f]"
					>
						No coordinates in these submissions — map view needs a geopoint field.
					</div>
				{:else}
					<div class="site-picker" aria-label="Select site">
						<label class="picker-ctrl">
							<span class="picker-label">Select column</span>
							<select class="picker-select" value={pickerColumn} onchange={onPickerColumnChange}>
								{#each pickerColumns as col (col.name)}
									<option value={col.name}>
										{col.label}{col.unique && col.name !== SITE_COORD_COLUMN ? ' · unique' : ''}
									</option>
								{/each}
							</select>
						</label>
						<label class="picker-ctrl">
							<span class="picker-label">Selected value</span>
							<select
								class="picker-select"
								value={selectedPickerValue}
								onchange={onPickerValueChange}
								disabled={!pickerValues.length}
							>
								{#if !pickerValues.length}
									<option value="">No values</option>
								{:else}
									{#each pickerValues as opt (opt.value + opt.siteKey)}
										<option value={opt.value}>{opt.label}</option>
									{/each}
								{/if}
							</select>
						</label>
						<p class="picker-hint">
							{sites.length} site{sites.length === 1 ? '' : 's'} · or click a point on the map
						</p>
					</div>
					<FormExploreMap
						{sites}
						{columns}
						numericFields={nums}
						{prefs}
						onPrefs={patchPrefs}
						bind:selectedKey={selectedSiteKey}
					/>
				{/if}
			</section>
		</div>
	{/if}
</div>

<style>
	.explore-layout {
		display: grid;
		grid-template-columns: 13.5rem minmax(0, 1fr);
		flex: 1;
		min-height: calc(100vh - 4rem);
		border-top: 1px solid rgba(20, 40, 60, 0.08);
	}
	.explore-nav {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		padding: 1.25rem 1rem;
		border-right: 1px solid rgba(20, 40, 60, 0.08);
		background: #f8faf8;
	}
	.nav-label {
		margin: 0;
		font-family: var(--font-headline);
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: #1b75e0;
	}
	.nav-meta {
		margin: 0;
		font-family: var(--font-body);
		font-size: 0.75rem;
		line-height: 1.4;
		color: #6b7885;
	}
	.nav-tabs {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		margin-top: 0.5rem;
	}
	.nav-tab {
		border: 1px solid transparent;
		border-radius: 0.65rem;
		background: transparent;
		padding: 0.65rem 0.85rem;
		text-align: left;
		font-family: var(--font-body);
		font-size: 0.875rem;
		font-weight: 600;
		color: #56646f;
		cursor: pointer;
		transition:
			background 0.15s ease,
			border-color 0.15s ease,
			color 0.15s ease;
	}
	.nav-tab:hover {
		background: white;
		border-color: rgba(22, 163, 74, 0.2);
	}
	.nav-tab.active {
		background: white;
		border-color: color-mix(in srgb, #1b75e0 35%, transparent);
		color: #1b75e0;
		box-shadow: 0 1px 4px rgba(20, 40, 60, 0.06);
	}
	.explore-main {
		min-width: 0;
		min-height: 0;
		padding: 1rem 1.25rem 1.25rem;
		overflow: hidden;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}
	.explore-main.scrollable {
		overflow: auto;
	}
	.explore-main :global(.map-shell) {
		flex: 1;
		min-height: 0;
		height: auto;
	}
	.site-picker {
		display: flex;
		flex-wrap: wrap;
		align-items: end;
		gap: 0.75rem;
		flex-shrink: 0;
		padding: 0.75rem 0.9rem;
		border-radius: 0.75rem;
		border: 1px solid rgba(20, 40, 60, 0.12);
		background: white;
	}
	.picker-ctrl {
		display: grid;
		gap: 0.25rem;
		min-width: min(100%, 14rem);
		flex: 1 1 12rem;
	}
	.picker-label {
		font-family: var(--font-body);
		font-size: 0.8125rem;
		font-weight: 600;
		color: #1a2530;
	}
	.picker-select {
		width: 100%;
		border-radius: 0.45rem;
		border: 1px solid rgba(20, 40, 60, 0.2);
		background: white;
		padding: 0.45rem 0.6rem;
		font-family: var(--font-body);
		font-size: 0.875rem;
		color: #1a2530;
	}
	.picker-select:disabled {
		opacity: 0.55;
	}
	.picker-hint {
		margin: 0 0 0.35rem auto;
		font-size: 0.75rem;
		font-family: var(--font-mono, ui-monospace, monospace);
		color: #6b7885;
	}
	@media (max-width: 800px) {
		.explore-layout {
			grid-template-columns: 1fr;
		}
		.explore-nav {
			border-right: 0;
			border-bottom: 1px solid rgba(20, 40, 60, 0.08);
		}
		.nav-tabs {
			flex-direction: row;
		}
		.picker-hint {
			margin-left: 0;
			width: 100%;
		}
	}
</style>
