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
	 *   selectedPartId?: string | null,
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
		selectedPartId = null,
		contextLayers = null,
		interactiveClick = true,
		showMarker = undefined,
		hint = 'Click the map to set the project location.'
	} = $props();

	const markerVisible = $derived(showMarker ?? interactiveClick);
	/** Match legend “Micro watershed (L12)” */
	const SELECTED_COLOR = MICRO_COLOR;
	/** Same family, clearly secondary — listed as “Other micros” when multi-select */
	const UNSELECTED_COLOR = '#7eb6f5';
	const CLIP_ACCENT = '#ea580c';

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
		const items = order.map((id) => byId.get(id)).filter(Boolean);
		const multi = Array.isArray(parts) && parts.length > 1;
		const choosingOne = multi && selectedPartId && selectedPartId !== 'all';
		if (choosingOne) {
			const micro = items.find((i) => i.id === 'micro');
			if (micro) micro.name = 'Selected micro';
			const microIdx = items.findIndex((i) => i.id === 'micro');
			const other = {
				id: 'micro_other',
				name: 'Other micros',
				color: UNSELECTED_COLOR,
				style: 'solid'
			};
			if (microIdx >= 0) items.splice(microIdx + 1, 0, other);
			else items.push(other);
		}
		if (clipGeometry) {
			items.push({
				id: 'selected_clip',
				name: 'Selected clip',
				color: CLIP_ACCENT,
				style: 'dashed'
			});
		}
		return items;
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
			map.getCanvas().style.cursor = interactiveClick ? 'crosshair' : 'default';
			if (interactiveClick) placeMarker(lng, lat);
			else clearMarker();
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
					'fill-color': [
						'case',
						['==', ['get', 'selected'], 1],
						SELECTED_COLOR,
						UNSELECTED_COLOR
					],
					'fill-opacity': [
						'case',
						['==', ['get', 'selected'], 1],
						0.45,
						0.28
					]
				}
			});
			map.addLayer({
				id: 'parts-line',
				type: 'line',
				source: PARTS_SOURCE,
				paint: {
					'line-color': [
						'case',
						['==', ['get', 'selected'], 1],
						SELECTED_COLOR,
						UNSELECTED_COLOR
					],
					// Selected outline comes from orange “Selected clip”; avoid dual-colour border.
					'line-width': [
						'case',
						['==', ['get', 'selected'], 1],
						0,
						2.4
					],
					'line-opacity': 1
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
					'fill-color': CLIP_ACCENT,
					'fill-opacity': 0.14
				}
			});
			map.addLayer({
				id: 'clip-line',
				type: 'line',
				source: CLIP_SOURCE,
				paint: {
					'line-color': CLIP_ACCENT,
					'line-width': 2.75,
					'line-dasharray': [2, 1.25]
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
		const choice = selectedPartId == null ? null : String(selectedPartId);
		(parts || []).forEach((part) => {
			const wid = part?.watershed_id != null ? String(part.watershed_id) : '';
			const selected =
				!choice || choice === 'all' || (wid && wid === choice) ? 1 : 0;
			const f = asFeature(part?.geometry, {
				role: 'part',
				color: selected ? SELECTED_COLOR : UNSELECTED_COLOR,
				selected,
				watershed_id: wid,
				watershed_name: part?.watershed_name ?? ''
			});
			if (f) partFeats.push(f);
		});
		map.getSource(PARTS_SOURCE).setData({
			type: 'FeatureCollection',
			features: partFeats
		});
		if (map.getLayer('parts-fill')) {
			map.setPaintProperty('parts-fill', 'fill-color', [
				'case',
				['==', ['get', 'selected'], 1],
				SELECTED_COLOR,
				UNSELECTED_COLOR
			]);
			map.setPaintProperty('parts-fill', 'fill-opacity', [
				'case',
				['==', ['get', 'selected'], 1],
				0.45,
				0.28
			]);
		}
		if (map.getLayer('parts-line')) {
			map.setPaintProperty('parts-line', 'line-color', [
				'case',
				['==', ['get', 'selected'], 1],
				SELECTED_COLOR,
				UNSELECTED_COLOR
			]);
			map.setPaintProperty('parts-line', 'line-width', [
				'case',
				['==', ['get', 'selected'], 1],
				0,
				2.4
			]);
			map.setPaintProperty('parts-line', 'line-opacity', 1);
		}

		const clipFeat = asFeature(clipGeometry, { role: 'clip' });
		// Always show the active clip AOI; village outline stays separate (grey dashed).
		map.getSource(CLIP_SOURCE).setData({
			type: 'FeatureCollection',
			features: clipFeat ? [clipFeat] : []
		});
		// When micros are drawn, skip clip fill so it does not bury the blue parts
		// (union clip often matches the same polygons). Keep orange outline only.
		if (map.getLayer('clip-fill')) {
			map.setPaintProperty('clip-fill', 'fill-color', CLIP_ACCENT);
			map.setPaintProperty(
				'clip-fill',
				'fill-opacity',
				clipFeat && !partFeats.length ? 0.16 : 0
			);
		}
		if (map.getLayer('clip-line')) {
			map.setPaintProperty('clip-line', 'line-color', CLIP_ACCENT);
			map.setPaintProperty('clip-line', 'line-width', 3);
		}

		const villageFeat = asFeature(villageGeometry, {
			role: 'village',
			name: villageName || 'Village boundary'
		});
		map.getSource(VILLAGE_SOURCE).setData({
			type: 'FeatureCollection',
			features: villageFeat ? [villageFeat] : []
		});

		raiseMicroLayers();

		const bounds = boundsFromGeoms([
			villageGeometry,
			clipGeometry,
			...(parts || []).map((p) => p?.geometry)
		]);
		if (bounds) {
			map.fitBounds(bounds, { padding: 48, maxZoom: 12, duration: 500 });
		}
	}

	/** Keep L12 micros above context / village / clip fills so they stay visible. */
	function raiseMicroLayers() {
		if (!map) return;
		// Base stack: fills first, then lines. Micros near the top.
		for (const id of [
			'village-fill',
			'clip-fill',
			'parts-fill',
			'parts-line',
			'village-line',
			'clip-line'
		]) {
			if (map.getLayer(id)) map.moveLayer(id);
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
		map.getCanvas().style.cursor = interactiveClick ? 'crosshair' : 'default';
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
		selectedPartId;
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
