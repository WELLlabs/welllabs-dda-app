<script>
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';
	import LocationPicker from '$lib/shared/components/LocationPicker.svelte';
	import SearchableSelect from '$lib/shared/components/SearchableSelect.svelte';
	import WatershedThumb from '$lib/shared/components/WatershedThumb.svelte';
	import { itemPath } from '$lib/shared/slug.js';
	import { session } from '$lib/shared/session.svelte.js';
	import FieldNoteIcon from '$lib/modules/diagnose/components/icons/FieldNoteIcon.svelte';
	import ObservationZoneIcon from '$lib/modules/diagnose/components/icons/ObservationZoneIcon.svelte';
	import { parseAoiFile } from '$lib/modules/diagnose/aoi-parse.js';
	import {
		createProject,
		deleteProject,
		fetchProjects,
		fetchVillageDistricts,
		fetchVillageStates,
		fetchVillagesByDistrict,
		fetchWatershedPreviewContext,
		lookupWatershed,
		watershedsFromGeometry,
		watershedsFromVillage
	} from '$lib/modules/diagnose/api';

	let projects = $state([]);
	let loading = $state(true);
	let error = $state('');
	let showCreate = $state(false);
	let openMenuId = $state(null);
	let name = $state('');
	let lng = $state(77.2);
	let lat = $state(28.6);
	/** @type {'point' | 'village' | 'custom'} */
	let selectMode = $state('point');
	let watershedPreview = $state(null);
	let previewLoading = $state(false);
	/** @type {'all' | string} — 'all' intersecting micros, or one L12 watershed_id */
	let microChoice = $state('all');
	/** @type {Array<object>} */
	let previewContextLayers = $state([]);
	let contextLoading = $state(false);
	let creating = $state(false);
	let deletingId = $state(null);
	let mounted = $state(false);
	/** @type {AbortController | null} */
	let villageAbort = null;
	/** @type {AbortController | null} */
	let previewAbort = null;
	let previewGen = 0;

	let villageState = $state('');
	let villageDistrict = $state('');
	let villageId = $state('');
	/** @type {string[]} */
	let stateOptions = $state([]);
	/** @type {string[]} */
	let districtOptions = $state([]);
	/** @type {Array<{ id: string, name: string }>} */
	let villageOptions = $state([]);
	/** @type {Map<string, string[]>} */
	const districtCache = new Map();
	/** @type {Map<string, Array<{ id: string, name: string }>>} */
	const villageCache = new Map();
	let cascadeLoading = $state('');
	let cascadeError = $state('');
	let uploadError = $state('');
	let uploadName = $state('');
	let coordError = $state('');
	let coordInput = $state('');

	const stateSelectOptions = $derived(
		stateOptions.map((s) => ({ value: s, label: titleCase(s) }))
	);
	const districtSelectOptions = $derived(
		districtOptions.map((d) => ({ value: d, label: titleCase(d) }))
	);
	const villageSelectOptions = $derived(
		villageOptions.map((v) => ({ value: String(v.id), label: titleCase(v.name) }))
	);

	function titleCase(s) {
		return String(s || '')
			.split(/\s+/)
			.map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
			.join(' ');
	}

	onMount(() => {
		loadProjects();
		void ensureStatesLoaded();
		mounted = true;
		document.addEventListener('click', closeMenu);
		return () => {
			document.removeEventListener('click', closeMenu);
		};
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

	function setMode(mode) {
		selectMode = mode;
		watershedPreview = null;
		microChoice = 'all';
		previewContextLayers = [];
		previewLoading = false;
		contextLoading = false;
		cascadeError = '';
		uploadError = '';
		uploadName = '';
		coordError = '';
		if (mode === 'point') {
			coordInput = formatCoordInput(lat, lng);
		}
		if (mode === 'village') {
			ensureStatesLoaded();
		} else {
			resetVillageCascade();
		}
	}

	const multiMicroParts = $derived(
		Array.isArray(watershedPreview?.parts) && watershedPreview.parts.length > 1
			? watershedPreview.parts
			: []
	);

	/**
	 * Apply one-micro vs all-intersecting clip onto the preview payload.
	 * @param {any} base
	 * @param {'all' | string} choice
	 */
	function withMicroChoice(base, choice) {
		if (!base || base.error) return base;
		const parts = Array.isArray(base.parts) ? base.parts : [];
		if (parts.length <= 1) return base;

		if (choice === 'all' && base.all_geometry) {
			return {
				...base,
				geometry: base.all_geometry,
				watershed_id: base.all_watershed_id ?? base.watershed_id,
				watershed_name: base.all_watershed_name ?? base.watershed_name,
				bounds: base.all_bounds ?? base.bounds
			};
		}

		const part = parts.find((p) => String(p.watershed_id) === String(choice));
		if (!part?.geometry) return base;
		return {
			...base,
			geometry: part.geometry,
			watershed_id: part.watershed_id,
			watershed_name: part.watershed_name,
			bounds: part.bounds ?? base.bounds
		};
	}

	/**
	 * @param {any} result
	 * @param {'all' | 'point'} defaultMode — village defaults to all; point defaults to clicked L12
	 */
	function setWatershedPreview(result, defaultMode = 'all') {
		const parts = Array.isArray(result?.parts) ? result.parts : [];
		let choice = 'all';
		if (parts.length > 1) {
			if (defaultMode === 'point' && result.watershed_id) {
				choice = String(result.watershed_id);
			} else {
				choice = 'all';
			}
		} else if (parts.length === 1) {
			choice = String(parts[0].watershed_id ?? 'all');
		}
		microChoice = choice;
		const enriched =
			parts.length > 1 && !result.all_geometry && result.geometry
				? {
						...result,
						all_geometry: result.geometry,
						all_watershed_id: result.watershed_id,
						all_watershed_name: result.watershed_name,
						all_bounds: result.bounds
					}
				: result;
		watershedPreview = withMicroChoice(enriched, choice);
	}

	function onMicroChoiceChange(choice) {
		microChoice = choice;
		if (!watershedPreview || watershedPreview.error) return;
		watershedPreview = withMicroChoice(watershedPreview, choice);
		if (watershedPreview.geometry) void loadPreviewContext(watershedPreview.geometry);
	}

	function abortInFlightLoads() {
		villageAbort?.abort();
		previewAbort?.abort();
		villageAbort = null;
		previewAbort = null;
		previewGen += 1;
		contextLoading = false;
	}

	async function loadPreviewContext(geometry) {
		if (!geometry) {
			previewContextLayers = [];
			return;
		}
		previewAbort?.abort();
		previewAbort = new AbortController();
		const { signal } = previewAbort;
		const gen = ++previewGen;
		contextLoading = true;
		try {
			// Basin / sub-basin / L7 first (fast), then rivers (often the slow GPKG).
			const fast = await fetchWatershedPreviewContext(geometry, {
				signal,
				includeRivers: false
			});
			if (gen !== previewGen || signal.aborted) return;
			previewContextLayers = fast.layers ?? [];
			const full = await fetchWatershedPreviewContext(geometry, {
				signal,
				includeRivers: true
			});
			if (gen !== previewGen || signal.aborted) return;
			previewContextLayers = full.layers ?? previewContextLayers;
		} catch (err) {
			if (signal.aborted || (err instanceof Error && err.name === 'AbortError')) return;
			console.error('Preview context failed', err);
		} finally {
			if (gen === previewGen) contextLoading = false;
		}
	}

	function resetVillageCascade() {
		abortInFlightLoads();
		villageState = '';
		villageDistrict = '';
		villageId = '';
		districtOptions = [];
		villageOptions = [];
		cascadeError = '';
	}

	async function ensureStatesLoaded() {
		if (stateOptions.length) return;
		cascadeLoading = 'states';
		cascadeError = '';
		try {
			stateOptions = await fetchVillageStates();
		} catch (err) {
			cascadeError = String(err);
		} finally {
			cascadeLoading = '';
		}
	}

	async function onStateChange(state) {
		abortInFlightLoads();
		villageState = state;
		villageDistrict = '';
		villageId = '';
		districtOptions = [];
		villageOptions = [];
		watershedPreview = null;
		previewContextLayers = [];
		if (!state) return;
		cascadeError = '';
		const cached = districtCache.get(state);
		if (cached) {
			districtOptions = cached;
			return;
		}
		cascadeLoading = 'districts';
		try {
			const rows = await fetchVillageDistricts(state);
			districtCache.set(state, rows);
			if (villageState === state) districtOptions = rows;
		} catch (err) {
			cascadeError = String(err);
		} finally {
			cascadeLoading = '';
		}
	}

	async function onDistrictChange(district) {
		abortInFlightLoads();
		villageDistrict = district;
		villageId = '';
		villageOptions = [];
		watershedPreview = null;
		previewContextLayers = [];
		if (!district || !villageState) return;
		cascadeError = '';
		const cacheKey = `${villageState}::${district}`;
		const cached = villageCache.get(cacheKey);
		if (cached) {
			villageOptions = cached;
			return;
		}
		cascadeLoading = 'villages';
		try {
			const rows = await fetchVillagesByDistrict(villageState, district);
			villageCache.set(cacheKey, rows);
			if (villageState && villageDistrict === district) villageOptions = rows;
		} catch (err) {
			cascadeError = String(err);
		} finally {
			cascadeLoading = '';
		}
	}

	async function onVillageChange(id) {
		villageId = id;
		if (!id) {
			abortInFlightLoads();
			watershedPreview = null;
			microChoice = 'all';
			previewContextLayers = [];
			return;
		}
		const hit = villageOptions.find((v) => v.id === id);
		previewLoading = true;
		microChoice = 'all';
		cascadeError = '';
		villageAbort?.abort();
		previewAbort?.abort();
		villageAbort = new AbortController();
		const { signal } = villageAbort;
		try {
			const result = await watershedsFromVillage({ villageId: id, signal });
			if (signal.aborted) return;
			setWatershedPreview(result, 'all');
			if (result.seed_lng != null) lng = result.seed_lng;
			if (result.seed_lat != null) lat = result.seed_lat;
			if (!name.trim() && hit?.name) name = titleCase(hit.name);
			const geom = watershedPreview?.geometry;
			if (geom) {
				previewContextLayers = [];
				queueMicrotask(() => {
					void loadPreviewContext(geom);
				});
			}
		} catch (err) {
			if (signal.aborted || (err instanceof Error && err.name === 'AbortError')) return;
			watershedPreview = { error: String(err) };
			previewContextLayers = [];
		} finally {
			if (!signal.aborted) previewLoading = false;
		}
	}

	function formatCoordInput(latVal, lon) {
		return `${Number(latVal).toFixed(5)}, ${Number(lon).toFixed(5)}`;
	}

	/** @param {string} text */
	function parseLatLngPair(text) {
		const raw = String(text).trim();
		if (!raw) return { error: 'Enter latitude and longitude.' };
		const parts = raw.split(/[,;\s]+/).filter(Boolean);
		if (parts.length !== 2) {
			return { error: 'Use latitude, longitude — e.g. 12.9716, 77.5946' };
		}
		const a = Number.parseFloat(parts[0]);
		const b = Number.parseFloat(parts[1]);
		if (!Number.isFinite(a) || !Number.isFinite(b)) {
			return { error: 'Enter valid decimal numbers.' };
		}
		let latVal = a;
		let lon = b;
		// Accept longitude, latitude if the first value cannot be a latitude.
		if (Math.abs(a) > 90 && Math.abs(b) <= 90) {
			lon = a;
			latVal = b;
		}
		if (latVal < -90 || latVal > 90) {
			return { error: 'Latitude must be between −90 and 90.' };
		}
		if (lon < -180 || lon > 180) {
			return { error: 'Longitude must be between −180 and 180.' };
		}
		return { lat: latVal, lng: lon };
	}

	async function previewWatershedFromPoint() {
		coordInput = formatCoordInput(lat, lng);
		previewLoading = true;
		watershedPreview = null;
		microChoice = 'all';
		previewContextLayers = [];
		try {
			const result = await lookupWatershed(lng, lat);
			setWatershedPreview({ ...result, source: 'point' }, 'point');
			if (watershedPreview?.geometry) void loadPreviewContext(watershedPreview.geometry);
		} catch (err) {
			watershedPreview = { error: String(err) };
		} finally {
			previewLoading = false;
		}
	}

	function applyManualCoordinates() {
		coordError = '';
		const parsed = parseLatLngPair(coordInput);
		if (parsed.error) {
			coordError = parsed.error;
			return;
		}
		lat = parsed.lat;
		lng = parsed.lng;
		void previewWatershedFromPoint();
	}

	function onCoordKeydown(event) {
		if (event.key === 'Enter') {
			event.preventDefault();
			applyManualCoordinates();
		}
	}

	async function onAoiFileChange(event) {
		uploadError = '';
		uploadName = '';
		const file = event.currentTarget?.files?.[0];
		event.currentTarget.value = '';
		if (!file) return;
		previewLoading = true;
		watershedPreview = null;
		previewContextLayers = [];
		try {
			const { geometry, name: aoiName } = await parseAoiFile(file);
			uploadName = aoiName;
			const result = await watershedsFromGeometry(geometry, aoiName);
			watershedPreview = result;
			if (result.seed_lng != null) lng = result.seed_lng;
			if (result.seed_lat != null) lat = result.seed_lat;
			if (result.geometry) void loadPreviewContext(result.geometry);
		} catch (err) {
			uploadError = String(err);
			watershedPreview = { error: String(err) };
		} finally {
			previewLoading = false;
		}
	}

	function openProject(project) {
		goto(itemPath('/diagnose', project, projects));
	}

	function previewOk() {
		return Boolean(watershedPreview && !watershedPreview.error && watershedPreview.geometry);
	}

	async function handleCreate() {
		if (!name.trim() || !previewOk()) return;
		creating = true;
		error = '';
		// Free workers that may still be clipping preview layers.
		abortInFlightLoads();
		try {
			const project = await createProject({
				name: name.trim(),
				source: selectMode,
				lng: watershedPreview.seed_lng ?? lng,
				lat: watershedPreview.seed_lat ?? lat,
				geometry: watershedPreview.geometry,
				watershed_id: watershedPreview.watershed_id,
				watershed_name: watershedPreview.watershed_name
			});
			showCreate = false;
			name = '';
			watershedPreview = null;
			selectMode = 'point';
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
		microChoice = 'all';
		previewContextLayers = [];
		selectMode = 'point';
		coordError = '';
		coordInput = formatCoordInput(lat, lng);
		resetVillageCascade();
		uploadError = '';
		uploadName = '';
	}

	const mapHint = $derived(
		selectMode === 'point'
			? 'Click the map or enter coordinates (latitude, longitude). If the point sits in a village with several micro watersheds, choose one or all.'
			: selectMode === 'village'
				? 'Choose state → district → village. Use the options on the left to clip to one micro or all intersecting. Blue dashed outline is the selected L12 clip.'
				: 'Upload a polygon AOI (GeoJSON, KML, or GPX polygon). That shape becomes the clip boundary.'
	);

	/** Human-readable hierarchy level for the active clip. */
	const clipLevelLabel = $derived.by(() => {
		const preview = watershedPreview;
		if (!preview || preview.error) return null;
		if (preview.source === 'custom' || preview.watershed_id === 'custom') {
			return 'Custom AOI';
		}
		const n = Array.isArray(preview.parts) ? preview.parts.length : 0;
		if (microChoice === 'all' && n > 1) {
			return `Micro watersheds (L12) · ${n} units`;
		}
		return 'Micro watershed (L12)';
	});

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
			<div class="create-shell mx-auto flex min-h-[calc(100vh-7.5rem)] w-full max-w-[1600px] flex-col overflow-hidden rounded-xl bg-white shadow-sm md:flex-row">
				<aside class="create-side flex w-full flex-col gap-4 overflow-y-auto border-brand-navy/10 p-5 md:w-1/4 md:border-r">
					<h2 class="m-0 font-headline text-lg font-semibold text-brand-navy">New project</h2>

					<label class="block font-body text-sm font-medium text-brand-navy" for="proj-name"
						>Project name</label
					>
					<input
						id="proj-name"
						type="text"
						class="w-full rounded border border-brand-navy/20 px-3 py-2 font-body"
						bind:value={name}
						placeholder="e.g. North basin survey"
					/>

					<div class="flex flex-wrap gap-2" role="tablist" aria-label="Watershed selection mode">
						{#each [
							{ id: 'point', label: 'Map click' },
							{ id: 'village', label: 'Village' },
							{ id: 'custom', label: 'Upload AOI' }
						] as mode}
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

					{#if selectMode === 'point'}
						<div class="grid gap-2">
							<div>
								<label class="mb-1 block font-body text-sm font-medium text-brand-navy" for="coord-input"
									>Coordinates (lat, lng)</label
								>
								<input
									id="coord-input"
									type="text"
									inputmode="decimal"
									autocomplete="off"
									class="w-full rounded border border-brand-navy/20 px-3 py-2 font-body"
									bind:value={coordInput}
									onkeydown={onCoordKeydown}
									placeholder="e.g. 12.9716, 77.5946"
								/>
							</div>
							<button
								type="button"
								class="cursor-pointer rounded bg-brand-blue px-4 py-2 font-body text-sm text-white disabled:opacity-60"
								disabled={previewLoading}
								onclick={applyManualCoordinates}
							>
								{previewLoading ? 'Finding…' : 'Find watershed'}
							</button>
						</div>
						{#if coordError}
							<p class="m-0 text-xs text-red-600">{coordError}</p>
						{/if}
					{:else if selectMode === 'village'}
						<div class="grid gap-3">
							<SearchableSelect
								id="village-state"
								label="State"
								placeholder="Select state…"
								options={stateSelectOptions}
								bind:value={villageState}
								loading={cascadeLoading === 'states'}
								disabled={cascadeLoading === 'states'}
								onChange={onStateChange}
							/>
							<SearchableSelect
								id="village-district"
								label="District"
								placeholder="Select district…"
								options={districtSelectOptions}
								bind:value={villageDistrict}
								loading={cascadeLoading === 'districts'}
								disabled={!villageState || cascadeLoading === 'districts'}
								onChange={onDistrictChange}
							/>
							<SearchableSelect
								id="village-name"
								label="Village"
								placeholder="Select village…"
								options={villageSelectOptions}
								bind:value={villageId}
								loading={cascadeLoading === 'villages'}
								disabled={!villageDistrict || cascadeLoading === 'villages'}
								emptyText="No villages in this district"
								onChange={onVillageChange}
							/>
						</div>
						{#if cascadeError}
							<p class="m-0 text-xs text-red-600">{cascadeError}</p>
						{/if}
					{:else if selectMode === 'custom'}
						<div>
							<label class="mb-1 block font-body text-sm font-medium text-brand-navy" for="aoi-file"
								>AOI file</label
							>
							<input
								id="aoi-file"
								type="file"
								accept=".geojson,.json,.kml,.gpx,application/geo+json,application/json,application/vnd.google-earth.kml+xml"
								class="block w-full font-body text-sm"
								onchange={onAoiFileChange}
							/>
							<p class="m-0 mt-1 text-xs text-brand-steel">
								GeoJSON, KML, or GPX polygon. The uploaded shape is used as the clip boundary.
							</p>
							{#if uploadName}
								<p class="m-0 mt-1 text-xs text-brand-navy">Loaded: {uploadName}</p>
							{/if}
							{#if uploadError}
								<p class="m-0 mt-1 text-xs text-red-600">{uploadError}</p>
							{/if}
						</div>
					{/if}

					<div class="rounded-lg bg-brand-sky/20 p-3 font-body text-sm">
						{#if previewLoading}
							<p class="m-0 text-brand-steel">Resolving clip area…</p>
						{:else if watershedPreview?.error}
							<p class="m-0 text-red-600">{watershedPreview.error}</p>
						{:else if watershedPreview}
							<p class="m-0 text-[11px] font-semibold uppercase tracking-wide text-brand-navy/55">
								Clip level
							</p>
							<p class="m-0 mt-0.5 font-medium text-brand-navy">{clipLevelLabel}</p>
							<p class="m-0 mt-2 text-[11px] font-semibold uppercase tracking-wide text-brand-navy/55">
								Watershed ID
							</p>
							<p class="m-0 mt-0.5 break-all font-mono text-sm text-brand-navy">
								{watershedPreview.watershed_id}
							</p>
							{#if watershedPreview.watershed_name && String(watershedPreview.watershed_name) !== String(watershedPreview.watershed_id)}
								<p class="m-0 mt-2 text-[11px] font-semibold uppercase tracking-wide text-brand-navy/55">
									Name
								</p>
								<p class="m-0 mt-0.5 text-sm text-brand-steel">{watershedPreview.watershed_name}</p>
							{/if}
							{#if watershedPreview.village_name}
								<p class="m-0 mt-2 text-brand-steel">
									Village: {watershedPreview.village_name}
									{#if watershedPreview.village_geometry}
										<span class="text-brand-navy"> — grey dotted outline on the map</span>
									{/if}
								</p>
							{/if}
							{#if multiMicroParts.length}
								<div class="mt-3 space-y-2 border-t border-brand-navy/10 pt-3">
									<p class="m-0 text-xs font-medium uppercase tracking-wide text-brand-navy">
										Clip area ({multiMicroParts.length} micro watersheds)
									</p>
									<label class="flex cursor-pointer items-start gap-2 text-sm text-brand-navy">
										<input
											type="radio"
											name="micro-choice"
											class="mt-1"
											checked={microChoice === 'all'}
											onchange={() => onMicroChoiceChange('all')}
										/>
										<span>
											<span class="font-medium">All intersecting micros</span>
											<span class="block text-xs text-brand-steel">
												Union of every L12 that intersects the village (map clip).
											</span>
										</span>
									</label>
									{#each multiMicroParts as part (part.watershed_id)}
										<label class="flex cursor-pointer items-start gap-2 text-sm text-brand-navy">
											<input
												type="radio"
												name="micro-choice"
												class="mt-1"
												checked={String(microChoice) === String(part.watershed_id)}
												onchange={() => onMicroChoiceChange(String(part.watershed_id))}
											/>
											<span>
												<span class="font-medium">{part.watershed_name || 'Micro watershed'}</span>
												<span class="block font-mono text-[11px] text-brand-steel">
													{part.watershed_id}
												</span>
											</span>
										</label>
									{/each}
								</div>
							{:else if watershedPreview.parts?.length === 1}
								<p class="m-0 mt-1 text-brand-steel">
									1 micro watershed (L12)
									{#if watershedPreview.village_geometry}
										— grey dotted outline is the village boundary.
									{/if}
								</p>
							{/if}
							{#if contextLoading}
								<p class="m-0 mt-1 text-brand-steel">Loading rivers / basin context…</p>
							{/if}
						{:else}
							<p class="m-0 text-brand-steel">{mapHint}</p>
						{/if}
					</div>

					{#if error}
						<p class="m-0 text-sm text-red-600">{error}</p>
					{/if}

					<div class="mt-auto flex flex-wrap gap-2 pt-2">
						<button
							class="cursor-pointer rounded bg-brand-blue px-4 py-2 font-body text-white disabled:opacity-60"
							disabled={creating || !name.trim() || !previewOk()}
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
				</aside>

				<section class="create-map flex min-h-[24rem] w-full flex-1 flex-col p-4 md:w-3/4 md:flex-none md:self-stretch">
					<LocationPicker
						bind:lng
						bind:lat
						onPick={selectMode === 'point' ? previewWatershedFromPoint : undefined}
						clipGeometry={watershedPreview?.geometry ?? null}
						villageGeometry={watershedPreview?.village_geometry ?? null}
						villageName={watershedPreview?.village_name ?? null}
						parts={watershedPreview?.parts ?? null}
						selectedPartId={multiMicroParts.length ? microChoice : null}
						contextLayers={previewContextLayers}
						interactiveClick={selectMode === 'point'}
						showMarker={selectMode === 'point'}
						hint={mapHint}
					/>
				</section>
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
					style="--accent: #1b75e0; --delay: 0ms;"
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
						style="--accent: #1b75e0; --delay: {(i + 1) * 70}ms;"
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
		border-color: #1b75e0;
		background: color-mix(in srgb, #1b75e0 12%, white);
		color: #00306d;
		font-weight: 600;
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
