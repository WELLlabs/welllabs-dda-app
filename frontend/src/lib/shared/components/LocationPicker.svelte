<script>
	import { onDestroy, onMount } from 'svelte';
	import maplibregl from 'maplibre-gl';
	import 'maplibre-gl/dist/maplibre-gl.css';

	/** Distinct fills for individual intersecting basins */
	const PART_COLORS = [
		'#e07a3d',
		'#2a9d8f',
		'#e9c46a',
		'#457b9d',
		'#e76f51',
		'#6a4c93',
		'#43aa8b',
		'#f4a261',
		'#264653',
		'#d62828',
		'#4cc9f0',
		'#90be6d',
		'#f72585',
		'#577590',
		'#b56576'
	];

	/** @type {{
	 *   lng?: number,
	 *   lat?: number,
	 *   onPick?: (p: { lng: number, lat: number }) => void,
	 *   onBounds?: (b: [number, number, number, number]) => void,
	 *   clipGeometry?: object | null,
	 *   villageGeometry?: object | null,
	 *   parts?: Array<{ geometry?: object, watershed_id?: string, watershed_name?: string }> | null,
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
		parts = null,
		interactiveClick = true,
		showMarker = undefined,
		hint = 'Click the map to set the project location.'
	} = $props();

	const markerVisible = $derived(showMarker ?? interactiveClick);

	let container;
	let map;
	let marker = null;
	let styleReady = $state(false);

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

	onDestroy(() => map?.remove());

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
					'fill-color': ['coalesce', ['get', 'color'], '#e07a3d'],
					'fill-opacity': 0.38
				}
			});
			map.addLayer({
				id: 'parts-line',
				type: 'line',
				source: PARTS_SOURCE,
				paint: {
					'line-color': ['coalesce', ['get', 'color'], '#b5523a'],
					'line-width': 1.6,
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
					'fill-color': '#5c2d91',
					'fill-opacity': 0.12
				}
			});
			map.addLayer({
				id: 'village-line',
				type: 'line',
				source: VILLAGE_SOURCE,
				paint: {
					'line-color': '#5c2d91',
					'line-width': 2.8
				}
			});
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

	function syncOverlays() {
		if (!map?.isStyleLoaded() || !styleReady) return;
		ensureOverlayLayers();

		const partFeats = [];
		(parts || []).forEach((part, i) => {
			const color = PART_COLORS[i % PART_COLORS.length];
			const f = asFeature(part?.geometry, {
				role: 'part',
				color,
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

		const villageFeat = asFeature(villageGeometry, { role: 'village' });
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
			map.fitBounds(bounds, { padding: 36, maxZoom: 12, duration: 500 });
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
		for (const g of geoms) {
			if (!g) continue;
			const geom = g.type === 'Feature' ? g.geometry : g.type === 'FeatureCollection' ? null : g;
			if (geom?.coordinates) visit(geom.coordinates);
		}
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
		parts;
		interactiveClick;
		if (styleReady) syncOverlays();
	});
</script>

<div class="flex h-full flex-col gap-2">
	<p class="m-0 text-sm text-gray-600">{hint}</p>
	<div bind:this={container} class="min-h-[280px] flex-1 rounded-lg border border-gray-200"></div>
	{#if markerVisible}
		<p class="m-0 text-xs text-gray-500">
			Selected: {lng.toFixed(5)}, {lat.toFixed(5)}
		</p>
	{/if}
</div>
