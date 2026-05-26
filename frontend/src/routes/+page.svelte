<script>
  import { onMount } from 'svelte';

  let map;

  let selectedLat = $state(null);
  let selectedLng = $state(null);

  let watershed = $state(null);

  let marker = null;
  let watershedLayer = null;

  let L;

  onMount(async () => {

    const leaflet = await import('leaflet');

    L = leaflet.default;

    map = L.map('map').setView([12.9, 77.7], 10);

    L.tileLayer(
      'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
      {
        attribution: '&copy; OpenStreetMap contributors'
      }
    ).addTo(map);

    map.on('click', (e) => {

      selectedLat = e.latlng.lat.toFixed(6);
      selectedLng = e.latlng.lng.toFixed(6);

      if (marker) {
        map.removeLayer(marker);
      }

      marker = L.marker([
        selectedLat,
        selectedLng
      ]).addTo(map);

    });

  });

  async function fetchWatershed() {

    if (!selectedLat || !selectedLng) {
      alert('Select a point on the map');
      return;
    }

    try {

      const response = await fetch(
        `http://127.0.0.1:8000/api/watershed/?lat=${selectedLat}&lng=${selectedLng}`
      );

      watershed = await response.json();

      console.log(watershed);

      if (watershedLayer) {
        map.removeLayer(watershedLayer);
      }

      if (watershed.geom) {

        watershedLayer = L.geoJSON(
          watershed.geom
        ).addTo(map);

        map.fitBounds(
          watershedLayer.getBounds()
        );

      }

    } catch (err) {

      console.error(err);

      alert('Failed to fetch watershed');

    }

  }
</script>

<svelte:head>
  <link
    rel="stylesheet"
    href="https://unpkg.com/leaflet/dist/leaflet.css"
  />
</svelte:head>

<div class="h-screen flex flex-col">

  <div class="bg-white shadow p-4 z-[1000]">

    <h1 class="text-2xl font-bold mb-4">
      WELLlabs DDA
    </h1>

    <div class="flex gap-4 items-center flex-wrap">

      <div>
        <strong>Latitude:</strong>
        {selectedLat || '-'}
      </div>

      <div>
        <strong>Longitude:</strong>
        {selectedLng || '-'}
      </div>

      <button
        class="bg-black text-white px-4 py-2 rounded-lg"
        onclick={fetchWatershed}
      >
        Send
      </button>

    </div>

  </div>

  <div
    id="map"
    class="flex-1"
  ></div>

</div>
