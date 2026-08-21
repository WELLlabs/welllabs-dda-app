<script>
	import { onDestroy, onMount } from 'svelte';
	import maplibregl from 'maplibre-gl';
	import 'maplibre-gl/dist/maplibre-gl.css';

	let { lng = $bindable(77.2), lat = $bindable(28.6), onPick } = $props();

	let container;
	let map;
	let marker = null;

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
			placeMarker(lng, lat);
		});

		map.on('click', (e) => {
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
		marker = new maplibregl.Marker({ color: '#1b75e0' })
			.setLngLat([lon, latVal])
			.addTo(map);
	}

	$effect(() => {
		if (map?.isStyleLoaded()) placeMarker(lng, lat);
	});
</script>

<div class="flex h-full flex-col gap-2">
	<p class="m-0 text-sm text-gray-600">Click the map to set the project location.</p>
	<div bind:this={container} class="min-h-[280px] flex-1 rounded-lg border border-gray-200"></div>
	<p class="m-0 text-xs text-gray-500">
		Selected: {lng.toFixed(5)}, {lat.toFixed(5)}
	</p>
</div>
