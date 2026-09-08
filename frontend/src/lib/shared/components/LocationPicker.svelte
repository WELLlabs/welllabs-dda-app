<script>
	import { onDestroy, onMount } from 'svelte';
	import maplibregl from 'maplibre-gl';
	import 'maplibre-gl/dist/maplibre-gl.css';

	/** Fixed colours — one per hierarchy level */
	const MICRO_COLOR = '#1c75e9';
	const VILLAGE_COLOR = '#1f2937';
	const LEGEND_STATIC = [
		{ id: 'basin', name: 'Basin', color: '#00306d', style: 'solid' },
		{ id: 'sub_basin', name: 'Sub basin', color: '#7c3aed', style: 'solid' },
		{ id: 'level7', name: 'Level-7 watershed', color: '#db2777', style: 'solid' },
		{ id: 'micro', name: 'Micro watershed (L12)', color: MICRO_COLOR, style: 'solid' },
		{ id: 'rivers', name: 'Rivers', color: '#457b9d', style: 'solid' },
		{ id: 'village', name: 'Village boundary', color: VILLAGE_COLOR, style: 'dashed' }
	];

	/** @type {{
	 *   lng?: number,
	 *   lat?: number,
	 *   onPick?: (p: { lng: number, lat: number }) => void,
	 *   onBounds?: (b: [number, number, number, number]) => void,
	 *   clipGeometry?: object | null,
	 *   villageGeometry?: object | null,
	 *   villageName?: string | null,
	 *   parts?: Array<{ geometry?: object, watershed_id?: string, watershed_name?: string }> | null,
	 *   contextLayers?: Array<{
	 *     id: string,
	 *     name?: string,
	 *     geometry_kind?: string,
	 *     render_type?: string,
	 *     line_color?: string,
	 *     line_width?: number,
	 *     fill_color?: string | null,
	 *     fill_opacity?: number,
	 *     geojson?: object,
	 *     status?: string
	 *   }> | null,
	 *   interactiveClick?: boolean,
	 *   showMarker?: boolean,
	 *   hint?: string
	 * }} */
	let {
		lng = $bindable(77.2),
		lat = $bindable(28.6),
		onPick,
		onBounds,
		clipGeometry = null,
		villageGeometry = null,
		villageName = null,
		parts = null,
		contextLayers = null,
		interactiveClick = true,
		showMarker = undefined,
		hint = 'Click the map to set the project location.'
	} = $props();

	const markerVisible = $derived(showMarker ?? interactiveClick);

	const showLegend = $derived(
		Boolean(
			(parts && parts.length) ||
				villageGeometry ||
				(contextLayers && contextLayers.length) ||
				clipGeometry
		)
	);

	const legendItems = $derived.by(() => {
		const byId = new Map(LEGEND_STATIC.map((item) => [item.id, { ...item }]));
		for (const layer of contextLayers || []) {
			const item = byId.get(layer.id);
			if (!item) continue;
			if (layer.line_color) item.color = layer.line_color;
			if (layer.status === 'error') item.error = true;
		}
		const order = ['basin', 'sub_basin', 'level7', 'micro', 'rivers', 'village'];
		return order.map((id) => byId.get(id)).filter(Boolean);
	});

	let container;
	let map;
	let marker = null;
	let styleReady = $state(false);
	/** @type {string[]} */
	let contextSourceIds = [];
	/** @type {maplibregl.Popup | null} */
	let villagePopup = null;

	const CLIP_SOURCE = 'clip-aoi';
	const PARTS_SOURCE = 'clip-parts';
	const VILLAGE_SOURCE = 'village-boundary';

	function emitBounds() {
		if (!map || !onBounds) return;
		const b = map.getBounds();
		onBounds([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]);
	}

	onMount(() => {
		map = new maplibregl.Map({
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
			center: [lng, lat],
			zoom: 5
		});

		map.addControl(new maplibregl.NavigationControl(), 'top-right');

		map.on('load', () => {
			styleReady = true;
			ensureOverlayLayers();
			if (interactiveClick) placeMarker(lng, lat);
			syncOverlays();
			emitBounds();
		});

		map.on('moveend', emitBounds);

		map.on('click', (e) => {
			if (!interactiveClick) return;
			lng = e.lngLat.lng;
			lat = e.lngLat.lat;
			placeMarker(lng, lat);
			onPick?.({ lng, lat });
		});
	});

	onDestroy(() => {
		villagePopup?.remove();
		map?.remove();
	});

	function placeMarker(lon, latVal) {
		if (!map?.isStyleLoaded()) return;
		if (marker) marker.remove();
		marker = new maplibregl.Marker({ color: '#1b75e0' }).setLngLat([lon, latVal]).addTo(map);
	}

	function clearMarker() {
		if (marker) {
			marker.remove();
			marker = null;
		}
	}

	function ensureOverlayLayers() {
		if (!map?.getSource(PARTS_SOURCE)) {
			map.addSource(PARTS_SOURCE, {
				type: 'geojson',
				data: emptyFc()
			});
			map.addLayer({
				id: 'parts-fill',
				type: 'fill',
				source: PARTS_SOURCE,
				paint: {
					'fill-color': MICRO_COLOR,
					'fill-opacity': 0.32
				}
			});
			map.addLayer({
				id: 'parts-line',
				type: 'line',
				source: PARTS_SOURCE,
				paint: {
					'line-color': MICRO_COLOR,
					'line-width': 1.8,
					'line-opacity': 0.95
				}
			});
		}
		if (!map?.getSource(CLIP_SOURCE)) {
			map.addSource(CLIP_SOURCE, {
				type: 'geojson',
				data: emptyFc()
			});
			map.addLayer({
				id: 'clip-fill',
				type: 'fill',
				source: CLIP_SOURCE,
				paint: {
					'fill-color': '#1b75e0',
					'fill-opacity': 0.12
				}
			});
			map.addLayer({
				id: 'clip-line',
				type: 'line',
				source: CLIP_SOURCE,
				paint: {
					'line-color': '#00306d',
					'line-width': 1.5,
					'line-dasharray': [2, 2]
				}
			});
		}
		if (!map?.getSource(VILLAGE_SOURCE)) {
			map.addSource(VILLAGE_SOURCE, {
				type: 'geojson',
				data: emptyFc()
			});
			map.addLayer({
				id: 'village-fill',
				type: 'fill',
				source: VILLAGE_SOURCE,
				paint: {
					'fill-color': VILLAGE_COLOR,
					'fill-opacity': 0.06
				}
			});
			map.addLayer({
				id: 'village-line',
				type: 'line',
				source: VILLAGE_SOURCE,
				paint: {
					'line-color': VILLAGE_COLOR,
					'line-width': 2.75,
					'line-dasharray': [2, 1.5],
					'line-opacity': 1
				}
			});
			villagePopup = new maplibregl.Popup({
				closeButton: false,
				closeOnClick: false,
				offset: 10,
				className: 'village-hover-popup'
			});
			const showVillageTip = (e) => {
				const hit = map.queryRenderedFeatures(e.point, {
					layers: ['village-fill', 'village-line']
				});
				const props = hit[0]?.properties || {};
				const label =
					props.name ||
					props.village_name ||
					props['Village Na'] ||
					props['Village Name'] ||
					'';
				if (!label) {
					villagePopup?.remove();
					return;
				}
				map.getCanvas().style.cursor = 'pointer';
				villagePopup
					.setLngLat(e.lngLat)
					.setHTML(`<strong>${String(label).replace(/</g, '&lt;')}</strong>`)
					.addTo(map);
			};
			const hideVillageTip = () => {
				villagePopup?.remove();
				map.getCanvas().style.cursor = interactiveClick ? 'crosshair' : '';
			};
			map.on('mousemove', 'village-fill', showVillageTip);
			map.on('mousemove', 'village-line', showVillageTip);
			map.on('mouseleave', 'village-fill', hideVillageTip);
			map.on('mouseleave', 'village-line', hideVillageTip);
		}
	}

	function emptyFc() {
		return { type: 'FeatureCollection', features: [] };
	}

	function asFeature(geometry, properties = {}) {
		if (!geometry) return null;
		if (geometry.type === 'Feature') {
			return {
				...geometry,
				properties: { ...(geometry.properties || {}), ...properties }
			};
		}
		if (geometry.type === 'FeatureCollection') return null;
		return { type: 'Feature', properties, geometry };
	}

	function clearContextLayers() {
		for (const id of contextSourceIds) {
			const fillId = `ctx-${id}-fill`;
			const lineId = `ctx-${id}-line`;
			if (map.getLayer(fillId)) map.removeLayer(fillId);
			if (map.getLayer(lineId)) map.removeLayer(lineId);
			if (map.getSource(`ctx-${id}`)) map.removeSource(`ctx-${id}`);
		}
		contextSourceIds = [];
	}

	function syncContextLayers() {
		if (!map?.isStyleLoaded() || !styleReady) return;
		clearContextLayers();
		const layers = (contextLayers || []).filter((l) => l && l.status !== 'error' && l.geojson);
		// Draw under AOI overlays: insert before parts-fill when present.
		const beforeId = map.getLayer('parts-fill') ? 'parts-fill' : undefined;
		for (const layer of layers) {
			const sourceId = `ctx-${layer.id}`;
			const isLine = layer.geometry_kind === 'line' || layer.render_type === 'line';
			map.addSource(sourceId, {
				type: 'geojson',
				data: layer.geojson || emptyFc()
			});
			if (!isLine) {
				map.addLayer(
					{
						id: `${sourceId}-fill`,
						type: 'fill',
						source: sourceId,
						paint: {
							'fill-color': layer.fill_color || layer.line_color || '#64748b',
							'fill-opacity': layer.fill_opacity ?? 0.08
						}
					},
					beforeId
				);
			}
			map.addLayer(
				{
					id: `${sourceId}-line`,
					type: 'line',
					source: sourceId,
					paint: {
						'line-color': layer.line_color || '#334155',
						'line-width': layer.line_width ?? 1.5,
						'line-opacity': 0.9
					}
				},
				beforeId
			);
			contextSourceIds.push(layer.id);
		}
	}

	function syncOverlays() {
		if (!map?.isStyleLoaded() || !styleReady) return;
		ensureOverlayLayers();
		syncContextLayers();

		const partFeats = [];
		(parts || []).forEach((part) => {
			const f = asFeature(part?.geometry, {
				role: 'part',
				color: MICRO_COLOR,
				watershed_id: part?.watershed_id ?? '',
				watershed_name: part?.watershed_name ?? ''
			});
			if (f) partFeats.push(f);
		});
		map.getSource(PARTS_SOURCE).setData({
			type: 'FeatureCollection',
			features: partFeats
		});

		const clipFeat = asFeature(clipGeometry, { role: 'clip' });
		// Village mode: colored basins + village outline. Point/custom: clip polygon.
		map.getSource(CLIP_SOURCE).setData({
			type: 'FeatureCollection',
			features: !villageGeometry && clipFeat ? [clipFeat] : []
		});
		if (map.getLayer('clip-fill')) {
			map.setPaintProperty('clip-fill', 'fill-opacity', partFeats.length ? 0.1 : 0.22);
		}

		const villageFeat = asFeature(villageGeometry, {
			role: 'village',
			name: villageName || 'Village boundary'
		});
		map.getSource(VILLAGE_SOURCE).setData({
			type: 'FeatureCollection',
			features: villageFeat ? [villageFeat] : []
		});

		const bounds = boundsFromGeoms([
			villageGeometry,
			clipGeometry,
			...(parts || []).map((p) => p?.geometry)
		]);
		if (bounds) {
			map.fitBounds(bounds, { padding: 48, maxZoom: 12, duration: 500 });
		}
	}

	/** @param {Array<object|null|undefined>} geoms */
	function boundsFromGeoms(geoms) {
		let minX = Infinity,
			minY = Infinity,
			maxX = -Infinity,
			maxY = -Infinity;
		let found = false;
		const visit = (coords) => {
			if (!Array.isArray(coords)) return;
			if (typeof coords[0] === 'number' && typeof coords[1] === 'number') {
				minX = Math.min(minX, coords[0]);
				minY = Math.min(minY, coords[1]);
				maxX = Math.max(maxX, coords[0]);
				maxY = Math.max(maxY, coords[1]);
				found = true;
				return;
			}
			for (const c of coords) visit(c);
		};
		const walkGeom = (g) => {
			if (!g) return;
			if (g.type === 'FeatureCollection') {
				for (const f of g.features || []) walkGeom(f);
				return;
			}
			const geom = g.type === 'Feature' ? g.geometry : g;
			if (geom?.coordinates) visit(geom.coordinates);
		};
		for (const g of geoms) walkGeom(g);
		if (!found) return null;
		return [
			[minX, minY],
			[maxX, maxY]
		];
	}

	$effect(() => {
		if (!map?.isStyleLoaded()) return;
		if (markerVisible) {
			placeMarker(lng, lat);
			if (!interactiveClick) {
				map.flyTo({
					center: [lng, lat],
					zoom: Math.max(map.getZoom(), 9),
					duration: 500
				});
			}
		} else {
			clearMarker();
		}
	});

	$effect(() => {
		clipGeometry;
		villageGeometry;
		villageName;
		parts;
		contextLayers;
		interactiveClick;
		if (styleReady) syncOverlays();
	});
</script>

<div class="picker-root relative flex h-full min-h-0 flex-col gap-2">
	{#if hint}
		<p class="m-0 shrink-0 text-sm text-gray-600">{hint}</p>
	{/if}
	<div class="map-wrap relative min-h-0 flex-1">
		<div bind:this={container} class="absolute inset-0 rounded-lg border border-gray-200"></div>
		{#if showLegend}
			<div
				class="legend pointer-events-none absolute bottom-3 left-3 z-10 max-w-[min(100%-1.5rem,22rem)] rounded-lg border border-brand-navy/15 bg-white/95 px-3 py-2 shadow-md"
			>
				<p class="m-0 mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-brand-navy">
					Legend
				</p>
				<ul class="m-0 flex flex-wrap gap-x-4 gap-y-1.5 p-0 text-[11px] text-brand-steel list-none">
					{#each legendItems as item (item.id)}
						<li class="inline-flex items-center gap-1.5">
							<span
								class="legend-swatch"
								class:dashed={item.style === 'dashed'}
								style="--swatch:{item.color}"
							></span>
							{item.name}
							{#if item.error}
								<span class="text-red-600">(unavailable)</span>
							{/if}
						</li>
					{/each}
				</ul>
			</div>
		{/if}
	</div>
	{#if markerVisible}
		<p class="m-0 shrink-0 text-xs text-gray-500">
			Selected: {lng.toFixed(5)}, {lat.toFixed(5)}
		</p>
	{/if}
</div>

<style>
	.legend-swatch {
		display: inline-block;
		height: 0.35rem;
		width: 1.1rem;
		border-radius: 999px;
		background: var(--swatch);
		flex-shrink: 0;
	}
	.legend-swatch.dashed {
		background: repeating-linear-gradient(
			90deg,
			var(--swatch) 0 4px,
			transparent 4px 7px
		);
		height: 0.2rem;
		border-radius: 0;
	}
</style>
