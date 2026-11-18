<script>
	import { onDestroy, onMount } from 'svelte';
	import maplibregl from 'maplibre-gl';
	import 'maplibre-gl/dist/maplibre-gl.css';
	import { fetchProjectSolutions, fetchSolutionGeojson, inspectPoint } from '$lib/modules/design/api.js';
	import WatershedStats from './WatershedStats.svelte';

	/** @type {{ project: { id: string, name: string, bounds?: number[] | null, aoi_geometry?: object | null } }} */
	let { project } = $props();

	const TYPE_COLOR = { Areal: '#0d983b', Point: '#c2410c', Instream: '#1b75e0' };
	const TYPE_FILTERS = ['All', 'Areal', 'Point', 'Instream'];
	const EMPTY_FC = { type: 'FeatureCollection', features: [] };

	let solutions = $state([]);
	let warnings = $state([]);
	let summary = $state(/** @type {{ aoi_area_ha?: number, stream_km?: number } | null} */ (null));
	let loading = $state(true);
	let loadError = $state('');
	let selectedId = $state(/** @type {string | null} */ (null));
	let layerLoading = $state(false);
	let layerError = $state('');
	let expandedId = $state(/** @type {string | null} */ (null));
	let typeFilter = $state('All');
	let basemap = $state(/** @type {'satellite' | 'streets'} */ ('satellite'));

	/** @type {Map<string, any>} */
	const layerCache = new Map();
	/** @type {HTMLDivElement} */
	let container;
	/** @type {maplibregl.Map | null} */
	let map = null;
	let mapReady = $state(false);
	/** @type {AbortController | null} */
	let layerAbort = null;
	/** @type {AbortController | null} */
	let listAbort = null;

	// Which solutions this project views: all of them, or a custom list the user picks.
	// null until chosen (first visit) — the panel asks before drawing anything.
	let viewMode = $state(/** @type {'all' | 'custom' | null} */ (null));
	let customIds = $state(/** @type {string[]} */ ([]));
	let picking = $state(false);
	let draftIds = $state(/** @type {string[]} */ ([]));
	let pickQuery = $state('');
	let statsOpen = $state(true);

	const viewKey = () => `design:view:${project.id}`;
	const STATS_KEY = 'design:stats-open';

	function readPrefs() {
		try {
			const raw = localStorage.getItem(viewKey());
			if (raw) {
				const v = JSON.parse(raw);
				if (v?.mode === 'all') viewMode = 'all';
				else if (v?.mode === 'custom' && Array.isArray(v.ids) && v.ids.length) {
					viewMode = 'custom';
					customIds = v.ids.filter((id) => typeof id === 'string');
				}
			}
			const open = localStorage.getItem(STATS_KEY);
			if (open !== null) statsOpen = open === '1';
		} catch {
			// Storage blocked — fall back to asking each visit.
		}
	}

	function savePrefs() {
		try {
			localStorage.setItem(viewKey(), JSON.stringify({ mode: viewMode, ids: viewMode === 'custom' ? customIds : [] }));
		} catch {
			// best effort
		}
	}

	function setStatsOpen(open) {
		statsOpen = open;
		try {
			localStorage.setItem(STATS_KEY, open ? '1' : '0');
		} catch {
			// best effort
		}
	}

	const customSet = $derived(new Set(customIds));
	const viewed = $derived(
		viewMode === 'all' ? solutions : viewMode === 'custom' ? solutions.filter((s) => customSet.has(s.id)) : []
	);
	const selected = $derived(solutions.find((s) => s.id === selectedId) ?? null);
	const visible = $derived(typeFilter === 'All' ? viewed : viewed.filter((s) => s.type === typeFilter));
	const feasibleCount = $derived(solutions.filter(isFeasible).length);

	const draftSet = $derived(new Set(draftIds));
	const pickList = $derived.by(() => {
		const q = pickQuery.trim().toLowerCase();
		return q ? solutions.filter((s) => s.name.toLowerCase().includes(q) || s.type.toLowerCase().includes(q)) : solutions;
	});

	function startPicking() {
		// Start a new custom list empty; editing an existing one keeps its picks.
		draftIds = viewMode === 'custom' ? [...customIds] : [];
		pickQuery = '';
		picking = true;
	}

	function toggleDraft(id) {
		draftIds = draftSet.has(id) ? draftIds.filter((x) => x !== id) : [...draftIds, id];
	}

	/** @param {'all' | 'custom'} mode @param {string[]} [ids] */
	function applyView(mode, ids = []) {
		viewMode = mode;
		// Keep ranking order, drop ids no longer in the catalog.
		customIds = mode === 'custom' ? solutions.filter((s) => ids.includes(s.id)).map((s) => s.id) : [];
		picking = false;
		savePrefs();
		if (!visible.length) typeFilter = 'All';
		if (!selectedId || !viewed.some((s) => s.id === selectedId)) selectFirst();
	}

	function selectFirst() {
		const first = viewed.find(isFeasible) ?? viewed[0];
		if (first) {
			void selectSolution(first.id);
		} else {
			selectedId = null;
			popup?.remove();
			setLayer(EMPTY_FC, null);
		}
	}

	function isFeasible(s) {
		return s.metrics?.status === 'ok' && (s.metrics.score ?? 0) > 0;
	}

	function metricText(m) {
		if (!m || m.status !== 'ok') return m?.message ? 'Unavailable' : '—';
		if (m.kind === 'line') return `${m.suitable_km.toLocaleString()} km · ${m.pct}% of streams`;
		return `${Math.round(m.suitable_ha).toLocaleString()} ha · ${m.pct}% of AOI`;
	}

	async function loadSolutions() {
		listAbort?.abort();
		listAbort = new AbortController();
		const { signal } = listAbort;
		loading = true;
		loadError = '';
		try {
			const data = await fetchProjectSolutions(project.id, { signal });
			if (signal.aborted) return;
			solutions = data.solutions ?? [];
			warnings = data.warnings ?? [];
			summary = { aoi_area_ha: data.aoi_area_ha, stream_km: data.stream_km };
			if (viewMode === 'custom') {
				const known = new Set(solutions.map((s) => s.id));
				customIds = customIds.filter((id) => known.has(id));
				if (!customIds.length) viewMode = null;
			}
			// Most feasible first — show the top-ranked viewed solution by default.
			if (viewMode) selectFirst();
		} catch (err) {
			if (signal.aborted || err?.name === 'AbortError') return;
			loadError = err instanceof Error ? err.message : String(err);
		} finally {
			if (!signal.aborted) loading = false;
		}
	}

	async function selectSolution(id) {
		selectedId = id;
		popup?.remove();
		layerError = '';
		// Stop waiting on whichever layer was loading before (its fetch still finishes into the cache).
		layerAbort?.abort();
		layerLoading = false;
		const sol = solutions.find((s) => s.id === id);
		if (!sol || sol.metrics?.status !== 'ok') {
			setLayer(EMPTY_FC, sol);
			return;
		}
		const cached = layerCache.get(id);
		if (cached) {
			setLayer(cached, sol);
			return;
		}
		// Clear the previous solution's layer at once so two solutions never look alike
		// while the new one loads; the map overlay shows progress instead.
		setLayer(EMPTY_FC, sol);
		layerAbort = new AbortController();
		const { signal } = layerAbort;
		layerLoading = true;
		try {
			const fc = await loadLayer(id, signal);
			if (signal.aborted) return;
			if (selectedId === id) setLayer(fc, sol);
		} catch (err) {
			if (signal.aborted || err?.name === 'AbortError') return;
			layerError = err instanceof Error ? err.message : String(err);
			setLayer(EMPTY_FC, sol);
		} finally {
			if (!signal.aborted) layerLoading = false;
		}
		void prefetchLayers();
	}

	/** In-flight layer requests, shared by the selected layer and background prefetch. */
	/** @type {Map<string, Promise<any>>} */
	const inflight = new Map();

	/** @param {string} id @param {AbortSignal} [signal] */
	function loadLayer(id, signal) {
		const hit = layerCache.get(id);
		if (hit) return Promise.resolve(hit);
		let p = inflight.get(id);
		if (!p) {
			// Not tied to the caller's signal: switching away mid-load should not throw the
			// work away — the layer lands in the cache for the next time it's picked.
			p = fetchSolutionGeojson(project.id, id, { signal: prefetchAbort.signal })
				.then((fc) => {
					layerCache.set(id, fc);
					return fc;
				})
				.finally(() => inflight.delete(id));
			inflight.set(id, p);
		}
		if (!signal) return p;
		return new Promise((resolve, reject) => {
			const onAbort = () => reject(new DOMException('Aborted', 'AbortError'));
			if (signal.aborted) return onAbort();
			signal.addEventListener('abort', onAbort, { once: true });
			p.then(resolve, reject).finally(() => signal.removeEventListener('abort', onAbort));
		});
	}

	const prefetchAbort = new AbortController();
	let prefetching = false;

	/** Warm the rest of the feasible layers, two at a time, so later switches are instant. */
	async function prefetchLayers() {
		if (prefetching) return;
		prefetching = true;
		try {
			const queue = viewed.filter((s) => isFeasible(s) && !layerCache.has(s.id)).map((s) => s.id);
			const worker = async () => {
				while (queue.length && !prefetchAbort.signal.aborted) {
					const id = /** @type {string} */ (queue.shift());
					try {
						await loadLayer(id);
					} catch {
						// Best effort — a failure surfaces if the user selects that solution.
					}
				}
			};
			await Promise.all([worker(), worker()]);
		} finally {
			prefetching = false;
		}
	}

	/** Pending data if the style is not ready yet. */
	let pending = /** @type {{ fc: any, sol: any } | null} */ (null);

	function setLayer(fc, sol) {
		if (!map || !mapReady) {
			pending = { fc, sol };
			return;
		}
		// Binary: suitable = the solution category's colour, unsuitable = no fill.
		const color = solColor(sol);
		/** @type {maplibregl.GeoJSONSource} */ (map.getSource('suitable'))?.setData(fc);
		map.setPaintProperty('suitable-fill', 'fill-color', color);
		map.setPaintProperty('suitable-outline', 'line-color', color);
		map.setPaintProperty('suitable-line', 'line-color', color);
	}

	function solColor(sol) {
		return TYPE_COLOR[sol?.type] ?? TYPE_COLOR.Areal;
	}

	// ---------------------------------------------------------------- click → inspect

	/** @type {maplibregl.Popup | null} */
	let popup = null;
	/** @type {AbortController | null} */
	let inspectAbort = null;

	function esc(s) {
		return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
	}

	function popupHtml(r) {
		const head = !r.inside_aoi
			? '<p class="pp-status pp-out">Outside the AOI</p>'
			: r.suitable
				? '<p class="pp-status pp-ok">Suitable here</p>'
				: '<p class="pp-status pp-no">Not suitable here</p>';
		const rows = r.checks
			.map(
				(c) => `<tr>
					<td class="pp-mark ${c.pass ? 'ok' : 'no'}">${c.pass ? '✓' : '✗'}</td>
					<td><b>${esc(c.criterion)}</b><br><span>needs ${esc(c.rule)}</span></td>
					<td class="pp-val">${esc(c.value)}</td>
				</tr>`
			)
			.join('');
		return `<div class="pp">
			<p class="pp-title">${esc(r.solution_name)}</p>
			${head}
			${rows ? `<table>${rows}</table>` : '<p class="pp-note">No GIS criteria for this solution.</p>'}
			<p class="pp-note">${r.lat.toFixed(5)}, ${r.lng.toFixed(5)}</p>
		</div>`;
	}

	async function onMapClick(e) {
		if (!map || !selectedId) return;
		const { lng, lat } = e.lngLat;
		inspectAbort?.abort();
		inspectAbort = new AbortController();
		const { signal } = inspectAbort;
		popup?.remove();
		popup = new maplibregl.Popup({ maxWidth: '320px', className: 'design-popup' })
			.setLngLat([lng, lat])
			.setHTML('<div class="pp"><p class="pp-note">Checking this location…</p></div>')
			.addTo(map);
		try {
			const r = await inspectPoint(project.id, selectedId, lng, lat, { signal });
			if (signal.aborted) return;
			popup?.setHTML(popupHtml(r));
		} catch (err) {
			if (signal.aborted || err?.name === 'AbortError') return;
			popup?.setHTML(`<div class="pp"><p class="pp-status pp-no">${esc(err instanceof Error ? err.message : err)}</p></div>`);
		}
	}

	function boundsOf(p) {
		if (Array.isArray(p.bounds) && p.bounds.length === 4) return p.bounds;
		return null;
	}

	function setBasemap(kind) {
		basemap = kind;
		if (!map || !mapReady) return;
		map.setLayoutProperty('sat', 'visibility', kind === 'satellite' ? 'visible' : 'none');
		map.setLayoutProperty('osm', 'visibility', kind === 'streets' ? 'visible' : 'none');
	}

	/** @type {ResizeObserver | null} */
	let resizeObs = null;

	onMount(() => {
		readPrefs();
		const b = boundsOf(project);
		map = new maplibregl.Map({
			container,
			style: {
				version: 8,
				sources: {
					sat: {
						type: 'raster',
						tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
						tileSize: 256,
						maxzoom: 18,
						attribution: 'Imagery © Esri'
					},
					osm: {
						type: 'raster',
						tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
						tileSize: 256,
						attribution: '© OpenStreetMap'
					}
				},
				layers: [
					{ id: 'sat', type: 'raster', source: 'sat' },
					{ id: 'osm', type: 'raster', source: 'osm', layout: { visibility: 'none' } }
				]
			},
			...(b
				? { bounds: /** @type {[number, number, number, number]} */ (b), fitBoundsOptions: { padding: 40 } }
				: { center: [78.5, 20], zoom: 5 })
		});
		map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
		map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');
		// The stats sidebar opens/closes beside the map — keep the canvas sized to its box.
		resizeObs = new ResizeObserver(() => map?.resize());
		resizeObs.observe(container);

		map.on('load', () => {
			if (!map) return;
			map.addSource('aoi', { type: 'geojson', data: project.aoi_geometry ?? EMPTY_FC });
			map.addSource('suitable', { type: 'geojson', data: EMPTY_FC });
			map.addLayer({
				id: 'aoi-mask',
				type: 'fill',
				source: 'aoi',
				paint: { 'fill-color': '#ffffff', 'fill-opacity': 0.08 }
			});
			map.addLayer({
				id: 'suitable-fill',
				type: 'fill',
				source: 'suitable',
				filter: ['in', ['geometry-type'], ['literal', ['Polygon', 'MultiPolygon']]],
				paint: { 'fill-color': '#0d983b', 'fill-opacity': 0.6 }
			});
			map.addLayer({
				id: 'suitable-outline',
				type: 'line',
				source: 'suitable',
				filter: ['in', ['geometry-type'], ['literal', ['Polygon', 'MultiPolygon']]],
				paint: { 'line-color': '#0d983b', 'line-width': 1, 'line-opacity': 0.9 }
			});
			map.addLayer({
				id: 'suitable-line',
				type: 'line',
				source: 'suitable',
				filter: ['in', ['geometry-type'], ['literal', ['LineString', 'MultiLineString']]],
				layout: { 'line-cap': 'round', 'line-join': 'round' },
				paint: {
					'line-color': '#1b75e0',
					'line-width': ['interpolate', ['linear'], ['zoom'], 10, 2.5, 15, 6]
				}
			});
			// White AOI outline on a dark casing — stays distinct from the red→green zones.
			map.addLayer({
				id: 'aoi-casing',
				type: 'line',
				source: 'aoi',
				paint: { 'line-color': '#0f172a', 'line-width': 4.5, 'line-opacity': 0.55 }
			});
			map.addLayer({
				id: 'aoi-outline',
				type: 'line',
				source: 'aoi',
				paint: { 'line-color': '#ffffff', 'line-width': 2 }
			});
			mapReady = true;
			map.getCanvas().style.cursor = 'crosshair';
			map.on('click', onMapClick);
			setBasemap(basemap);
			if (pending) {
				setLayer(pending.fc, pending.sol);
				pending = null;
			}
		});

		void loadSolutions();
	});

	onDestroy(() => {
		listAbort?.abort();
		layerAbort?.abort();
		prefetchAbort.abort();
		inspectAbort?.abort();
		popup?.remove();
		resizeObs?.disconnect();
		map?.remove();
		map = null;
	});

	function onRowKey(e, id) {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			void selectSolution(id);
		}
	}
</script>

<div class="designer flex min-h-0 flex-1 flex-col md:flex-row">
	{#if statsOpen}
		<WatershedStats {project} onclose={() => setStatsOpen(false)} />
	{:else}
		<button type="button" class="stats-rail" onclick={() => setStatsOpen(true)} aria-label="Show watershed summary" title="Show watershed summary">
			<svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true"><path d="M7.5 4.5 13 10l-5.5 5.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" /></svg>
			<span>Watershed</span>
		</button>
	{/if}

	<aside class="panel flex min-h-0 w-full flex-col border-brand-navy/10 bg-white md:w-[24rem] md:shrink-0 md:border-r">
		<div class="border-b border-brand-navy/10 px-4 py-3">
			<h2 class="m-0 font-headline text-base font-semibold text-brand-navy">Solutions</h2>
			<p class="m-0 mt-0.5 text-xs text-brand-steel">
				Ranked by how much of the area meets the slope, stream order and land-use criteria.
				{#if summary?.aoi_area_ha}
					AOI {Math.round(summary.aoi_area_ha).toLocaleString()} ha · {summary.stream_km?.toLocaleString() ?? 0} km of streams.
				{/if}
			</p>
			{#if viewMode && !picking && !loading && !loadError}
				<div class="view-bar mt-2">
					<span>
						{#if viewMode === 'all'}
							Viewing all <b>{solutions.length}</b> solutions
						{:else}
							Viewing <b>{viewed.length}</b> of {solutions.length} solutions
						{/if}
					</span>
					<button type="button" class="link-btn text-brand-blue" onclick={startPicking}>
						{viewMode === 'all' ? 'Choose solutions' : 'Edit selection'}
					</button>
					{#if viewMode === 'custom'}
						<button type="button" class="link-btn text-brand-blue" onclick={() => applyView('all')}>View all</button>
					{/if}
				</div>
				<div class="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="Filter by solution type">
					{#each TYPE_FILTERS as t (t)}
						<button type="button" class="chip" class:active={typeFilter === t} onclick={() => (typeFilter = t)}>
							{#if t !== 'All'}<span class="dot" style:background-color={TYPE_COLOR[t]}></span>{/if}{t}
						</button>
					{/each}
				</div>
			{/if}
		</div>

		{#if warnings.length}
			<div class="border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-900" role="status">
				{#each warnings as w (w)}<p class="m-0">{w}</p>{/each}
			</div>
		{/if}

		<div class="min-h-0 flex-1 overflow-y-auto">
			{#if loading}
				<div class="flex items-center gap-2 px-4 py-6 text-sm text-brand-steel" role="status">
					<span class="h-4 w-4 animate-spin rounded-full border-2 border-brand-navy/20 border-t-[#0d983b]" aria-hidden="true"></span>
					Analysing slope, land use and drainage…
				</div>
			{:else if loadError}
				<div class="px-4 py-6 text-sm">
					<p class="m-0 text-red-600">{loadError}</p>
					<button type="button" class="mt-2 cursor-pointer rounded border border-brand-navy/20 bg-white px-3 py-1 text-sm" onclick={loadSolutions}>
						Retry
					</button>
				</div>
			{:else if picking}
				<div class="flex h-full min-h-0 flex-col">
					<div class="border-b border-brand-navy/10 px-4 py-3">
						<p class="m-0 text-sm font-semibold text-brand-navy">Choose solutions to view</p>
						<input
							type="search"
							class="search mt-2"
							placeholder="Search by name or type"
							aria-label="Search solutions"
							bind:value={pickQuery}
						/>
						<div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
							<button type="button" class="link-btn text-brand-blue" onclick={() => (draftIds = solutions.map((s) => s.id))}>Select all</button>
							<button type="button" class="link-btn text-brand-blue" onclick={() => (draftIds = solutions.filter(isFeasible).map((s) => s.id))}>Feasible only ({feasibleCount})</button>
							<button type="button" class="link-btn text-brand-blue" onclick={() => (draftIds = [])}>Clear</button>
						</div>
					</div>
					<ul class="m-0 min-h-0 flex-1 list-none overflow-y-auto p-0" aria-label="Solutions to view">
						{#each pickList as sol (sol.id)}
							<li class="pick" class:dim={!isFeasible(sol)} style:--c={TYPE_COLOR[sol.type]}>
								<label class="flex cursor-pointer items-start gap-2.5 px-4 py-2">
									<input type="checkbox" class="mt-0.5" checked={draftSet.has(sol.id)} onchange={() => toggleDraft(sol.id)} />
									<span class="min-w-0 flex-1">
										<span class="flex items-start justify-between gap-2">
											<span class="text-sm font-medium leading-snug text-brand-navy">{sol.name}</span>
											<span class="type">{sol.type}</span>
										</span>
										<span class="block text-xs text-brand-steel">{metricText(sol.metrics)}</span>
									</span>
								</label>
							</li>
						{/each}
						{#if !pickList.length}
							<li class="px-4 py-6 text-sm text-brand-steel">No solutions match "{pickQuery}".</li>
						{/if}
					</ul>
					<div class="flex items-center justify-end gap-2 border-t border-brand-navy/10 bg-white px-4 py-2.5">
						<button type="button" class="btn" onclick={() => (picking = false)}>Cancel</button>
						<button type="button" class="btn primary" disabled={!draftIds.length} onclick={() => applyView('custom', draftIds)}>
							View {draftIds.length} solution{draftIds.length === 1 ? '' : 's'}
						</button>
					</div>
				</div>
			{:else if !viewMode}
				<div class="px-4 py-5">
					<p class="m-0 text-sm font-semibold text-brand-navy">Which solutions do you want to view?</p>
					<p class="m-0 mt-1 text-xs text-brand-steel">
						{solutions.length} solutions were checked for this area; {feasibleCount} have suitable sites. You can change this later.
					</p>
					<div class="mt-3 grid gap-2">
						<button type="button" class="choice" onclick={() => applyView('all')}>
							<b>View all solutions</b>
							<span>Every solution in the catalog, ranked most feasible first.</span>
						</button>
						<button type="button" class="choice" onclick={startPicking}>
							<b>Choose solutions</b>
							<span>Pick a custom list — only those show in the panel and on the map.</span>
						</button>
					</div>
				</div>
			{:else}
				<ul class="m-0 list-none p-0" role="listbox" aria-label="Solutions">
					{#each visible as sol, i (sol.id)}
						{@const feasible = isFeasible(sol)}
						{@const active = sol.id === selectedId}
						<li
							class="row"
							class:active
							class:dim={!feasible}
							role="option"
							aria-selected={active}
							tabindex="0"
							style:--c={TYPE_COLOR[sol.type]}
							onclick={() => selectSolution(sol.id)}
							onkeydown={(e) => onRowKey(e, sol.id)}
						>
							<div class="flex items-start gap-3">
								<span class="radio" aria-hidden="true"></span>
								<div class="min-w-0 flex-1">
									<div class="flex items-start justify-between gap-2">
										<p class="m-0 text-sm font-semibold leading-snug text-brand-navy">{sol.name}</p>
										<span class="type">{sol.type}</span>
									</div>
									<p class="m-0 mt-0.5 text-xs text-brand-steel">{sol.criteria_summary.join(' · ')}</p>
									{#if sol.metrics?.status === 'ok'}
										<!-- Share of the AOI (or stream length) that is suitable, in the category colour. -->
										<div class="bar mt-1.5" aria-hidden="true">
											<span style:width="{Math.min(100, sol.metrics.pct ?? 0)}%" style:background-color={solColor(sol)}></span>
										</div>
									{/if}
									<p class="m-0 mt-1 text-xs font-medium text-brand-navy/80">{metricText(sol.metrics)}</p>
									{#if sol.notes.length}
										<button
											type="button"
											class="link-btn mt-1 text-brand-blue"
											aria-expanded={expandedId === sol.id}
											onclick={(e) => {
												e.stopPropagation();
												expandedId = expandedId === sol.id ? null : sol.id;
											}}
										>
											{expandedId === sol.id ? 'Hide field checks' : 'Field checks'}
										</button>
										{#if expandedId === sol.id}
											<dl class="m-0 mt-1 grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-xs">
												{#each sol.notes as n (n.label)}
													<dt class="text-brand-steel">{n.label}</dt>
													<dd class="m-0 text-brand-navy">{n.value}</dd>
												{/each}
											</dl>
										{/if}
									{/if}
								</div>
							</div>
						</li>
					{/each}
				</ul>
				{#if !visible.length}
					<p class="px-4 py-6 text-sm text-brand-steel">
						No {typeFilter.toLowerCase()} solutions {viewMode === 'custom' ? 'in your selection' : 'in the sheet'}.
					</p>
				{/if}
			{/if}
		</div>
	</aside>

	<section class="relative min-h-[60vh] flex-1">
		<!-- Inline position: maplibre-gl.css sets .maplibregl-map { position: relative }, which would
		     override a utility class and collapse the container to 0 px height. -->
		<div bind:this={container} style="position: absolute; inset: 0;"></div>

		{#if layerLoading && selected}
			<div class="map-loading" role="status" aria-live="polite">
				<div class="map-loading-card" style:--c={solColor(selected)}>
					<span class="spinner" aria-hidden="true"></span>
					<span>Loading <b>{selected.name}</b>…</span>
				</div>
			</div>
		{/if}

		<div class="absolute left-3 top-3 z-10 flex overflow-hidden rounded-md border border-black/10 bg-white text-xs shadow-sm">
			{#each [['satellite', 'Satellite'], ['streets', 'Streets']] as [id, label] (id)}
				<button
					type="button"
					class="cursor-pointer border-0 px-2.5 py-1.5"
					class:bg-brand-navy={basemap === id}
					class:text-white={basemap === id}
					class:bg-white={basemap !== id}
					onclick={() => setBasemap(/** @type {any} */ (id))}
				>
					{label}
				</button>
			{/each}
		</div>

		{#if selected}
			<div class="legend absolute bottom-8 right-3 z-10 max-w-[19rem] rounded-lg bg-white/95 p-3 text-xs shadow-md">
				<div class="flex items-center gap-2">
					<span class="font-semibold text-brand-navy">{selected.name}</span>
				</div>
				<p class="m-0 mt-1 text-brand-steel">
					{selected.geometry_kind === 'line' ? 'Suitable stream reaches' : 'Suitable areas'} · {metricText(selected.metrics)}
				</p>
				{#if selected.metrics?.status === 'ok'}
					<ul class="m-0 mt-2 grid list-none gap-0.5 p-0">
						<li class="flex items-center gap-2">
							{#if selected.geometry_kind === 'line'}
								<span class="inline-block h-[3px] w-4 rounded" style:background-color={solColor(selected)}></span>
							{:else}
								<span class="inline-block h-3 w-3 rounded-sm" style:background-color={solColor(selected)} style:opacity="0.75"></span>
							{/if}
							<span class="text-brand-navy">Suitable</span>
						</li>
						<li class="flex items-center gap-2">
							<span class="inline-block h-3 w-3 rounded-sm border border-brand-navy/25 bg-transparent"></span>
							<span class="text-brand-navy">Not suitable</span>
						</li>
					</ul>
					<p class="m-0 mt-1 text-[10.5px] leading-snug text-brand-steel">Click the map to check any spot.</p>
				{/if}
				{#if layerLoading}
					<p class="m-0 mt-1 text-brand-steel">Drawing layer…</p>
				{:else if layerError}
					<p class="m-0 mt-1 text-red-600">{layerError}</p>
				{:else if selected.metrics?.status !== 'ok'}
					<p class="m-0 mt-1 text-amber-700">{selected.metrics?.message ?? 'Not available for this AOI.'}</p>
				{:else if !isFeasible(selected)}
					<p class="m-0 mt-1 text-amber-700">No location in this AOI meets all the criteria.</p>
				{/if}
				<p class="m-0 mt-1.5 flex items-center gap-1.5 text-brand-steel">
					<span class="inline-block h-[3px] w-4 bg-white ring-1 ring-slate-800/60"></span> AOI boundary
				</p>
			</div>
		{/if}
	</section>
</div>

<style>
	/* The page root is a fixed-height column (see routes/design/[slug]); the designer
	   fills what's left under the header, the list scrolls inside its panel, and the
	   map takes the rest. On phones the panel is capped and the page scrolls. */
	@media (max-width: 767px) {
		.panel {
			max-height: 45vh;
		}
	}
	.stats-rail {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		flex: none;
		cursor: pointer;
		border: 0;
		border-bottom: 1px solid rgba(0, 48, 109, 0.1);
		background: #f7f9fc;
		padding: 0.5rem 1rem;
		font: inherit;
		font-size: 0.75rem;
		font-weight: 600;
		color: #00306d;
	}
	.stats-rail:hover {
		background: #eef3fa;
	}
	@media (min-width: 768px) {
		.stats-rail {
			flex-direction: column;
			width: 2.25rem;
			padding: 0.75rem 0;
			border-bottom: 0;
			border-right: 1px solid rgba(0, 48, 109, 0.1);
		}
		.stats-rail span {
			writing-mode: vertical-rl;
			transform: rotate(180deg);
		}
	}
	.view-bar {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.25rem 0.75rem;
		font-size: 0.75rem;
		color: #24303a;
	}
	.choice {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		cursor: pointer;
		border-radius: 0.6rem;
		border: 1px solid rgba(0, 48, 109, 0.15);
		background: white;
		padding: 0.65rem 0.8rem;
		text-align: left;
		font: inherit;
	}
	.choice:hover {
		border-color: #1b75e0;
		background: #f4f8fe;
	}
	.choice b {
		font-size: 0.85rem;
		color: #00306d;
	}
	.choice span {
		font-size: 0.75rem;
		color: #56646f;
	}
	.search {
		width: 100%;
		box-sizing: border-box;
		border-radius: 0.4rem;
		border: 1px solid rgba(0, 48, 109, 0.2);
		padding: 0.35rem 0.6rem;
		font: inherit;
		font-size: 0.8rem;
	}
	.pick {
		border-bottom: 1px solid rgba(0, 48, 109, 0.07);
	}
	.pick:hover {
		background: rgba(0, 48, 109, 0.03);
	}
	.pick.dim {
		opacity: 0.6;
	}
	.btn {
		cursor: pointer;
		border-radius: 0.4rem;
		border: 1px solid rgba(0, 48, 109, 0.2);
		background: white;
		padding: 0.35rem 0.8rem;
		font: inherit;
		font-size: 0.8rem;
		color: #00306d;
	}
	.btn.primary {
		border-color: #00306d;
		background: #00306d;
		color: white;
	}
	.btn:disabled {
		cursor: not-allowed;
		opacity: 0.5;
	}
	/* Map-wide veil while a solution's layer loads, so the stale map never reads as the new one. */
	.map-loading {
		position: absolute;
		inset: 0;
		z-index: 5;
		display: grid;
		place-items: center;
		background: rgba(15, 23, 42, 0.28);
		pointer-events: none;
		animation: veil-in 0.15s ease-out;
	}
	.map-loading-card {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		max-width: min(22rem, calc(100% - 2rem));
		padding: 0.6rem 0.9rem;
		border-radius: 0.6rem;
		border-left: 4px solid var(--c);
		background: rgba(255, 255, 255, 0.96);
		box-shadow: 0 10px 30px -12px rgba(0, 30, 60, 0.45);
		font-size: 0.8rem;
		color: #0f172a;
	}
	.spinner {
		flex: none;
		width: 1rem;
		height: 1rem;
		border-radius: 999px;
		border: 2px solid color-mix(in srgb, var(--c) 25%, transparent);
		border-top-color: var(--c);
		animation: spin 0.7s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	@keyframes veil-in {
		from {
			opacity: 0;
		}
	}
	.link-btn {
		cursor: pointer;
		border: 0;
		background: transparent;
		padding: 0;
		font-size: 0.75rem;
		text-underline-offset: 2px;
	}
	.link-btn:hover {
		text-decoration: underline;
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		cursor: pointer;
		border-radius: 999px;
		border: 1px solid rgba(0, 48, 109, 0.18);
		background: white;
		padding: 0.2rem 0.65rem;
		font: inherit;
		font-size: 0.75rem;
		color: #56646f;
	}
	.chip.active {
		border-color: #00306d;
		background: #00306d;
		color: white;
	}
	.dot {
		height: 0.5rem;
		width: 0.5rem;
		border-radius: 999px;
	}
	.row {
		cursor: pointer;
		border-bottom: 1px solid rgba(0, 48, 109, 0.07);
		border-left: 3px solid transparent;
		padding: 0.7rem 1rem 0.7rem calc(1rem - 3px);
		outline: none;
	}
	.row:hover {
		background: rgba(0, 48, 109, 0.03);
	}
	.row:focus-visible {
		box-shadow: inset 0 0 0 2px #1b75e0;
	}
	.row.active {
		border-left-color: var(--c);
		background: color-mix(in srgb, var(--c) 7%, white);
	}
	.row.dim {
		opacity: 0.55;
	}
	.row.dim.active {
		opacity: 0.85;
	}
	.radio {
		margin-top: 0.15rem;
		height: 0.9rem;
		width: 0.9rem;
		flex-shrink: 0;
		border-radius: 999px;
		border: 2px solid rgba(0, 48, 109, 0.3);
	}
	.row.active .radio {
		border-color: var(--c);
		background: radial-gradient(circle, var(--c) 0 45%, white 50%);
	}
	.type {
		flex-shrink: 0;
		border-radius: 999px;
		background: color-mix(in srgb, var(--c) 12%, white);
		padding: 0.05rem 0.45rem;
		font-size: 0.65rem;
		font-weight: 600;
		color: color-mix(in srgb, var(--c) 75%, black);
	}
	.bar {
		height: 4px;
		overflow: hidden;
		border-radius: 999px;
		background: rgba(0, 48, 109, 0.08);
	}
	.bar {
		display: flex;
	}
	.bar span {
		display: block;
		height: 100%;
	}
	/* Click popup (rendered by maplibre outside this component). */
	:global(.design-popup .maplibregl-popup-content) {
		border-radius: 10px;
		padding: 10px 12px;
		box-shadow: 0 10px 30px -12px rgba(0, 30, 60, 0.45);
	}
	:global(.design-popup .pp) {
		font-size: 12px;
		color: #24303a;
	}
	:global(.design-popup .pp-title) {
		margin: 0 16px 2px 0;
		font-weight: 700;
		color: #00306d;
	}
	:global(.design-popup .pp-status) {
		margin: 0 0 6px;
		font-weight: 600;
	}
	:global(.design-popup .pp-status span) {
		font-weight: 400;
		color: #56646f;
	}
	:global(.design-popup .pp-ok) {
		color: #0b7d31;
	}
	:global(.design-popup .pp-no) {
		color: #b91c1c;
	}
	:global(.design-popup .pp-out) {
		color: #56646f;
	}
	:global(.design-popup table) {
		width: 100%;
		border-collapse: collapse;
	}
	:global(.design-popup td) {
		padding: 3px 4px 3px 0;
		vertical-align: top;
		border-top: 1px solid rgba(0, 48, 109, 0.08);
	}
	:global(.design-popup td span) {
		color: #6b7885;
		font-size: 11px;
	}
	:global(.design-popup .pp-val) {
		text-align: right;
		white-space: nowrap;
		font-weight: 600;
	}
	:global(.design-popup .pp-mark) {
		width: 14px;
		font-weight: 700;
	}
	:global(.design-popup .pp-mark.ok) {
		color: #0b7d31;
	}
	:global(.design-popup .pp-mark.no) {
		color: #b91c1c;
	}
	:global(.design-popup .pp-note) {
		margin: 6px 0 0;
		color: #6b7885;
		font-size: 11px;
	}
</style>
