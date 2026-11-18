<script>
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';
	import LocationPicker from '$lib/shared/components/LocationPicker.svelte';
	import SearchableSelect from '$lib/shared/components/SearchableSelect.svelte';
	import WatershedThumb from '$lib/shared/components/WatershedThumb.svelte';
	import { itemPath } from '$lib/shared/slug.js';
	import { parseAoiFile } from '$lib/modules/diagnose/aoi-parse.js';
	import {
		createDesignProject,
		deleteDesignProject,
		fetchDesignProjects,
		fetchImportableAoi,
		fetchImportableAois,
		fetchWatershedPreviewContext,
		lookupWatershed,
		searchPlaces,
		watershedsFromGeometry,
		watershedsFromPoint
	} from '$lib/modules/design/api.js';

	const ACCENT = '#0d983b';

	/** @typedef {'diagnosis' | 'point' | 'village' | 'custom'} Mode */
	const MODES = /** @type {Array<{ id: Mode, label: string }>} */ ([
		{ id: 'diagnosis', label: 'From PD project' },
		{ id: 'point', label: 'Map click' },
		{ id: 'village', label: 'Village' },
		{ id: 'custom', label: 'Upload AOI' }
	]);

	let projects = $state([]);
	let loading = $state(true);
	let error = $state('');
	let mounted = $state(false);
	let showCreate = $state(false);
	let creating = $state(false);
	let openMenuId = $state(null);
	let deletingId = $state(null);

	let name = $state('');
	let lng = $state(78.5);
	let lat = $state(18.0);
	/** @type {Mode} */
	let selectMode = $state('diagnosis');
	/** @type {any} */
	let preview = $state(null);
	let previewLoading = $state(false);
	/** @type {'all' | string} */
	let microChoice = $state('all');
	let contextLayers = $state([]);
	let contextLoading = $state(false);

	// From PD project
	let pdProjects = $state([]);
	let pdLoading = $state(false);
	let pdError = $state('');
	let pdChoice = $state('');

	// Map click
	let coordInput = $state('');
	let coordError = $state('');

	// Village search
	let placeQuery = $state('');
	/** @type {Array<{ label: string, lat: number, lng: number, type?: string }>} */
	let placeResults = $state([]);
	let placeSearching = $state(false);
	let placeError = $state('');
	/** @type {ReturnType<typeof setTimeout> | null} */
	let placeDebounce = null;

	// Upload
	let uploadName = $state('');
	let uploadError = $state('');

	/** @type {AbortController | null} */
	let previewAbort = null;
	/** @type {AbortController | null} */
	let contextAbort = null;
	/** @type {AbortController | null} */
	let placeAbort = null;
	let contextGen = 0;

	onMount(() => {
		loadProjects();
		mounted = true;
		const closeMenu = () => (openMenuId = null);
		document.addEventListener('click', closeMenu);
		return () => {
			document.removeEventListener('click', closeMenu);
			if (placeDebounce) clearTimeout(placeDebounce);
			abortAll();
		};
	});

	function abortAll() {
		previewAbort?.abort();
		contextAbort?.abort();
		placeAbort?.abort();
		previewAbort = contextAbort = placeAbort = null;
		contextGen += 1;
		contextLoading = false;
	}

	async function loadProjects() {
		loading = true;
		error = '';
		try {
			const data = await fetchDesignProjects();
			projects = data.projects ?? [];
		} catch (err) {
			error = String(err);
		} finally {
			loading = false;
		}
	}

	async function loadPdProjects() {
		if (pdProjects.length || pdLoading) return;
		pdLoading = true;
		pdError = '';
		try {
			pdProjects = await fetchImportableAois();
			if (!pdProjects.length) pdError = 'You have no Problem Diagnosis projects to import from yet.';
		} catch (err) {
			pdError = String(err);
		} finally {
			pdLoading = false;
		}
	}

	function titleCase(s) {
		return String(s || '')
			.split(/\s+/)
			.map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
			.join(' ');
	}

	function formatCoordInput(latVal, lon) {
		return `${Number(latVal).toFixed(5)}, ${Number(lon).toFixed(5)}`;
	}

	function resetSelection() {
		abortAll();
		preview = null;
		previewLoading = false;
		microChoice = 'all';
		contextLayers = [];
		placeQuery = '';
		placeResults = [];
		placeError = '';
		uploadName = '';
		uploadError = '';
		coordError = '';
		pdChoice = '';
	}

	/** @param {Mode} mode */
	function setMode(mode) {
		selectMode = mode;
		resetSelection();
		if (mode === 'point') coordInput = formatCoordInput(lat, lng);
		if (mode === 'diagnosis') void loadPdProjects();
	}

	function openCreate() {
		showCreate = true;
		error = '';
		name = '';
		setMode('diagnosis');
	}

	// ---------------------------------------------------------------- preview helpers

	const multiMicroParts = $derived(
		Array.isArray(preview?.parts) && preview.parts.length > 1 ? preview.parts : []
	);

	function withMicroChoice(base, choice) {
		if (!base || base.error) return base;
		const parts = Array.isArray(base.parts) ? base.parts : [];
		if (parts.length <= 1) return base;
		if (choice === 'all' && base.all_geometry) {
			return {
				...base,
				geometry: base.all_geometry,
				watershed_name: base.all_watershed_name ?? base.watershed_name,
				bounds: base.all_bounds ?? base.bounds
			};
		}
		const part = parts.find((p) => String(p.watershed_id) === String(choice));
		if (!part?.geometry) return base;
		return { ...base, geometry: part.geometry, watershed_name: part.watershed_name, bounds: part.bounds ?? base.bounds };
	}

	function setPreview(result, defaultMode = 'all') {
		const parts = Array.isArray(result?.parts) ? result.parts : [];
		let choice = 'all';
		if (parts.length > 1 && defaultMode === 'point' && result.watershed_id) choice = String(result.watershed_id);
		else if (parts.length === 1) choice = String(parts[0].watershed_id ?? 'all');
		microChoice = choice;
		const enriched =
			parts.length > 1 && !result.all_geometry && result.geometry
				? {
						...result,
						all_geometry: result.geometry,
						all_watershed_name: result.watershed_name,
						all_bounds: result.bounds
					}
				: result;
		preview = withMicroChoice(enriched, choice);
	}

	function onMicroChoiceChange(choice) {
		microChoice = choice;
		if (!preview || preview.error) return;
		preview = withMicroChoice(preview, choice);
		if (preview.geometry) void loadContext(preview.geometry);
	}

	async function loadContext(geometry) {
		contextAbort?.abort();
		contextAbort = new AbortController();
		const { signal } = contextAbort;
		const gen = ++contextGen;
		contextLoading = true;
		try {
			const data = await fetchWatershedPreviewContext(geometry, { signal, includeRivers: true });
			if (gen !== contextGen || signal.aborted) return;
			contextLayers = data.layers ?? [];
		} catch (err) {
			if (signal.aborted || err?.name === 'AbortError') return;
			console.error('Preview context failed', err);
		} finally {
			if (gen === contextGen) contextLoading = false;
		}
	}

	/** @returns {AbortSignal} */
	function startPreview() {
		previewAbort?.abort();
		previewAbort = new AbortController();
		previewLoading = true;
		preview = null;
		contextLayers = [];
		return previewAbort.signal;
	}

	// ---------------------------------------------------------------- From PD project

	async function onPdChoice(id) {
		pdChoice = id;
		if (!id) return;
		const signal = startPreview();
		try {
			const result = await fetchImportableAoi(id, { signal });
			if (signal.aborted) return;
			preview = { ...result, source: 'diagnosis' };
			if (!name.trim()) name = result.name;
		} catch (err) {
			if (signal.aborted || err?.name === 'AbortError') return;
			preview = { error: String(err) };
		} finally {
			if (!signal.aborted) previewLoading = false;
		}
	}

	const pdOptions = $derived(
		pdProjects.map((p) => ({
			value: p.id,
			label: p.area_ha ? `${p.name} · ${Math.round(p.area_ha).toLocaleString()} ha` : p.name
		}))
	);

	// ---------------------------------------------------------------- Map click

	async function previewFromPoint() {
		coordInput = formatCoordInput(lat, lng);
		const signal = startPreview();
		try {
			const result = await lookupWatershed(lng, lat, { signal });
			if (signal.aborted) return;
			setPreview({ ...result, source: 'point' }, 'point');
			if (preview?.geometry) void loadContext(preview.geometry);
		} catch (err) {
			if (signal.aborted || err?.name === 'AbortError') return;
			preview = { error: String(err) };
		} finally {
			if (!signal.aborted) previewLoading = false;
		}
	}

	function applyCoordinates() {
		coordError = '';
		const parts = coordInput.trim().split(/[,;\s]+/).filter(Boolean);
		const a = Number.parseFloat(parts[0]);
		const b = Number.parseFloat(parts[1]);
		if (parts.length !== 2 || !Number.isFinite(a) || !Number.isFinite(b)) {
			coordError = 'Use latitude, longitude — e.g. 18.0432, 78.2615';
			return;
		}
		let latVal = a;
		let lon = b;
		if (Math.abs(a) > 90 && Math.abs(b) <= 90) [lon, latVal] = [a, b];
		if (Math.abs(latVal) > 90 || Math.abs(lon) > 180) {
			coordError = 'Coordinates are out of range.';
			return;
		}
		lat = latVal;
		lng = lon;
		void previewFromPoint();
	}

	// ---------------------------------------------------------------- Village

	function onPlaceInput(event) {
		const q = String(event.currentTarget?.value ?? '');
		placeQuery = q;
		placeError = '';
		if (placeDebounce) clearTimeout(placeDebounce);
		if (q.trim().length < 2) {
			placeResults = [];
			placeSearching = false;
			placeAbort?.abort();
			return;
		}
		placeDebounce = setTimeout(() => void runPlaceSearch(q.trim()), 350);
	}

	async function runPlaceSearch(q) {
		placeAbort?.abort();
		placeAbort = new AbortController();
		const { signal } = placeAbort;
		placeSearching = true;
		try {
			const rows = await searchPlaces(q, 6, { signal });
			if (signal.aborted) return;
			placeResults = rows;
			if (!rows.length) placeError = 'No places found — try a nearby town or village name.';
		} catch (err) {
			if (signal.aborted || err?.name === 'AbortError') return;
			placeResults = [];
			placeError = String(err);
		} finally {
			if (!signal.aborted) placeSearching = false;
		}
	}

	async function resolveVillageAtPoint({ lng: lon, lat: latVal, label } = {}) {
		if (lon == null || latVal == null) return;
		lng = lon;
		lat = latVal;
		placeResults = [];
		const signal = startPreview();
		try {
			const result = await watershedsFromPoint({ lng: lon, lat: latVal, signal });
			if (signal.aborted) return;
			setPreview({ ...result, source: 'village' }, 'all');
			const villageLabel = result.village_name || label;
			if (!name.trim() && villageLabel) name = titleCase(villageLabel);
			if (preview?.geometry) void loadContext(preview.geometry);
		} catch (err) {
			if (signal.aborted || err?.name === 'AbortError') return;
			preview = { error: String(err) };
			placeError = String(err);
		} finally {
			if (!signal.aborted) previewLoading = false;
		}
	}

	// ---------------------------------------------------------------- Upload

	async function onAoiFileChange(event) {
		uploadError = '';
		uploadName = '';
		const file = event.currentTarget?.files?.[0];
		event.currentTarget.value = '';
		if (!file) return;
		const signal = startPreview();
		try {
			const { geometry, name: aoiName } = await parseAoiFile(file);
			if (signal.aborted) return;
			uploadName = aoiName;
			const result = await watershedsFromGeometry(geometry, aoiName, { signal });
			if (signal.aborted) return;
			preview = { ...result, source: 'custom' };
			if (!name.trim() && aoiName) name = aoiName;
		} catch (err) {
			if (signal.aborted || err?.name === 'AbortError') return;
			uploadError = String(err);
			preview = { error: String(err) };
		} finally {
			if (!signal.aborted) previewLoading = false;
		}
	}

	// ---------------------------------------------------------------- create / open / delete

	const previewOk = $derived(Boolean(preview && !preview.error && preview.geometry));

	async function handleCreate() {
		if (!name.trim() || !previewOk || creating) return;
		creating = true;
		error = '';
		abortAll();
		try {
			/** @type {any} */
			const payload =
				selectMode === 'diagnosis'
					? { name: name.trim(), source: 'diagnosis', source_diagnosis_id: pdChoice }
					: {
							name: name.trim(),
							source: selectMode,
							geometry: preview.geometry,
							aoi_name: preview.watershed_name || preview.village_name || uploadName || undefined,
							lng: preview.seed_lng ?? lng,
							lat: preview.seed_lat ?? lat,
							...(preview.create_token ? { create_token: preview.create_token } : {})
						};
			const project = await createDesignProject(payload);
			goto(itemPath('/design', project, [...projects, project]));
		} catch (err) {
			error = String(err);
			creating = false;
		}
	}

	function openProject(project) {
		goto(itemPath('/design', project, projects));
	}

	async function handleDelete(e, project) {
		e.stopPropagation();
		openMenuId = null;
		if (!confirm(`Delete design project "${project.name}"? This cannot be undone.`)) return;
		deletingId = project.id;
		try {
			await deleteDesignProject(project.id);
			projects = projects.filter((p) => p.id !== project.id);
		} catch (err) {
			error = String(err);
		} finally {
			deletingId = null;
		}
	}

	function handlePointer(event) {
		const el = event.currentTarget;
		const rect = el.getBoundingClientRect();
		el.style.setProperty('--mx', `${event.clientX - rect.left}px`);
		el.style.setProperty('--my', `${event.clientY - rect.top}px`);
	}

	function formatDate(iso) {
		return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
	}

	const SOURCE_LABEL = {
		diagnosis: 'From PD project',
		point: 'Micro watershed',
		village: 'Village',
		custom: 'Custom AOI'
	};

	const mapHint = $derived(
		selectMode === 'diagnosis'
			? 'Pick one of your Problem Diagnosis projects — its AOI is copied into this design project.'
			: selectMode === 'point'
				? 'Click the map or enter coordinates to select the micro watershed (L12) at that point.'
				: selectMode === 'village'
					? 'Search a place or click the map — the village’s intersecting micro watersheds become the AOI.'
					: 'Upload a polygon AOI (GeoJSON, KML, or GPX). That shape becomes the AOI.'
	);
</script>

<svelte:head>
	<title>Design · Water Security Toolbox</title>
</svelte:head>

<div class="flex h-full min-h-screen flex-col bg-[#f6f8f7] font-body">
	<ModuleHeader title="Design" titleHref="/design" subtitle="Find where each solution fits — select an area to begin." />

	<main class="relative z-10 flex-1 overflow-auto p-4 sm:p-6">
		{#if loading}
			<p class="text-brand-steel">Loading projects…</p>
		{:else if showCreate}
			<div class="mx-auto flex min-h-[calc(100vh-7.5rem)] w-full max-w-[1600px] flex-col overflow-hidden rounded-xl bg-white shadow-sm md:flex-row">
				<aside class="flex w-full flex-col gap-4 overflow-y-auto border-brand-navy/10 p-5 md:w-[26rem] md:shrink-0 md:border-r">
					<h2 class="m-0 font-headline text-lg font-semibold text-brand-navy">New design project</h2>

					<div>
						<label class="mb-1 block text-sm font-medium text-brand-navy" for="design-name">Project name</label>
						<input
							id="design-name"
							type="text"
							class="w-full rounded border border-brand-navy/20 px-3 py-2"
							bind:value={name}
							placeholder="e.g. Thupran solution plan"
						/>
					</div>

					<div class="flex flex-wrap gap-2" role="tablist" aria-label="Area selection mode">
						{#each MODES as mode (mode.id)}
							<button
								type="button"
								role="tab"
								aria-selected={selectMode === mode.id}
								class="mode-tab"
								class:active={selectMode === mode.id}
								onclick={() => setMode(mode.id)}
							>
								{mode.label}
							</button>
						{/each}
					</div>

					{#if selectMode === 'diagnosis'}
						<div class="grid gap-2">
							<SearchableSelect
								id="pd-project"
								label="Problem Diagnosis project"
								placeholder={pdLoading ? 'Loading projects…' : 'Choose a project…'}
								filterPlaceholder="Filter projects…"
								options={pdOptions}
								value={pdChoice}
								loading={pdLoading}
								disabled={pdLoading || !pdOptions.length}
								emptyText="No matching projects"
								onChange={onPdChoice}
							/>
							{#if pdError}
								<p class="m-0 text-xs text-brand-steel">{pdError}</p>
							{/if}
						</div>
					{:else if selectMode === 'point'}
						<div class="grid gap-2">
							<label class="block text-sm font-medium text-brand-navy" for="coord-input">Coordinates (lat, lng)</label>
							<input
								id="coord-input"
								type="text"
								inputmode="decimal"
								autocomplete="off"
								class="w-full rounded border border-brand-navy/20 px-3 py-2"
								bind:value={coordInput}
								onkeydown={(e) => e.key === 'Enter' && (e.preventDefault(), applyCoordinates())}
								placeholder="e.g. 18.0432, 78.2615"
							/>
							<button
								type="button"
								class="btn-primary"
								disabled={previewLoading}
								onclick={applyCoordinates}
							>
								{previewLoading ? 'Finding…' : 'Find watershed'}
							</button>
							{#if coordError}
								<p class="m-0 text-xs text-red-600">{coordError}</p>
							{/if}
						</div>
					{:else if selectMode === 'village'}
						<div class="grid gap-2">
							<label class="block text-sm font-medium text-brand-navy" for="place-search">Search place</label>
							<input
								id="place-search"
								type="search"
								autocomplete="off"
								class="w-full rounded border border-brand-navy/20 px-3 py-2"
								placeholder="e.g. Thupran, Medak"
								value={placeQuery}
								oninput={onPlaceInput}
							/>
							{#if placeSearching}
								<p class="m-0 text-xs text-brand-steel">Searching…</p>
							{/if}
							{#if placeResults.length}
								<ul class="m-0 max-h-48 list-none overflow-y-auto rounded border border-brand-navy/15 p-0" role="listbox">
									{#each placeResults as place (place.label + place.lat + place.lng)}
										<li class="m-0 border-b border-brand-navy/10 last:border-b-0">
											<button
												type="button"
												class="w-full cursor-pointer px-3 py-2 text-left text-sm text-brand-navy hover:bg-brand-sky/30"
												onclick={() => {
													placeQuery = place.label;
													void resolveVillageAtPoint(place);
												}}
											>
												<span class="block font-medium leading-snug">{place.label}</span>
												{#if place.type}<span class="block text-[11px] text-brand-steel">{place.type}</span>{/if}
											</button>
										</li>
									{/each}
								</ul>
							{/if}
							{#if placeError}
								<p class="m-0 text-xs text-red-600">{placeError}</p>
							{/if}
						</div>
					{:else}
						<div>
							<label class="mb-1 block text-sm font-medium text-brand-navy" for="aoi-file">AOI file</label>
							<input
								id="aoi-file"
								type="file"
								accept=".geojson,.json,.kml,.gpx,application/geo+json,application/json,application/vnd.google-earth.kml+xml"
								class="block w-full text-sm"
								onchange={onAoiFileChange}
							/>
							{#if uploadName}<p class="m-0 mt-1 text-xs text-brand-navy">Loaded: {uploadName}</p>{/if}
							{#if uploadError}<p class="m-0 mt-1 text-xs text-red-600">{uploadError}</p>{/if}
						</div>
					{/if}

					<div class="rounded-lg p-3 text-sm" style:background-color="color-mix(in srgb, {ACCENT} 8%, white)">
						{#if previewLoading}
							<p class="m-0 text-brand-steel">Resolving area…</p>
						{:else if preview?.error}
							<p class="m-0 text-red-600">{preview.error}</p>
						{:else if preview}
							<p class="m-0 text-[11px] font-semibold uppercase tracking-wide text-brand-navy/55">Area of interest</p>
							<p class="m-0 mt-0.5 font-medium text-brand-navy">
								{preview.watershed_name || preview.name || 'Selected area'}
							</p>
							{#if preview.village_name}
								<p class="m-0 mt-1 text-brand-steel">Village: {preview.village_name}</p>
							{/if}
							{#if multiMicroParts.length}
								<fieldset class="m-0 mt-3 space-y-2 border-0 border-t border-brand-navy/10 p-0 pt-3">
									<legend class="text-xs font-medium uppercase tracking-wide text-brand-navy">
										{multiMicroParts.length} micro watersheds
									</legend>
									<label class="flex cursor-pointer items-start gap-2 text-brand-navy">
										<input type="radio" name="micro" class="mt-1" checked={microChoice === 'all'} onchange={() => onMicroChoiceChange('all')} />
										<span class="font-medium">All intersecting micros</span>
									</label>
									{#each multiMicroParts as part (part.watershed_id)}
										<label class="flex cursor-pointer items-start gap-2 text-brand-navy">
											<input
												type="radio"
												name="micro"
												class="mt-1"
												checked={String(microChoice) === String(part.watershed_id)}
												onchange={() => onMicroChoiceChange(String(part.watershed_id))}
											/>
											<span>{part.watershed_name || part.watershed_id}</span>
										</label>
									{/each}
								</fieldset>
							{/if}
							{#if contextLoading}
								<p class="m-0 mt-1 text-brand-steel">Loading rivers / basin context…</p>
							{/if}
						{:else}
							<p class="m-0 text-brand-steel">{mapHint}</p>
						{/if}
					</div>

					{#if error}<p class="m-0 text-sm text-red-600">{error}</p>{/if}

					<div class="mt-auto flex flex-wrap gap-2 pt-2">
						<button type="button" class="btn-primary" disabled={creating || !name.trim() || !previewOk} onclick={handleCreate}>
							{creating ? 'Creating…' : 'Create & find solutions'}
						</button>
						<button
							type="button"
							class="cursor-pointer rounded bg-brand-steel px-4 py-2 text-white hover:bg-brand-navy"
							onclick={() => {
								abortAll();
								showCreate = false;
							}}
						>
							Cancel
						</button>
					</div>
				</aside>

				<section class="create-map flex min-h-[24rem] w-full flex-1 flex-col p-4">
					<LocationPicker
						bind:lng
						bind:lat
						onPick={selectMode === 'point' ? previewFromPoint : selectMode === 'village' ? resolveVillageAtPoint : undefined}
						clipGeometry={preview?.geometry ?? null}
						villageGeometry={preview?.village_geometry ?? null}
						villageName={preview?.village_name ?? null}
						parts={preview?.parts ?? null}
						selectedPartId={multiMicroParts.length ? microChoice : null}
						contextLayers={contextLayers}
						interactiveClick={selectMode === 'point' || selectMode === 'village'}
						showMarker={selectMode === 'point' || selectMode === 'village'}
						hint={mapHint}
					/>
				</section>
			</div>
		{:else}
			{#if error}<p class="mb-4 text-sm text-red-600">{error}</p>{/if}

			<div class="grid gap-6" style="grid-template-columns: repeat(auto-fill, minmax(min(100%, 20rem), 1fr));">
				<button
					type="button"
					class="card card-new"
					class:in={mounted}
					style="--accent: {ACCENT}; --delay: 0ms;"
					onpointermove={handlePointer}
					onclick={openCreate}
				>
					<span class="card-spotlight" aria-hidden="true"></span>
					<div class="relative z-10 flex w-full flex-col items-start gap-4">
						<div class="icon-wrap icon-wrap-dashed">
							<span class="text-2xl leading-none text-[color:var(--accent)]">+</span>
						</div>
						<h3 class="card-title m-0 font-display text-xl">New design project</h3>
						<p class="card-desc m-0 text-[13.5px] leading-relaxed">
							Import an AOI from a PD project or pick a new one, then see which solutions fit where.
						</p>
						<span class="cta mt-1 font-mono text-[12px]">Create →</span>
					</div>
				</button>

				{#each projects as project, i (project.id)}
					<div
						class="card"
						class:in={mounted}
						style="--accent: {ACCENT}; --delay: {(i + 1) * 70}ms;"
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
						<div class="relative z-10 flex w-full flex-col items-start gap-4">
							<div class="flex w-full items-start justify-between gap-2">
								<div class="icon-wrap icon-wrap-thumb">
									<WatershedThumb geometry={project.aoi_geometry} circular />
								</div>
								<div class="relative shrink-0" role="presentation" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
									<button
										type="button"
										class="menu-btn"
										aria-label="Project actions"
										disabled={deletingId === project.id}
										onclick={(e) => {
											e.stopPropagation();
											openMenuId = openMenuId === project.id ? null : project.id;
										}}
									>
										<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="h-5 w-5">
											<circle cx="12" cy="5" r="1.5" /><circle cx="12" cy="12" r="1.5" /><circle cx="12" cy="19" r="1.5" />
										</svg>
									</button>
									{#if openMenuId === project.id}
										<div class="menu-panel">
											<button type="button" class="menu-item menu-item-danger" onclick={(e) => handleDelete(e, project)}>
												{deletingId === project.id ? 'Deleting…' : 'Delete'}
											</button>
										</div>
									{/if}
								</div>
							</div>
							<h3 class="card-title m-0 min-w-0 break-words font-display text-xl">{project.name}</h3>
							<p class="card-desc m-0 text-[13px]">
								{project.aoi_source === 'diagnosis' && project.source_diagnosis_name
									? `From PD: ${project.source_diagnosis_name}`
									: SOURCE_LABEL[project.aoi_source] || 'AOI'}
								{#if project.area_ha}· {Math.round(project.area_ha).toLocaleString()} ha{/if}
							</p>
							<div class="card-meta flex w-full items-center justify-between gap-3">
								<span class="font-mono text-[11px] tracking-wide">{formatDate(project.updated_at ?? project.created_at)}</span>
								<span class="cta font-mono text-[12px]">Open →</span>
							</div>
						</div>
					</div>
				{/each}
			</div>

			{#if projects.length === 0}
				<p class="mt-4 text-sm text-[#56646f]">No design projects yet. Create one to get started.</p>
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
		background: rgba(255, 255, 255, 0.9);
		padding: 1.6rem;
		text-align: left;
		cursor: pointer;
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
		box-shadow: 0 24px 44px -22px color-mix(in srgb, var(--accent) 50%, transparent);
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
	.cta {
		color: color-mix(in srgb, var(--accent) 80%, black);
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
	}
	.menu-item-danger {
		color: #dc2626;
	}
	.menu-item-danger:hover {
		background: #fef2f2;
	}
	.mode-tab {
		cursor: pointer;
		border-radius: 999px;
		border: 1px solid rgba(0, 48, 109, 0.2);
		background: white;
		padding: 0.4rem 0.9rem;
		font-family: inherit;
		font-size: 0.8125rem;
		color: #56646f;
	}
	.mode-tab.active {
		border-color: #0d983b;
		background: color-mix(in srgb, #0d983b 12%, white);
		color: #00306d;
		font-weight: 600;
	}
	.btn-primary {
		cursor: pointer;
		border: 0;
		border-radius: 0.375rem;
		background: #0d983b;
		padding: 0.5rem 1rem;
		font-family: inherit;
		font-size: 0.875rem;
		color: white;
	}
	.btn-primary:hover:not(:disabled) {
		background: #0b7d31;
	}
	.btn-primary:disabled {
		cursor: not-allowed;
		opacity: 0.6;
	}
	.create-map :global(.maplibregl-map) {
		min-height: 100%;
	}
	@media (prefers-reduced-motion: reduce) {
		.card {
			transition: none;
			opacity: 1;
			transform: none;
		}
	}
</style>
