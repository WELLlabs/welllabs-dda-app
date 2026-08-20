<script>
	import { onDestroy, untrack } from 'svelte';
	import maplibregl from 'maplibre-gl';
	import 'maplibre-gl/dist/maplibre-gl.css';
	import * as d3 from 'd3';
	import {
		ASSESS_GREEN,
		GREEN_SCALE
	} from '$lib/modules/assess/form-explore.js';
	import FormExploreSidePanel from './FormExploreSidePanel.svelte';

	/**
	 * @type {{
	 *   sites: any[],
	 *   columns: any[],
	 *   numericFields: any[],
	 *   prefs: any,
	 *   onPrefs: (patch: object) => void,
	 *   selectedKey?: string | null
	 * }}
	 */
	let {
		sites = [],
		columns = [],
		numericFields = [],
		prefs,
		onPrefs,
		selectedKey = $bindable(null)
	} = $props();

	/** @type {HTMLElement | undefined} */
	let container = $state();
	/** @type {maplibregl.Map | null} */
	let map = null;
	/** @type {ResizeObserver | null} */
	let ro = null;

	const selected = $derived(sites.find((s) => s.key === selectedKey) || null);

	$effect(() => {
		if (!selectedKey && sites.length) selectedKey = sites[0].key;
	});

	$effect(() => {
		selectedKey;
		if (!map || !selectedKey) return;
		const site = sites.find((s) => s.key === selectedKey);
		if (!site) return;
		map.easeTo({
			center: [site.lon, site.lat],
			duration: 450,
			padding: 40
		});
	});

	$effect(() => {
		if (!container) return;

		const start = untrack(() => sites[0]);
		const instance = new maplibregl.Map({
			container,
			style: {
				version: 8,
				sources: {
					osm: {
						type: 'raster',
						tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
						tileSize: 256,
						attribution: '© OpenStreetMap'
					}
				},
				layers: [{ id: 'osm', type: 'raster', source: 'osm' }]
			},
			center: start ? [start.lon, start.lat] : [78.5, 20.5],
			zoom: start ? 8 : 4
		});
		map = instance;
		instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
		instance.on('load', () => {
			ensureLayer();
			fitSites();
			instance.resize();
		});
		instance.on('click', 'sites-circle', (e) => {
			const f = e.features?.[0];
			if (f?.properties?.key) selectedKey = f.properties.key;
		});
		instance.on('mouseenter', 'sites-circle', () => {
			instance.getCanvas().style.cursor = 'pointer';
		});
		instance.on('mouseleave', 'sites-circle', () => {
			instance.getCanvas().style.cursor = '';
		});

		const observer = new ResizeObserver(() => instance.resize());
		observer.observe(container);
		ro = observer;

		return () => {
			observer.disconnect();
			instance.remove();
			if (map === instance) map = null;
		};
	});

	$effect(() => {
		sites;
		prefs.sizeField;
		prefs.colorField;
		selectedKey;
		if (map?.isStyleLoaded()) {
			ensureLayer();
			updatePaint();
			requestAnimationFrame(() => map?.resize());
		}
	});

	onDestroy(() => {
		ro?.disconnect();
		map?.remove();
		map = null;
	});

	function metricForSite(site, field) {
		if (!field) return null;
		const vals = site.rows
			.map((r) => Number(r[field]))
			.filter((n) => !Number.isNaN(n));
		if (!vals.length) return null;
		return d3.mean(vals);
	}

	function geojson() {
		return {
			type: 'FeatureCollection',
			features: sites.map((site) => ({
				type: 'Feature',
				properties: {
					key: site.key,
					selected: site.key === selectedKey ? 1 : 0,
					sizeVal: metricForSite(site, prefs.sizeField),
					colorVal: metricForSite(site, prefs.colorField),
					count: site.rows.length
				},
				geometry: { type: 'Point', coordinates: [site.lon, site.lat] }
			}))
		};
	}

	function ensureLayer() {
		if (!map) return;
		const data = geojson();
		if (map.getSource('sites')) {
			/** @type {any} */ (map.getSource('sites')).setData(data);
		} else {
			map.addSource('sites', { type: 'geojson', data });
			map.addLayer({
				id: 'sites-circle',
				type: 'circle',
				source: 'sites',
				paint: {
					'circle-radius': 8,
					'circle-color': ASSESS_GREEN,
					'circle-opacity': 0.85,
					'circle-stroke-width': 1.5,
					'circle-stroke-color': '#fff'
				}
			});
		}
		updatePaint();
	}

	function updatePaint() {
		if (!map?.getLayer('sites-circle')) return;
		const sizeVals = sites
			.map((s) => metricForSite(s, prefs.sizeField))
			.filter((v) => v != null);
		const colorVals = sites
			.map((s) => metricForSite(s, prefs.colorField))
			.filter((v) => v != null);

		if (prefs.sizeField && sizeVals.length) {
			const [lo, hi] = d3.extent(sizeVals);
			map.setPaintProperty('sites-circle', 'circle-radius', [
				'interpolate',
				['linear'],
				['coalesce', ['get', 'sizeVal'], lo],
				lo,
				6,
				hi,
				22
			]);
		} else {
			map.setPaintProperty('sites-circle', 'circle-radius', [
				'case',
				['==', ['get', 'selected'], 1],
				12,
				8
			]);
		}

		if (prefs.colorField && colorVals.length) {
			const [lo, hi] = d3.extent(colorVals);
			const mid = lo + (hi - lo) / 2;
			map.setPaintProperty('sites-circle', 'circle-color', [
				'interpolate',
				['linear'],
				['coalesce', ['get', 'colorVal'], lo],
				lo,
				GREEN_SCALE[0],
				mid,
				GREEN_SCALE[2],
				hi,
				GREEN_SCALE[4]
			]);
		} else {
			map.setPaintProperty('sites-circle', 'circle-color', ASSESS_GREEN);
		}

		map.setPaintProperty('sites-circle', 'circle-stroke-width', [
			'case',
			['==', ['get', 'selected'], 1],
			3,
			1.5
		]);
		map.setPaintProperty('sites-circle', 'circle-stroke-color', [
			'case',
			['==', ['get', 'selected'], 1],
			'#14532d',
			'#ffffff'
		]);
	}

	function fitSites() {
		if (!map || !sites.length) return;
		const bounds = new maplibregl.LngLatBounds();
		for (const s of sites) bounds.extend([s.lon, s.lat]);
		map.fitBounds(bounds, { padding: 48, maxZoom: 12, duration: 600 });
	}

	const panelProps = $derived({
		site: selected,
		columns,
		dateField: prefs.dateField,
		barField: prefs.barField,
		lineField: prefs.lineField,
		boxField: prefs.boxField || prefs.barField,
		timeGrain: prefs.timeGrain,
		lineTimeGrain: prefs.lineTimeGrain || prefs.timeGrain || 'daily',
		boxTimeGrain: prefs.boxTimeGrain || prefs.timeGrain || 'daily',
		numericFields,
		onChange: onPrefs
	});
</script>

<div class="map-shell">
	<div class="dashboard">
		<div class="row row-top">
			<FormExploreSidePanel {...panelProps} section="about" />
			<section class="cell cell-map">
				<div class="map-controls">
					<label class="ctrl">
						<span class="font-body text-sm font-medium text-brand-navy">Size by</span>
						<select
							class="rounded border border-brand-navy/20 px-2 py-1.5 font-body text-sm"
							value={prefs.sizeField || ''}
							onchange={(e) => onPrefs({ sizeField: e.currentTarget.value || null })}
						>
							<option value="">Fixed</option>
							{#each numericFields as f (f.name)}
								<option value={f.name}>{f.label}</option>
							{/each}
						</select>
					</label>
					<label class="ctrl">
						<span class="font-body text-sm font-medium text-brand-navy">Color by</span>
						<select
							class="rounded border border-brand-navy/20 px-2 py-1.5 font-body text-sm"
							value={prefs.colorField || ''}
							onchange={(e) => onPrefs({ colorField: e.currentTarget.value || null })}
						>
							<option value="">Fixed</option>
							{#each numericFields as f (f.name)}
								<option value={f.name}>{f.label}</option>
							{/each}
						</select>
					</label>
				</div>
				<div class="map-frame">
					<div bind:this={container} class="map-canvas"></div>
				</div>
			</section>
		</div>

		<div class="row row-charts">
			<FormExploreSidePanel {...panelProps} section="bar" />
			<FormExploreSidePanel {...panelProps} section="line" />
		</div>

		<div class="row row-calendar">
			<FormExploreSidePanel {...panelProps} section="calendar" />
			<FormExploreSidePanel {...panelProps} section="box" />
		</div>
	</div>
</div>

<style>
	.map-shell {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-height: 0;
		height: 100%;
	}
	.dashboard {
		display: flex;
		flex-direction: column;
		gap: 0.85rem;
		flex: 1;
		min-height: 0;
		overflow: auto;
		padding: 0.85rem;
		border-radius: 1rem;
		border: 1px solid rgba(20, 40, 60, 0.1);
		background: #eef2f4;
	}
	.row {
		display: grid;
		gap: 0.85rem;
		min-width: 0;
	}
	.row-top {
		grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
		align-items: stretch;
		flex: 0 0 auto;
	}
	.row-charts {
		grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
		flex: 1 1 auto;
		min-height: 280px;
	}
	.row-calendar {
		grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
		flex: 0 0 auto;
		min-height: 280px;
	}
	.cell-map {
		display: flex;
		flex-direction: column;
		min-width: 0;
		min-height: 0;
		height: 100%;
		padding: 0;
		overflow: hidden;
		background: white;
		border: 1px solid rgba(20, 40, 60, 0.08);
		border-radius: 0.75rem;
	}
	.map-controls {
		display: flex;
		flex-wrap: wrap;
		align-items: end;
		gap: 0.65rem;
		flex-shrink: 0;
		padding: 0.65rem 0.85rem;
		border-bottom: 1px solid rgba(20, 40, 60, 0.08);
		background: white;
	}
	.ctrl {
		display: grid;
		gap: 0.2rem;
	}
	.hint {
		font-size: 0.75rem;
		font-family: var(--font-mono, ui-monospace, monospace);
		color: #6b7885;
		margin-left: auto;
		padding-bottom: 0.35rem;
	}
	.map-frame {
		position: relative;
		flex: 1;
		min-height: 120px;
		background: #d9e2ea;
		border-radius: 0 0 0.75rem 0.75rem;
	}
	.map-canvas {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
	}
	:global(.row-top .cell-about) {
		min-width: 0;
		height: auto;
		border: 1px solid rgba(20, 40, 60, 0.08);
		border-radius: 0.75rem;
		background: white;
	}
	:global(.row-charts .cell-graph),
	:global(.row-charts .cell-line) {
		min-width: 0;
		min-height: 280px;
		height: 100%;
		border: 1px solid rgba(20, 40, 60, 0.08);
		border-radius: 0.75rem;
		background: white;
	}
	:global(.row-calendar .cell-calendar),
	:global(.row-calendar .cell-box) {
		min-width: 0;
		min-height: 280px;
		height: 100%;
		border: 1px solid rgba(20, 40, 60, 0.08);
		border-radius: 0.75rem;
		background: white;
	}
	:global(.row-charts .chart-host) {
		padding-bottom: 0.5rem;
	}
	@media (max-width: 960px) {
		.map-shell {
			height: auto;
			min-height: 36rem;
		}
		.row-top,
		.row-charts,
		.row-calendar {
			grid-template-columns: 1fr;
		}
		.cell-map {
			min-height: 260px;
		}
	}
</style>
