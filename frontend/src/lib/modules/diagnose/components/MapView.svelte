<script>
	import { onDestroy, onMount } from 'svelte';
	import maplibregl from 'maplibre-gl';
	import 'maplibre-gl/dist/maplibre-gl.css';

	import {
		createFieldNote,
		createHypothesis,
		createObservationZone,
		deleteFieldNote,
		deleteHypothesis,
		deleteObservationZone,
		fetchCogLayers,
		fetchFieldNotes,
		fetchHypotheses,
		fetchLayerAnalysis,
		fetchBatchLayerAnalysis,
		fetchObservationZones,
		fetchVectorLayers,
		fieldNoteMediaUrl,
		fieldNoteThumbnailUrl,
		updateFieldNote,
		updateHypothesis,
		updateObservationZone
	} from '$lib/modules/diagnose/api';
	import { MAX_FIELD_NOTE_MEDIA_BYTES, OBSERVATION_ZONE_COLOR, FIELD_NOTE_COLOR, HYPOTHESIS_COLOR, ZONE_COLORS } from '$lib/modules/diagnose/map-constants';
	import FieldNoteIcon from '$lib/modules/diagnose/components/icons/FieldNoteIcon.svelte';
	import HypothesisIcon from '$lib/modules/diagnose/components/icons/HypothesisIcon.svelte';
	import ObservationZoneIcon from '$lib/modules/diagnose/components/icons/ObservationZoneIcon.svelte';
	import Terrain3DView from '$lib/modules/diagnose/components/Terrain3DView.svelte';

	const BASE_LAYERS = {
		osm: {
			id: 'base-osm',
			label: 'OpenStreetMap',
			tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
			attribution: '© OpenStreetMap contributors'
		},
		esri: {
			id: 'base-esri',
			label: 'ESRI Imagery',
			tiles: [
				'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
			],
			attribution: '© Esri, Maxar, Earthstar Geographics'
		}
	};

	const UUID_RE =
		/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

	function zoneIdFromFeature(f) {
		const id = String(f.properties?.id ?? '');
		return UUID_RE.test(id) ? id : null;
	}

	/** @param {string} hex */
	function contrastTextColor(hex) {
		const normalized = String(hex || '#000000').replace('#', '');
		if (normalized.length !== 6) return '#ffffff';
		const r = parseInt(normalized.slice(0, 2), 16);
		const g = parseInt(normalized.slice(2, 4), 16);
		const b = parseInt(normalized.slice(4, 6), 16);
		const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
		return luminance > 0.55 ? '#000000' : '#ffffff';
	}

	function closeSelectedZone() {
		selectedZone = null;
		editingSelectedZone = null;
		showSelectedZoneMenu = false;
	}

	function closeSelectedFieldNote() {
		selectedFieldNote = null;
		editingSelectedFieldNote = null;
		showSelectedFieldNoteMenu = false;
		expandedFieldNotePhoto = null;
	}

	function closeSelectedHypothesis() {
		selectedHypothesis = null;
		editingHypothesis = null;
		hypothesisError = '';
		showSelectedHypothesisMenu = false;
	}

	function showOnlySecondaryLayer(layerId) {
		for (const l of secondaryLayers) {
			const visible = l.id === layerId && l.map_render !== false;
			cogVisibility = { ...cogVisibility, [l.id]: visible };
			if (l.kind === 'vector') {
				setLayerVisibility(`vec-${l.id}-fill`, visible);
				setLayerVisibility(`vec-${l.id}-line`, visible);
			} else {
				setLayerVisibility(`cog-${l.id}`, visible);
			}
		}
	}

	async function selectLayer(layer) {
		selectedLayer = layer;
		if (layer?.kind === 'primary') {
			activePrimaryTab = layer.id;
			closeSelectedZone();
			closeSelectedFieldNote();
			closeSelectedHypothesis();
			cancelPendingForms();
			if (layer.id === 'hypotheses') {
				void reloadHypotheses();
			}
		} else if (layer?.kind === 'secondary') {
			if (mapReady) {
				const meta = secondaryLayers.find((l) => l.id === layer.id);
				if (meta?.kind === 'vector' && meta.map_render !== false) {
					await ensureVectorLayerOnMap(meta);
				}
				showOnlySecondaryLayer(layer.id);
			}
		}
	}

	function selectPrimaryTab(id) {
		selectLayer({ kind: 'primary', id });
	}

	function cancelPendingForms() {
		pendingPoint = null;
		pendingZone = null;
		addingFieldNote = false;
		zoneDraw = false;
		noteText = '';
		noteTitle = '';
		notePhoto = undefined;
		noteAudio = undefined;
		if (notePhotoPreview) URL.revokeObjectURL(notePhotoPreview);
		notePhotoPreview = null;
		if (noteAudioPreview) URL.revokeObjectURL(noteAudioPreview);
		noteAudioPreview = null;
		noteMediaError = '';
		noteHypothesisId = '';
		creatingHypothesis = false;
		newHypothesisText = '';
		newHypothesisZoneIds = [];
		zoneText = '';
		zoneObservations = '';
		zoneQuestions = '';
		resetDrawState();
	}

	function isPlacingOnMap() {
		return zoneDraw || (addingFieldNote && !pendingPoint);
	}

	/** Fallback expressions; runtime sizes set from viewport height in updateDrawSizes(). */
	const VERTEX_RADIUS = 11;
	const LINE_WIDTH = 3.5;
	const FIELD_NOTE_PIN_BASE = 1.35;
	const FIELD_NOTE_PIN_FILL = FIELD_NOTE_COLOR;
	let fieldNotePinReady = false;

	function ensureFieldNotePinIcon() {
		if (!map) return Promise.resolve();
		if (fieldNotePinReady) return Promise.resolve();

		const w = 48;
		const h = 62;
		const canvas = document.createElement('canvas');
		canvas.width = w;
		canvas.height = h;
		const ctx = canvas.getContext('2d');
		if (!ctx) return Promise.resolve();

		const cx = w / 2;
		const headY = 18;
		const headR = 15;

		function pinPath() {
			ctx.beginPath();
			ctx.arc(cx, headY, headR, Math.PI, 0, false);
			ctx.lineTo(cx, h - 4);
			ctx.closePath();
		}

		pinPath();
		ctx.fillStyle = FIELD_NOTE_PIN_FILL;
		ctx.fill();

		pinPath();
		ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)';
		ctx.lineWidth = 2;
		ctx.lineJoin = 'round';
		ctx.stroke();

		ctx.beginPath();
		ctx.arc(cx, headY, 5, 0, Math.PI * 2);
		ctx.fillStyle = 'rgba(255, 255, 255, 0.95)';
		ctx.fill();

		if (map.hasImage('field-note-pin')) map.removeImage('field-note-pin');
		map.addImage('field-note-pin', ctx.getImageData(0, 0, w, h), { pixelRatio: 2 });
		fieldNotePinReady = true;
		return Promise.resolve();
	}

	let lastHoverPoint = null;

	function markerRadiusPx() {
		if (!map) return VERTEX_RADIUS;
		const h = map.getContainer().clientHeight || 700;
		return Math.max(10, Math.round(h * 0.032 * 0.7));
	}

	function lineWidthPx() {
		if (!map) return LINE_WIDTH;
		const h = map.getContainer().clientHeight || 700;
		return Math.max(3, h * 0.007 * 0.7);
	}

	function fieldNotePinSize() {
		return Math.max(0.75, (markerRadiusPx() / VERTEX_RADIUS) * FIELD_NOTE_PIN_BASE);
	}

	function clickableFeatureLayers() {
		if (zoneDraw || pendingZone || addingFieldNote) return [];
		if (activePrimaryTab === 'observation-zones' && showZonesLayer) {
			return ['zones-fill', 'zones-line', 'zones-label'];
		}
		if (activePrimaryTab === 'field-notes' && showFieldNotesLayer) {
			return ['field-notes-point'];
		}
		return [];
	}

	function isOverClickableFeature(point) {
		if (!mapReady || !map || !point) return false;
		const layers = clickableFeatureLayers();
		if (!layers.length) return false;
		const hit = map.queryRenderedFeatures(point, { layers });
		for (const f of hit) {
			if (activePrimaryTab === 'observation-zones') {
				if (zoneIdFromFeature(f)) return true;
			} else if (activePrimaryTab === 'field-notes') {
				const id = String(f.properties?.id ?? f.id ?? '');
				if (UUID_RE.test(id)) return true;
			}
		}
		return false;
	}

	function updateMapCursor(point = lastHoverPoint) {
		if (!mapReady || !map) return;
		const canvas = map.getCanvas();
		if (isPlacingOnMap()) {
			canvas.style.cursor = dragVertexIndex !== null ? 'grabbing' : 'crosshair';
			return;
		}
		if (zoneDraw || pendingZone || addingFieldNote) {
			canvas.style.cursor = '';
			return;
		}
		if (point && isOverClickableFeature(point)) {
			canvas.style.cursor = 'pointer';
			return;
		}
		canvas.style.cursor = '';
	}

	function hitTolerancePx() {
		return markerRadiusPx() * 1.4;
	}

	function updateDrawSizes() {
		if (!mapReady) return;
		const r = markerRadiusPx();
		const w = lineWidthPx();
		const stroke = Math.max(1.5, r * 0.14);
		if (map.getLayer('draw-preview-vertices')) {
			map.setPaintProperty('draw-preview-vertices', 'circle-radius', r);
			map.setPaintProperty('draw-preview-vertices', 'circle-stroke-width', stroke);
		}
		if (map.getLayer('field-notes-point')) {
			map.setLayoutProperty('field-notes-point', 'icon-size', fieldNotePinSize());
		}
		if (map.getLayer('draw-preview-field-note')) {
			map.setLayoutProperty('draw-preview-field-note', 'icon-size', fieldNotePinSize());
		}
		for (const id of ['draw-preview-line', 'draw-preview-dash', 'zones-line']) {
			if (map.getLayer(id)) map.setPaintProperty(id, 'line-width', w);
		}
	}

	function ensureDrawPreviewOnTop() {
		if (!mapReady) return;
		for (const id of [
			'draw-preview-fill',
			'draw-preview-line',
			'draw-preview-dash',
			'draw-preview-vertices',
			'draw-preview-field-note'
		]) {
			if (map.getLayer(id)) map.moveLayer(id);
		}
	}

	let { project, refreshKey = 0 } = $props();

	const watershedBounds = $derived(project?.bounds ?? null);

	function cogTileUrl(layerId) {
		const params = new URLSearchParams();
		params.set('project_id', project.id);
		return `/api/diagnose/layers/cog/${layerId}/tiles/WebMercatorQuad/{z}/{x}/{y}?${params.toString()}`;
	}

	function removeCogLayers() {
		if (!map) return;
		for (const layer of cogLayers) {
			const layerId = `cog-${layer.id}`;
			if (map.getLayer(layerId)) map.removeLayer(layerId);
			if (map.getSource(layerId)) map.removeSource(layerId);
		}
		for (const styleLayer of map.getStyle().layers ?? []) {
			if (!styleLayer.id.startsWith('cog-')) continue;
			if (map.getLayer(styleLayer.id)) map.removeLayer(styleLayer.id);
			if (map.getSource(styleLayer.id)) map.removeSource(styleLayer.id);
		}
	}

	function removeVectorLayers() {
		if (!map) return;
		for (const layer of vectorLayers) {
			const fillId = `vec-${layer.id}-fill`;
			const lineId = `vec-${layer.id}-line`;
			const sourceId = `vec-${layer.id}`;
			if (map.getLayer(lineId)) map.removeLayer(lineId);
			if (map.getLayer(fillId)) map.removeLayer(fillId);
			if (map.getSource(sourceId)) map.removeSource(sourceId);
		}
	}

	function rebuildSecondaryList(cogs, vectors) {
		return [
			...cogs.map((l) => ({ ...l, kind: 'cog' })),
			...vectors.map((l) => ({ ...l, kind: 'vector' }))
		];
	}

	function matchColorExpression(column, classes, fallback = '#e6e9eb') {
		const expr = ['match', ['to-string', ['get', column]]];
		for (const c of classes || []) {
			if (c.value == null) continue;
			expr.push(String(c.value), c.color);
		}
		expr.push(fallback);
		return expr;
	}

	function stepColorExpression(column, stops, fallback = '#e6e9eb') {
		const sorted = [...(stops || [])].sort((a, b) => a.min - b.min);
		if (!sorted.length) return fallback;
		const expr = ['step', ['to-number', ['get', column]], sorted[0].color];
		for (let i = 1; i < sorted.length; i++) {
			expr.push(sorted[i].min, sorted[i].color);
		}
		return expr;
	}

	function vectorFillColor(layer) {
		const column = layer.style_column;
		if (!column) return '#94a3b8';
		if (layer.render_type === 'choropleth') {
			return stepColorExpression(column, layer.choropleth_stops);
		}
		return matchColorExpression(column, layer.legend);
	}

	/** Legend entries actually present in watershed features (or full for COG). */
	function legendFromFeatures(layer, features) {
		if (!layer) return [];
		if (layer.render_type === 'continuous') {
			// gist_earth gradient: dark-green (low) → brown (mid) → off-white (high)
			return [
				{ label: 'Lower elevation', color: '#2a4a1e', continuous: true },
				{ label: 'Mid elevation', color: '#8c6d3f', continuous: true },
				{ label: 'Higher elevation', color: '#e8e0d0', continuous: true }
			];
		}
		if (layer.kind === 'cog' || !features?.length) {
			return layer.legend || [];
		}
		const column = layer.style_column;
		if (layer.render_type === 'choropleth' && layer.choropleth_stops?.length) {
			const nums = features
				.map((f) => Number(f.properties?.[column]))
				.filter((n) => Number.isFinite(n));
			return (layer.choropleth_stops || []).filter((s) =>
				nums.some((n) => n >= s.min && n < s.max)
			);
		}
		const present = new Set(
			features
				.map((f) => f.properties?.[column])
				.filter((v) => v != null && v !== '')
				.map((v) => String(v))
		);
		return (layer.legend || []).filter((item) => present.has(String(item.value)));
	}

	const mapLegendItems = $derived.by(() => {
		if (selectedLayer?.kind !== 'secondary') return [];
		const layer = secondaryLayers.find((l) => l.id === selectedLayer.id);
		if (!layer) return [];
		return layerActiveLegend[layer.id] || layer.legend || [];
	});

	let container;
	let map;
	let noteTitle = $state('');
	let noteText = $state('');
	let notePhoto = $state(undefined);
	let noteAudio = $state(undefined);
	let notePhotoPreview = $state(null);
	let noteAudioPreview = $state(null);
	let noteMediaError = $state('');
	let pendingPoint = $state(null);
	let status = $state('Loading map…');

	let baseLayer = $state('osm');
	/** @type {'flat' | '3d'} */
	let mapMode = $state('flat');
	const activeAttribution = $derived(
		baseLayer === 'osm' ? BASE_LAYERS.osm.attribution : BASE_LAYERS.esri.attribution
	);
	let selectedLayer = $state(null);
	let addingFieldNote = $state(false);
	let showZonesLayer = $state(true);
	let showFieldNotesLayer = $state(true);
	let mapReady = $state(false);
	let cogLayers = $state([]);
	let vectorLayers = $state([]);
	let secondaryLayers = $state([]);
	let cogVisibility = $state({});
	let layerAnalysis = $state({});
	let layerAnalysisLoading = $state({});
	/** @type {Record<string, Array<{value?: any, label: string, color: string, continuous?: boolean}>>} */
	let layerActiveLegend = $state({});
	let analysisPreloadDone = $state(false);
	let primaryLayerOrder = $state(['observation-zones', 'hypotheses', 'field-notes']);
	let sidebarWidth = $state(280);
	let sidebarResizing = $state(false);
	let rightSidebarWidth = $state(360);
	let rightSidebarResizing = $state(false);
	let activePrimaryTab = $state('observation-zones');
	/** @type {{ category: 'secondary' | 'primary' | null, index: number | null }} */
	let dragReorder = $state({ category: null, index: null });
	/** @type {number | null} */
	let dragOverIndex = $state(null);

	const PRIMARY_LAYER_LABELS = {
		'observation-zones': 'Observation zones',
		'hypotheses': 'Hypotheses',
		'field-notes': 'Field notes'
	};

	const HYPOTHESIS_STATUS_LABELS = {
		untested: 'Untested',
		validated: 'Validated',
		invalidated: 'Invalidated',
		discarded: 'Discarded'
	};

	let zoneDraw = $state(false);
	let drawCoords = $state([]);
	let cursorLngLat = $state(null);
	let dragVertexIndex = $state(null);
	let pendingZone = $state(null);
	let zoneText = $state('');
	let zoneObservations = $state('');
	let zoneQuestions = $state('');
	let zoneColor = $state(OBSERVATION_ZONE_COLOR);
	let savingZone = $state(false);
	let selectedZone = $state(null);
	let editingSelectedZone = $state(null);
	let savedZones = $state([]);
	let savedFieldNotes = $state([]);
	let hypotheses = $state([]);
	let creatingHypothesis = $state(false);
	let newHypothesisText = $state('');
	let newHypothesisZoneIds = $state([]);
	let selectedHypothesis = $state(null);
	let editingHypothesis = $state(null);
	let savingHypothesis = $state(false);
	let hypothesisError = $state('');
	let noteHypothesisId = $state('');
	let selectedFieldNote = $state(null);
	let editingSelectedFieldNote = $state(null);
	let showSelectedZoneMenu = $state(false);
	let showSelectedFieldNoteMenu = $state(false);
	let showSelectedHypothesisMenu = $state(false);
	let savingFieldNote = $state(false);
	/** @type {string | null} */
	let expandedFieldNotePhoto = $state(null);

	$effect(() => {
		if (!expandedFieldNotePhoto) return;
		function onKey(e) {
			if (e.key === 'Escape') expandedFieldNotePhoto = null;
		}
		window.addEventListener('keydown', onKey);
		return () => window.removeEventListener('keydown', onKey);
	});

	let lastTapTime = 0;
	let lastTapIndex = -1;
	let didDrag = false;

	onMount(async () => {
		map = new maplibregl.Map({
			container,
			style: {
				version: 8,
				sources: {
					[BASE_LAYERS.osm.id]: {
						type: 'raster',
						tiles: [...BASE_LAYERS.osm.tiles],
						tileSize: 256
					},
					[BASE_LAYERS.esri.id]: {
						type: 'raster',
						tiles: [...BASE_LAYERS.esri.tiles],
						tileSize: 256
					}
				},
				layers: [
					{
						id: BASE_LAYERS.osm.id,
						type: 'raster',
						source: BASE_LAYERS.osm.id,
						layout: { visibility: 'visible' }
					},
					{
						id: BASE_LAYERS.esri.id,
						type: 'raster',
						source: BASE_LAYERS.esri.id,
						layout: { visibility: 'none' }
					}
				]
			},
			center: [0, 20],
			zoom: 2
		});

		map.addControl(new maplibregl.NavigationControl(), 'top-left');

		map.on('load', async () => {
			mapReady = true;
			map.setPitch(0);
			map.setBearing(0);
			map.setMaxBounds(null);
			applyBasemapVisibility(BASE_LAYERS.osm.id, baseLayer === 'osm');
			applyBasemapVisibility(BASE_LAYERS.esri.id, baseLayer === 'esri');
			await ensureFieldNotePinIcon();
			loadWatershedBoundary();
			initDrawPreview();
			updateDrawSizes();
			ensureDrawPreviewOnTop();
			try {
				await loadCogLayers();
				await loadVectorLayers();
				await preloadAllSecondaryData();
			} catch (err) {
				status = `Layers unavailable: ${err instanceof Error ? err.message : String(err)}`;
			}
			try {
				await reloadObservationZones();
			} catch (err) {
				console.error('Failed to load observation zones', err);
				status = `Could not load observation zones: ${err instanceof Error ? err.message : String(err)}`;
			}
			try {
				await reloadFieldNotes();
			} catch (err) {
				console.error('Failed to load field notes', err);
				status = `Could not load field notes: ${err instanceof Error ? err.message : String(err)}`;
			}
			try {
				await reloadHypotheses();
			} catch (err) {
				console.error('Failed to load hypotheses', err);
				status = `Could not load hypotheses: ${err instanceof Error ? err.message : String(err)}`;
			}
			if (secondaryLayers.length > 0) {
				await selectLayer({ kind: 'secondary', id: secondaryLayers[0].id });
			} else {
				await selectLayer({ kind: 'primary', id: 'observation-zones' });
			}
			ensureDrawPreviewOnTop();
			status =
				status.startsWith('Layers unavailable') || status.startsWith('Could not load')
					? status
					: 'Ready';
			requestAnimationFrame(() => map?.resize());
		});

		map.on('zoom', () => {
			updateDrawSizes();
			setDrawPreviewFromState();
		});
		map.on('resize', updateDrawSizes);

		const resizeObserver = new ResizeObserver(() => map?.resize());
		resizeObserver.observe(container);
		onDestroy(() => resizeObserver.disconnect());

		window.addEventListener('mousemove', onSidebarResizeMove);
		window.addEventListener('mouseup', onSidebarResizeEnd);
		window.addEventListener('mousemove', onRightSidebarResizeMove);
		window.addEventListener('mouseup', onRightSidebarResizeEnd);
		onDestroy(() => {
			window.removeEventListener('mousemove', onSidebarResizeMove);
			window.removeEventListener('mouseup', onSidebarResizeEnd);
			window.removeEventListener('mousemove', onRightSidebarResizeMove);
			window.removeEventListener('mouseup', onRightSidebarResizeEnd);
		});

		map.on('click', onMapClick);
		map.on('dblclick', onMapDblClick);
		map.on('mousedown', onMapMouseDown);
		map.on('mousemove', onMapMouseMove);
		map.on('mouseup', onMapMouseUp);
		map.on('mouseleave', () => {
			lastHoverPoint = null;
			updateMapCursor();
		});
	});

	onDestroy(() => {
		fieldNotePinReady = false;
		map?.remove();
	});

	$effect(() => {
		void sidebarWidth;
		void rightSidebarWidth;
		if (mapReady) requestAnimationFrame(() => map?.resize());
	});

	$effect(() => {
		if (!mapReady) return;
		void zoneDraw;
		void pendingZone;
		void addingFieldNote;
		void pendingPoint;
		void drawCoords.length;
		void cursorLngLat;
		void dragVertexIndex;
		void zoneColor;
		void activePrimaryTab;
		void selectedLayer;
		void showZonesLayer;
		void showFieldNotesLayer;

		if (zoneDraw || pendingZone) {
			map.doubleClickZoom.disable();
		} else {
			map.doubleClickZoom.enable();
		}

		updateMapCursor();

		updatePreviewColor(zoneColor);
		updateDrawPreview();
		ensureDrawPreviewOnTop();
	});

	$effect(() => {
		if (!mapReady) return;
		applyBasemapVisibility(BASE_LAYERS.osm.id, baseLayer === 'osm');
		applyBasemapVisibility(BASE_LAYERS.esri.id, baseLayer === 'esri');
	});

	$effect(() => {
		if (!mapReady || !refreshKey) return;
		void refreshKey;
		void (async () => {
			try {
				await reloadObservationZones();
			} catch (err) {
				console.error('Failed to refresh observation zones', err);
				status = `Could not load observation zones: ${err instanceof Error ? err.message : String(err)}`;
			}
			try {
				await reloadFieldNotes();
			} catch (err) {
				console.error('Failed to refresh field notes', err);
				status = `Could not load field notes: ${err instanceof Error ? err.message : String(err)}`;
			}
			try {
				await reloadHypotheses();
			} catch (err) {
				console.error('Failed to refresh hypotheses', err);
				status = `Could not load hypotheses: ${err instanceof Error ? err.message : String(err)}`;
			}
		})();
	});

	function updatePreviewColor(color) {
		if (!mapReady) return;
		if (map.getLayer('draw-preview-fill')) {
			map.setPaintProperty('draw-preview-fill', 'fill-color', color);
			map.setPaintProperty('draw-preview-fill', 'fill-opacity', 0.35);
			map.setPaintProperty('draw-preview-line', 'line-color', color);
			map.setPaintProperty('draw-preview-dash', 'line-color', color);
			map.setPaintProperty('draw-preview-vertices', 'circle-color', color);
		}
	}

	function screenPoint(lngLat) {
		const p = map.project(lngLat);
		if (Array.isArray(p)) return { x: p[0], y: p[1] };
		return { x: p.x, y: p.y };
	}

	function findVertexIndex(e, coords) {
		for (let i = 0; i < coords.length; i++) {
			const p = screenPoint(coords[i]);
			const dx = p.x - e.point.x;
			const dy = p.y - e.point.y;
			if (Math.sqrt(dx * dx + dy * dy) <= hitTolerancePx()) return i;
		}
		return null;
	}

	function isNearPoint(e, pt) {
		const p = screenPoint(pt);
		const dx = p.x - e.point.x;
		const dy = p.y - e.point.y;
		return Math.sqrt(dx * dx + dy * dy) <= hitTolerancePx();
	}

	function activeCoords() {
		if (pendingZone?.coords) return pendingZone.coords;
		return drawCoords;
	}

	function polygonFromCoords(coords) {
		return { type: 'Polygon', coordinates: [[...coords, coords[0]]] };
	}

	function initDrawPreview() {
		if (!map || map.getSource('draw-preview')) return;
		map.addSource('draw-preview', {
			type: 'geojson',
			data: { type: 'FeatureCollection', features: [] }
		});
		map.addLayer({
			id: 'draw-preview-fill',
			type: 'fill',
			source: 'draw-preview',
			filter: ['==', ['get', 'kind'], 'fill'],
			paint: { 'fill-color': '#f59e0b', 'fill-opacity': 0.5 }
		});
		map.addLayer({
			id: 'draw-preview-line',
			type: 'line',
			source: 'draw-preview',
			filter: ['==', ['get', 'kind'], 'line'],
			paint: { 'line-color': '#d97706', 'line-width': LINE_WIDTH }
		});
		map.addLayer({
			id: 'draw-preview-dash',
			type: 'line',
			source: 'draw-preview',
			filter: ['==', ['get', 'kind'], 'dash'],
			paint: {
				'line-color': '#ea580c',
				'line-width': LINE_WIDTH,
				'line-dasharray': [2, 2]
			}
		});
		map.addLayer({
			id: 'draw-preview-vertices',
			type: 'circle',
			source: 'draw-preview',
			filter: ['==', ['get', 'kind'], 'vertex'],
			paint: {
				'circle-radius': VERTEX_RADIUS,
				'circle-color': '#ea580c',
				'circle-stroke-width': 2,
				'circle-stroke-color': '#ffffff'
			}
		});
		map.addLayer({
			id: 'draw-preview-field-note',
			type: 'symbol',
			source: 'draw-preview',
			filter: ['==', ['get', 'kind'], 'field-note'],
			layout: {
				'icon-image': 'field-note-pin',
				'icon-size': fieldNotePinSize(),
				'icon-anchor': 'bottom',
				'icon-allow-overlap': true
			}
		});
	}

	function updateDrawPreview() {
		if (!mapReady || !map) return;
		initDrawPreview();
		if (!map.getSource('draw-preview')) return;
		const features = [];

		const coords = activeCoords();
		for (const c of coords) {
			features.push({
				type: 'Feature',
				properties: { kind: 'vertex' },
				geometry: { type: 'Point', coordinates: c }
			});
		}

		const drawing = zoneDraw;
		const cursor = drawing ? cursorLngLat : null;

		const ring = cursor && drawing ? [...coords, cursor] : [...coords];
		if (ring.length >= 2) {
			features.push({
				type: 'Feature',
				properties: { kind: 'line' },
				geometry: { type: 'LineString', coordinates: [...ring, ring[0]] }
			});
		}
		if (ring.length >= 3) {
			features.push({
				type: 'Feature',
				properties: { kind: 'fill' },
				geometry: { type: 'Polygon', coordinates: [[...ring, ring[0]]] }
			});
		}
		if (drawing && cursor && coords.length >= 1) {
			features.push({
				type: 'Feature',
				properties: { kind: 'dash' },
				geometry: { type: 'LineString', coordinates: [coords[coords.length - 1], cursor] }
			});
		}

		if (pendingPoint) {
			features.push({
				type: 'Feature',
				properties: { kind: 'field-note' },
				geometry: { type: 'Point', coordinates: pendingPoint }
			});
		}

		map.getSource('draw-preview').setData({
			type: 'FeatureCollection',
			features
		});
	}

	function setDrawPreviewFromState() {
		updateDrawPreview();
	}

	function finishPolygon(coords) {
		if (coords.length < 3) return;
		const ring = [...coords, coords[0]];
		pendingZone = {
			geometry: { type: 'Polygon', coordinates: [ring] },
			coords: [...coords]
		};
		zoneDraw = false;
		drawCoords = [];
		cursorLngLat = null;
		zoneObservations = '';
		zoneQuestions = '';
		status = 'Enter title, observations, and questions — drag vertices to adjust';
		setDrawPreviewFromState();
	}

	function onMapMouseDown(e) {
		if (pendingZone?.coords) {
			const idx = findVertexIndex(e, pendingZone.coords);
			if (idx !== null) {
				dragVertexIndex = idx;
				return;
			}
		}
		if (zoneDraw) {
			const idx = findVertexIndex(e, drawCoords);
			if (idx !== null) dragVertexIndex = idx;
		}
	}

	function onMapClick(e) {
		if (didDrag) {
			didDrag = false;
			return;
		}

		if (!zoneDraw && !pendingZone && !addingFieldNote) {
			if (activePrimaryTab === 'observation-zones') {
				const hit = map.queryRenderedFeatures(e.point, {
					layers: ['zones-fill', 'zones-line', 'zones-label']
				});
				if (hit.length > 0) {
					const f = hit[0];
					const id = zoneIdFromFeature(f);
					if (id) {
						editingSelectedZone = null;
						showSelectedZoneMenu = false;
						selectedZone = {
							id,
							text: String(f.properties?.text ?? ''),
							observations: String(f.properties?.observations ?? ''),
							questions: String(f.properties?.questions ?? ''),
							color: String(f.properties?.color ?? OBSERVATION_ZONE_COLOR)
						};
						closeSelectedFieldNote();
						status = 'Observation zone selected';
						return;
					}
				}
				closeSelectedZone();
			} else if (activePrimaryTab === 'field-notes') {
				const hit = map.queryRenderedFeatures(e.point, {
					layers: ['field-notes-point']
				});
				if (hit.length > 0) {
					const f = hit[0];
					const id = String(f.properties?.id ?? f.id ?? '');
					if (UUID_RE.test(id)) {
						showSelectedFieldNoteMenu = false;
						editingSelectedFieldNote = null;
						selectedFieldNote = {
							id,
							title: String(f.properties?.title ?? ''),
							text: String(f.properties?.text ?? ''),
							photo_path: f.properties?.photo_path ?? null,
							audio_path: f.properties?.audio_path ?? null,
							hypothesis_id: f.properties?.hypothesis_id ?? null,
							created_at: f.properties?.created_at ?? ''
						};
					closeSelectedZone();
					status = 'Field note selected';
						return;
					}
				}
				closeSelectedFieldNote();
			}
		}

		if (addingFieldNote && !zoneDraw && !pendingZone) {
			pendingPoint = [e.lngLat.lng, e.lngLat.lat];
			setDrawPreviewFromState();
			status = 'Add text and optional media, then save';
			return;
		}

		const lngLat = [e.lngLat.lng, e.lngLat.lat];

		if (!zoneDraw) return;

		drawCoords = [...drawCoords, lngLat];
		setDrawPreviewFromState();
		status = `Polygon: ${drawCoords.length} point(s) — double-click last point to finish`;
	}

	function onMapDblClick(e) {
		e.preventDefault();
		if (zoneDraw && drawCoords.length >= 3) {
			const last = drawCoords[drawCoords.length - 1];
			if (isNearPoint(e, last)) {
				finishPolygon(drawCoords);
			}
		}
	}

	function onMapMouseMove(e) {
		const lngLat = [e.lngLat.lng, e.lngLat.lat];

		if (dragVertexIndex !== null) {
			didDrag = true;
			if (pendingZone?.coords) {
				const coords = [...pendingZone.coords];
				coords[dragVertexIndex] = lngLat;
				pendingZone = {
					...pendingZone,
					coords,
					geometry: polygonFromCoords(coords)
				};
			} else {
				const coords = [...drawCoords];
				coords[dragVertexIndex] = lngLat;
				drawCoords = coords;
			}
			setDrawPreviewFromState();
			return;
		}

		if (zoneDraw) {
			cursorLngLat = lngLat;
			setDrawPreviewFromState();
		}

		if (!dragVertexIndex && !zoneDraw) {
			lastHoverPoint = e.point;
			updateMapCursor(e.point);
		}
	}

	function onMapMouseUp() {
		dragVertexIndex = null;
	}

	function firstOverlayLayerId() {
		for (const layer of map.getStyle().layers ?? []) {
			if (
				layer.id.startsWith('cog-') ||
				layer.id.startsWith('vec-') ||
				layer.id.startsWith('zones-') ||
				layer.id.startsWith('field-notes-')
			) {
				return layer.id;
			}
		}
		return undefined;
	}

	function applyBasemapVisibility(layerId, visible) {
		if (!mapReady || !map.getLayer(layerId)) return;
		map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none');
		if (visible) {
			const before = firstOverlayLayerId();
			if (before) map.moveLayer(layerId, before);
		}
	}

	function setBaseLayer(id) {
		baseLayer = id;
		applyBasemapVisibility(BASE_LAYERS.osm.id, id === 'osm');
		applyBasemapVisibility(BASE_LAYERS.esri.id, id === 'esri');
	}

	function toggleOsm(visible) {
		if (visible) setBaseLayer('osm');
	}

	function toggleEsri(visible) {
		if (visible) setBaseLayer('esri');
	}

	function setLayerVisibility(layerId, visible) {
		if (!map.getLayer(layerId)) return;
		map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none');
	}

	function toggleZonesLayer(visible) {
		showZonesLayer = visible;
		for (const id of ['zones-fill', 'zones-line', 'zones-label']) {
			setLayerVisibility(id, visible);
		}
	}

	function toggleFieldNotesLayer(visible) {
		showFieldNotesLayer = visible;
		setLayerVisibility('field-notes-point', visible);
	}

	function ensureCogAboveBasemaps() {
		applyLayerStackOrder();
	}

	function applyLayerStackOrder() {
		if (!mapReady) return;
		for (const layer of secondaryLayers) {
			if (layer.kind === 'cog') {
				const id = `cog-${layer.id}`;
				if (map.getLayer(id)) map.moveLayer(id);
			} else {
				const fillId = `vec-${layer.id}-fill`;
				const lineId = `vec-${layer.id}-line`;
				if (map.getLayer(fillId)) map.moveLayer(fillId);
				if (map.getLayer(lineId)) map.moveLayer(lineId);
			}
		}
		if (map.getLayer('watershed-fill')) map.moveLayer('watershed-fill');
		if (map.getLayer('watershed-line')) map.moveLayer('watershed-line');
		for (const key of primaryLayerOrder) {
			if (key === 'hypotheses') continue;
			const ids =
				key === 'observation-zones'
					? ['zones-fill', 'zones-line', 'zones-label']
					: ['field-notes-point'];
			for (const id of ids) {
				if (map.getLayer(id)) map.moveLayer(id);
			}
		}
		ensureDrawPreviewOnTop();
	}

	function reorderList(list, from, to) {
		const copy = [...list];
		const [item] = copy.splice(from, 1);
		copy.splice(to, 0, item);
		return copy;
	}

	function startLayerDrag(category, index, e) {
		dragReorder = { category, index };
		dragOverIndex = index;
		e.dataTransfer.effectAllowed = 'move';
		e.dataTransfer.setData('text/plain', `${category}:${index}`);
	}

	function onLayerDragOver(e) {
		e.preventDefault();
		e.dataTransfer.dropEffect = 'move';
	}

	/** Live-reorder so the whole row slides as you drag over siblings. */
	function onLayerDragEnter(category, targetIndex, e) {
		e.preventDefault();
		const { category: srcCategory, index: srcIndex } = dragReorder;
		if (srcCategory !== category || srcIndex === null || srcIndex === targetIndex) {
			dragOverIndex = targetIndex;
			return;
		}
		if (category === 'secondary') {
			secondaryLayers = reorderList(secondaryLayers, srcIndex, targetIndex);
		} else {
			primaryLayerOrder = reorderList(primaryLayerOrder, srcIndex, targetIndex);
		}
		dragReorder = { category, index: targetIndex };
		dragOverIndex = targetIndex;
		applyLayerStackOrder();
	}

	function onLayerDrop(category, targetIndex, e) {
		e.preventDefault();
		e.stopPropagation();
		const { category: srcCategory, index: srcIndex } = dragReorder;
		if (srcCategory === category && srcIndex !== null && srcIndex !== targetIndex) {
			if (category === 'secondary') {
				secondaryLayers = reorderList(secondaryLayers, srcIndex, targetIndex);
			} else {
				primaryLayerOrder = reorderList(primaryLayerOrder, srcIndex, targetIndex);
			}
			applyLayerStackOrder();
		}
		endLayerDrag();
	}

	function endLayerDrag() {
		dragReorder = { category: null, index: null };
		dragOverIndex = null;
	}

	function onRowDragStart(category, index, e) {
		// Don't start a row drag from the visibility toggle
		const t = e.target;
		if (t instanceof Element && t.closest('[data-no-drag]')) {
			e.preventDefault();
			return;
		}
		startLayerDrag(category, index, e);
	}

	function onSidebarResizeStart(e) {
		sidebarResizing = true;
		e.preventDefault();
	}

	function onSidebarResizeMove(e) {
		if (!sidebarResizing) return;
		sidebarWidth = Math.min(480, Math.max(200, e.clientX));
	}

	function onSidebarResizeEnd() {
		sidebarResizing = false;
	}

	function onRightSidebarResizeStart(e) {
		rightSidebarResizing = true;
		e.preventDefault();
	}

	function onRightSidebarResizeMove(e) {
		if (!rightSidebarResizing) return;
		rightSidebarWidth = Math.min(480, Math.max(280, window.innerWidth - e.clientX));
	}

	function onRightSidebarResizeEnd() {
		rightSidebarResizing = false;
	}

	function resetDrawState() {
		drawCoords = [];
		cursorLngLat = null;
		dragVertexIndex = null;
		lastTapTime = 0;
		lastTapIndex = -1;
		setDrawPreviewFromState();
	}

	function startObservationZoneDraw() {
		cancelPendingForms();
		activePrimaryTab = 'observation-zones';
		selectedLayer = { kind: 'primary', id: 'observation-zones' };
		closeSelectedZone();
		closeSelectedFieldNote();
		closeSelectedHypothesis();
		initDrawPreview();
		zoneDraw = true;
		zoneColor = OBSERVATION_ZONE_COLOR;
		ensureDrawPreviewOnTop();
		updateDrawSizes();
		setDrawPreviewFromState();
		map?.doubleClickZoom.disable();
		status = 'Click corners — double-click last point to finish';
	}

	function startFieldNoteAdd() {
		cancelPendingForms();
		selectPrimaryTab('field-notes');
		addingFieldNote = true;
		void reloadHypotheses();
		status = 'Click the map to place the field note';
	}

	function cancelZoneDraw() {
		zoneDraw = false;
		resetDrawState();
		if (!pendingZone) status = 'Ready';
	}

	async function loadCogLayers() {
		try {
			removeCogLayers();
			const { cog_layers } = await fetchCogLayers(watershedBounds, project.id);
			cogLayers = cog_layers;
			secondaryLayers = rebuildSecondaryList(cogLayers, vectorLayers);
			if (cog_layers.length === 0 && vectorLayers.length === 0) {
				status = 'No secondary layers configured (set COG_LAYERS / VECTOR_LAYERS in .env)';
				return;
			}
		for (const layer of cog_layers) {
			if (layer.status === 'error') {
				status = `${layer.name} error: ${layer.error ?? 'unknown'}`;
				cogVisibility = { ...cogVisibility, [layer.id]: false };
				continue;
			}
			cogVisibility = { ...cogVisibility, [layer.id]: false };
			const sourceId = `cog-${layer.id}`;
			const tileUrl = cogTileUrl(layer.id);
			map.addSource(sourceId, {
				type: 'raster',
				tiles: [tileUrl],
				tileSize: 256,
				minzoom: 7,
				maxzoom: 14,
				...(watershedBounds ? { bounds: watershedBounds } : {})
			});
			const beforeId = map.getLayer('watershed-fill') ? 'watershed-fill' : undefined;
			map.addLayer(
				{
					id: sourceId,
					type: 'raster',
					source: sourceId,
					layout: { visibility: 'none' },
					paint: { 'raster-opacity': 0.85 }
				},
				beforeId
			);
		}
			ensureCogAboveBasemaps();
			ensureDrawPreviewOnTop();
			fitToWatershed();
		} catch (err) {
			status = `Raster layers unavailable: ${err instanceof Error ? err.message : String(err)}`;
		}
	}

	function enrichVillageProperties(features, needPctScst) {
		if (!needPctScst) return features;
		return features.map((f) => {
			const p = { ...(f.properties || {}) };
			if (p.pct_scst == null || p.pct_scst === '') {
				const pop = Number(p.Total_Popu ?? p.total_popu ?? 0);
				const sc = Number(p.Total_SC_P ?? p.total_sc_p ?? 0);
				const st = Number(p.Total_ST_P ?? p.total_st_p ?? 0);
				p.pct_scst = pop > 0 ? ((sc + st) / pop) * 100 : 0;
			}
			return { ...f, properties: p };
		});
	}

	const GW_NORMALIZE = {
		safe: 'Safe',
		'semi-critical': 'Semi-critical',
		semicritical: 'Semi-critical',
		'semi critical': 'Semi-critical',
		critical: 'Critical',
		'over-exploited': 'Over-exploited',
		overexploited: 'Over-exploited',
		'over exploited': 'Over-exploited',
		oe: 'Over-exploited',
		saline: 'Saline'
	};

	const RANK_NORMALIZE = {
		'very low': 'Very low',
		verylow: 'Very low',
		low: 'Low',
		moderate: 'Moderate',
		medium: 'Moderate',
		high: 'High',
		'very high': 'Very high',
		veryhigh: 'Very high',
		na: 'NA',
		'n/a': 'NA',
		none: 'NA'
	};

	function pickProp(props, candidates) {
		const keys = Object.keys(props || {});
		const lower = Object.fromEntries(keys.map((k) => [k.toLowerCase(), k]));
		for (const c of candidates) {
			if (c && lower[c.toLowerCase()]) return props[lower[c.toLowerCase()]];
		}
		for (const k of keys) {
			const lk = k.toLowerCase();
			if (candidates.some((c) => c && lk.includes(String(c).toLowerCase()))) {
				return props[k];
			}
		}
		return undefined;
	}

	/** Normalize raw GPKG columns into the style_column expected by layers.yaml. */
	function normalizeVectorFeatures(features, layer) {
		const column = layer.style_column;
		if (!column || !features?.length) return features;
		const atype = layer.analysis_type;

		return features.map((f) => {
			const p = { ...(f.properties || {}) };
			if (p[column] != null && p[column] !== '') {
				return { ...f, properties: p };
			}

			if (atype === 'wiser_gw_stress') {
				const raw = pickProp(p, [
					'__wiser_gw_stress_class',
					'category',
					'Category',
					'stage',
					'status',
					'gw_stress'
				]);
				const key = String(raw ?? '')
					.trim()
					.toLowerCase();
				p[column] = GW_NORMALIZE[key] || (raw ? String(raw).trim() : 'Groundwater class unavailable');
			} else if (atype === 'wiser_rank') {
				const preferred =
					column === '__wiser_irrigation_access_class'
						? ['Irr_access', column]
						: column === '__wiser_kharif_resilience_class'
							? ['Kharif_res', column]
							: column === '__wiser_rabi_resilience_class'
								? ['Rabi_res', column]
								: [column, 'Irr_access', 'Kharif_res', 'Rabi_res'];
				const raw = pickProp(p, preferred);
				const key = String(raw ?? '')
					.trim()
					.toLowerCase();
				p[column] = RANK_NORMALIZE[key] || (raw ? String(raw).trim() : 'NA');
			} else if (atype === 'aquifers') {
				const raw = pickProp(p, ['aquifer', 'Major_Aqui', 'aquifers']);
				p[column] = raw != null ? String(raw) : 'Other';
			}

			return { ...f, properties: p };
		});
	}

	async function fetchClippedGeoJSON(url) {
		const response = await fetch(url, { credentials: 'include' });
		if (!response.ok) {
			throw new Error(`Failed to fetch vector layer (${response.status})`);
		}
		return response.json();
	}

	/** Metadata only — geometries load on demand when the user selects a layer. */
	async function loadVectorLayers() {
		try {
			removeVectorLayers();
			const { vector_layers } = await fetchVectorLayers(project?.id);
			vectorLayers = vector_layers;
			secondaryLayers = rebuildSecondaryList(cogLayers, vectorLayers);
			for (const layer of vector_layers) {
				cogVisibility = {
					...cogVisibility,
					[layer.id]: false
				};
				if (layer.status === 'error') {
					status = `${layer.name} error: ${layer.error ?? 'unavailable'}`;
				}
			}
		} catch (err) {
			console.error('Vector layers failed', err);
			status = `Vector layers unavailable: ${err instanceof Error ? err.message : String(err)}`;
		}
	}

	async function ensureVectorLayerOnMap(layer) {
		if (!map || !layer?.id) return;
		const sourceId = `vec-${layer.id}`;
		if (map.getSource(sourceId)) return;
		if (!layer.url || layer.map_render === false) return;

		status = `Loading ${layer.name}…`;
		let data;
		try {
			data = await fetchClippedGeoJSON(layer.url);
		} catch (fetchErr) {
			console.error(`Failed to load ${layer.name}:`, fetchErr);
			status = `${layer.name} failed: ${fetchErr instanceof Error ? fetchErr.message : String(fetchErr)}`;
			return;
		}

		let features = enrichVillageProperties(
			data.features ?? [],
			layer.analysis_type === 'demographics_marginalized' || layer.style_column === 'pct_scst'
		);
		features = normalizeVectorFeatures(features, layer);
		data = { type: 'FeatureCollection', features };
		layerActiveLegend = {
			...layerActiveLegend,
			[layer.id]: legendFromFeatures(layer, features)
		};

		const fillId = `${sourceId}-fill`;
		const lineId = `${sourceId}-line`;
		const beforeId = map.getLayer('watershed-fill') ? 'watershed-fill' : undefined;
		const fillColor = vectorFillColor(layer);

		map.addSource(sourceId, { type: 'geojson', data });
		map.addLayer(
			{
				id: fillId,
				type: 'fill',
				source: sourceId,
				layout: { visibility: 'none' },
				paint: { 'fill-color': fillColor, 'fill-opacity': 0.65 }
			},
			beforeId
		);
		map.addLayer(
			{
				id: lineId,
				type: 'line',
				source: sourceId,
				layout: { visibility: 'none' },
				paint: { 'line-color': '#334155', 'line-width': 0.6, 'line-opacity': 0.5 }
			},
			beforeId
		);
		applyLayerStackOrder();
		ensureDrawPreviewOnTop();
		status = 'Ready';
	}

	async function preloadAllSecondaryData() {
		if (!project?.id) return;
		status = 'Loading watershed layers & analysis…';

		// Seed COG legends (full catalog; class filter needs raster sampling later)
		for (const layer of secondaryLayers.filter((l) => l.kind === 'cog')) {
			layerActiveLegend = {
				...layerActiveLegend,
				[layer.id]: legendFromFeatures(layer, null)
			};
		}

		const vectorJobs = secondaryLayers
			.filter((l) => l.kind === 'vector' && l.map_render !== false && l.status !== 'error')
			.map((l) => ensureVectorLayerOnMap(l));

		let analysisJobs = [];
		try {
			layerAnalysisLoading = Object.fromEntries(
				secondaryLayers.map((l) => [l.id, true])
			);
			const { analyses } = await fetchBatchLayerAnalysis(project.id);
			const next = { ...layerAnalysis };
			for (const a of analyses || []) {
				next[a.layer_id] = a;
			}
			layerAnalysis = next;
			analysisPreloadDone = true;
		} catch (err) {
			console.error('Batch analysis failed', err);
			// Fall back to per-layer
			analysisJobs = secondaryLayers.map((l) => ensureLayerAnalysis(l.id));
		} finally {
			layerAnalysisLoading = Object.fromEntries(
				secondaryLayers.map((l) => [l.id, false])
			);
		}

		await Promise.all([...vectorJobs, ...analysisJobs]);
		status = 'Ready';
	}

	async function ensureLayerAnalysis(layerId) {
		if (!project?.id || !layerId) return;
		if (layerAnalysis[layerId]?.stats || layerAnalysisLoading[layerId]) return;
		const meta = secondaryLayers.find((l) => l.id === layerId);
		if (!meta) return;
		layerAnalysisLoading = { ...layerAnalysisLoading, [layerId]: true };
		try {
			const isCog = meta.kind === 'cog';
			const result = await fetchLayerAnalysis(layerId, project.id, { isCog });
			layerAnalysis = { ...layerAnalysis, [layerId]: result };
		} catch (err) {
			layerAnalysis = {
				...layerAnalysis,
				[layerId]: {
					layer_id: layerId,
					stats: {},
					interpretation: meta.interpretation || '',
					field_check: meta.field_check || '',
					status: 'error',
					error: err instanceof Error ? err.message : String(err)
				}
			};
		} finally {
			layerAnalysisLoading = { ...layerAnalysisLoading, [layerId]: false };
		}
	}

	function fitToWatershed() {
		if (!map || !watershedBounds) return;
		map.fitBounds(
			[
				[watershedBounds[0], watershedBounds[1]],
				[watershedBounds[2], watershedBounds[3]]
			],
			{ padding: 40, maxZoom: 14, duration: 0 }
		);
	}

	function loadWatershedBoundary() {
		if (!project?.watershed_geometry) return;
		const data = {
			type: 'FeatureCollection',
			features: [
				{
					type: 'Feature',
					properties: { name: project.watershed_name },
					geometry: project.watershed_geometry
				}
			]
		};
		if (map.getSource('watershed')) {
			map.getSource('watershed').setData(data);
		} else {
			map.addSource('watershed', { type: 'geojson', data });
			map.addLayer({
				id: 'watershed-fill',
				type: 'fill',
				source: 'watershed',
				paint: { 'fill-color': '#9ca3af', 'fill-opacity': 0.08 }
			});
		}
		if (map.getLayer('watershed-line')) map.removeLayer('watershed-line');
		map.addLayer({
			id: 'watershed-line',
			type: 'line',
			source: 'watershed',
			paint: {
				'line-color': '#6b7280',
				'line-width': 2.5,
				'line-opacity': 1
			}
		});
	}

	function addGeoJsonSource(sourceId, data, layers, promoteId) {
		if (map.getSource(sourceId)) {
			map.getSource(sourceId).setData(data);
			return;
		}
		map.addSource(sourceId, {
			type: 'geojson',
			data,
			...(promoteId ? { promoteId } : {})
		});
		for (const spec of layers) map.addLayer(spec);
		updateDrawSizes();
		ensureDrawPreviewOnTop();
	}

	function removeGeoJsonSource(sourceId, layerIds) {
		for (const layerId of layerIds) {
			if (map.getLayer(layerId)) map.removeLayer(layerId);
		}
		if (map.getSource(sourceId)) map.removeSource(sourceId);
	}

	async function reloadObservationZones() {
		if (!project?.id) return;
		const data = await fetchObservationZones(project.id);
		savedZones = data.features.map((f) => ({
			id: String(f.id ?? ''),
			text: String(f.properties?.text ?? ''),
			observations: String(f.properties?.observations ?? ''),
			questions: String(f.properties?.questions ?? ''),
			color: String(f.properties?.color ?? OBSERVATION_ZONE_COLOR)
		}));
		const features = data.features.map((f) => {
			const id = String(f.id ?? '');
			return {
				...f,
				id,
				properties: {
					...f.properties,
					id,
					color: f.properties?.color ?? OBSERVATION_ZONE_COLOR
				}
			};
		});
		const zoneLayers = [
			{
				id: 'zones-fill',
				type: 'fill',
				source: 'zones',
				paint: {
					'fill-color': ['coalesce', ['get', 'color'], OBSERVATION_ZONE_COLOR],
					'fill-opacity': 0.4
				}
			},
			{
				id: 'zones-line',
				type: 'line',
				source: 'zones',
				paint: {
					'line-color': ['coalesce', ['get', 'color'], OBSERVATION_ZONE_COLOR],
					'line-width': LINE_WIDTH
				}
			},
			{
				id: 'zones-label',
				type: 'symbol',
				source: 'zones',
				layout: {
					'text-field': ['get', 'text'],
					'text-size': 11,
					'text-anchor': 'center',
					'text-allow-overlap': true
				},
				paint: {
					'text-color': '#ffffff',
					'text-halo-color': ['coalesce', ['get', 'color'], OBSERVATION_ZONE_COLOR],
					'text-halo-width': 8,
					'text-halo-blur': 0
				}
			}
		];
		removeGeoJsonSource('zones', ['zones-label', 'zones-line', 'zones-fill']);
		addGeoJsonSource('zones', { type: 'FeatureCollection', features }, zoneLayers, 'id');
		toggleZonesLayer(showZonesLayer);
		applyLayerStackOrder();
	}

	async function reloadFieldNotes() {
		if (!project?.id) return;
		const data = await fetchFieldNotes(project.id);
		savedFieldNotes = data.features.map((f) => ({
			id: String(f.id ?? f.properties?.id ?? ''),
			title: String(f.properties?.title ?? ''),
			text: String(f.properties?.text ?? ''),
			photo_path: f.properties?.photo_path ?? null,
			audio_path: f.properties?.audio_path ?? null,
			hypothesis_id: f.properties?.hypothesis_id ?? null,
			created_at: String(f.properties?.created_at ?? '')
		}));
		const features = data.features.map((f) => {
			const id = String(f.id ?? f.properties?.id ?? '');
			return {
				...f,
				id,
				properties: { ...f.properties, id }
			};
		});
		await ensureFieldNotePinIcon();
		removeGeoJsonSource('field-notes', ['field-notes-point']);
		addGeoJsonSource(
			'field-notes',
			{ type: 'FeatureCollection', features },
			[
				{
					id: 'field-notes-point',
					type: 'symbol',
					source: 'field-notes',
					layout: {
						'icon-image': 'field-note-pin',
						'icon-size': fieldNotePinSize(),
						'icon-anchor': 'bottom',
						'icon-allow-overlap': true
					}
				}
			],
			'id'
		);
		toggleFieldNotesLayer(showFieldNotesLayer);
		applyLayerStackOrder();
	}

	async function saveObservationZone() {
		if (!pendingZone) return;
		savingZone = true;
		try {
			await createObservationZone(
				project.id,
				pendingZone.geometry,
				zoneText.trim(),
				zoneObservations.trim(),
				zoneQuestions.trim(),
				zoneColor
			);
			pendingZone = null;
			zoneText = '';
			zoneObservations = '';
			zoneQuestions = '';
			resetDrawState();
			await reloadObservationZones();
			status = 'Observation zone saved';
		} catch (err) {
			status = `Save failed: ${err instanceof Error ? err.message : String(err)}`;
		} finally {
			savingZone = false;
		}
	}

	function cancelPendingZone() {
		pendingZone = null;
		zoneText = '';
		zoneObservations = '';
		zoneQuestions = '';
		resetDrawState();
		status = 'Ready';
	}

	function startEditSelectedZone() {
		if (!selectedZone) return;
		editingSelectedZone = { ...selectedZone };
		showSelectedZoneMenu = false;
	}

	function cancelEditSelectedZone() {
		editingSelectedZone = null;
	}

	async function saveSelectedZone() {
		if (!editingSelectedZone) return;
		savingZone = true;
		try {
			const updated = await updateObservationZone(editingSelectedZone.id, {
				text: editingSelectedZone.text.trim(),
				observations: editingSelectedZone.observations.trim(),
				questions: editingSelectedZone.questions.trim(),
				color: editingSelectedZone.color
			});
			selectedZone = {
				id: editingSelectedZone.id,
				text: String(updated.properties?.text ?? editingSelectedZone.text),
				observations: String(
					updated.properties?.observations ?? editingSelectedZone.observations
				),
				questions: String(updated.properties?.questions ?? editingSelectedZone.questions),
				color: String(updated.properties?.color ?? editingSelectedZone.color)
			};
			editingSelectedZone = null;
			await reloadObservationZones();
			status = 'Observation zone updated';
		} catch (err) {
			status = `Update failed: ${err instanceof Error ? err.message : String(err)}`;
		} finally {
			savingZone = false;
		}
	}

	async function deleteSelectedZone() {
		if (!selectedZone) return;
		showSelectedZoneMenu = false;
		if (!confirm('Delete this observation zone?')) return;
		try {
			await deleteObservationZone(selectedZone.id);
			closeSelectedZone();
			await reloadObservationZones();
			status = 'Observation zone deleted';
		} catch (err) {
			status = `Delete failed: ${err instanceof Error ? err.message : String(err)}`;
		}
	}

	async function reloadHypotheses() {
		if (!project?.id) return;
		hypotheses = await fetchHypotheses(project.id);
	}

	function hypothesisLabel(h) {
		const text = String(h?.hypothesis ?? '').trim();
		return text.length > 60 ? `${text.slice(0, 60)}…` : text || 'Untitled hypothesis';
	}

	function zoneTitleById(zoneId) {
		return savedZones.find((z) => z.id === zoneId)?.text?.trim() || 'Untitled zone';
	}

	function startCreateHypothesis() {
		creatingHypothesis = true;
		newHypothesisText = '';
		newHypothesisZoneIds = [];
		selectedHypothesis = null;
		editingHypothesis = null;
		hypothesisError = '';
	}

	function cancelCreateHypothesis() {
		creatingHypothesis = false;
		newHypothesisText = '';
		newHypothesisZoneIds = [];
		hypothesisError = '';
	}

	function toggleNewHypothesisZone(zoneId) {
		if (newHypothesisZoneIds.includes(zoneId)) {
			newHypothesisZoneIds = newHypothesisZoneIds.filter((id) => id !== zoneId);
		} else {
			newHypothesisZoneIds = [...newHypothesisZoneIds, zoneId];
		}
	}

	async function saveNewHypothesis() {
		if (!newHypothesisText.trim()) {
			hypothesisError = 'Hypothesis text is required';
			return;
		}
		savingHypothesis = true;
		hypothesisError = '';
		try {
			const created = await createHypothesis(
				project.id,
				newHypothesisText.trim(),
				newHypothesisZoneIds
			);
			creatingHypothesis = false;
			newHypothesisText = '';
			newHypothesisZoneIds = [];
			await reloadHypotheses();
			selectedHypothesis = created;
			editingHypothesis = null;
			status = 'Hypothesis created';
		} catch (err) {
			hypothesisError = err instanceof Error ? err.message : String(err);
		} finally {
			savingHypothesis = false;
		}
	}

	function openHypothesis(h) {
		selectedHypothesis = h;
		editingHypothesis = null;
		hypothesisError = '';
		showSelectedHypothesisMenu = false;
	}

	function startEditHypothesis() {
		if (!selectedHypothesis) return;
		showSelectedHypothesisMenu = false;
		editingHypothesis = {
			id: selectedHypothesis.id,
			hypothesis: selectedHypothesis.hypothesis,
			root_cause: selectedHypothesis.root_cause ?? '',
			status: selectedHypothesis.status,
			observation_zone_ids: [...(selectedHypothesis.observation_zone_ids ?? [])],
			field_note_count: selectedHypothesis.field_note_count ?? 0
		};
		hypothesisError = '';
	}

	function cancelEditHypothesis() {
		editingHypothesis = null;
		hypothesisError = '';
	}

	function toggleEditHypothesisZone(zoneId) {
		if (!editingHypothesis) return;
		const ids = editingHypothesis.observation_zone_ids;
		if (ids.includes(zoneId)) {
			editingHypothesis.observation_zone_ids = ids.filter((id) => id !== zoneId);
		} else {
			editingHypothesis.observation_zone_ids = [...ids, zoneId];
		}
	}

	async function saveEditedHypothesis() {
		if (!editingHypothesis) return;
		if (!editingHypothesis.hypothesis.trim()) {
			hypothesisError = 'Hypothesis text is required';
			return;
		}
		savingHypothesis = true;
		hypothesisError = '';
		try {
			const payload = {
				hypothesis: editingHypothesis.hypothesis.trim(),
				status: editingHypothesis.status,
				observation_zone_ids: editingHypothesis.observation_zone_ids
			};
			if (editingHypothesis.field_note_count > 0) {
				payload.root_cause = editingHypothesis.root_cause.trim();
			}
			const updated = await updateHypothesis(editingHypothesis.id, payload);
			selectedHypothesis = updated;
			editingHypothesis = null;
			await reloadHypotheses();
			status = 'Hypothesis updated';
		} catch (err) {
			hypothesisError = err instanceof Error ? err.message : String(err);
		} finally {
			savingHypothesis = false;
		}
	}

	async function deleteSelectedHypothesis() {
		if (!selectedHypothesis) return;
		if (!confirm('Delete this hypothesis?')) return;
		try {
			await deleteHypothesis(selectedHypothesis.id);
			closeSelectedHypothesis();
			await reloadHypotheses();
			status = 'Hypothesis deleted';
		} catch (err) {
			status = `Delete failed: ${err instanceof Error ? err.message : String(err)}`;
		}
	}

	function onFieldNotePhotoChange(e) {
		noteMediaError = '';
		const file = e.currentTarget.files?.[0];
		if (!file) {
			notePhoto = undefined;
			if (notePhotoPreview) URL.revokeObjectURL(notePhotoPreview);
			notePhotoPreview = null;
			return;
		}
		if (file.size > MAX_FIELD_NOTE_MEDIA_BYTES) {
			noteMediaError = 'Image must be 50MB or smaller';
			e.currentTarget.value = '';
			notePhoto = undefined;
			if (notePhotoPreview) URL.revokeObjectURL(notePhotoPreview);
			notePhotoPreview = null;
			return;
		}
		notePhoto = file;
		if (notePhotoPreview) URL.revokeObjectURL(notePhotoPreview);
		notePhotoPreview = file.type.startsWith('image/') ? URL.createObjectURL(file) : null;
	}

	function onFieldNoteAudioChange(e) {
		noteMediaError = '';
		const file = e.currentTarget.files?.[0];
		if (!file) {
			noteAudio = undefined;
			if (noteAudioPreview) URL.revokeObjectURL(noteAudioPreview);
			noteAudioPreview = null;
			return;
		}
		if (file.size > MAX_FIELD_NOTE_MEDIA_BYTES) {
			noteMediaError = 'Audio must be 50MB or smaller';
			e.currentTarget.value = '';
			noteAudio = undefined;
			if (noteAudioPreview) URL.revokeObjectURL(noteAudioPreview);
			noteAudioPreview = null;
			return;
		}
		noteAudio = file;
		if (noteAudioPreview) URL.revokeObjectURL(noteAudioPreview);
		noteAudioPreview = URL.createObjectURL(file);
	}

	async function submitFieldNote() {
		if (!pendingPoint) return;
		if (noteMediaError) return;
		try {
			await createFieldNote(
				project.id,
				{ type: 'Point', coordinates: pendingPoint },
				noteTitle,
				noteText,
				notePhoto,
				noteAudio,
				noteHypothesisId || null
			);
			cancelPendingForms();
			addingFieldNote = false;
			await reloadFieldNotes();
			await reloadHypotheses();
			status = 'Field note saved';
		} catch (err) {
			status = String(err);
		}
	}

	function startEditSelectedFieldNote() {
		if (!selectedFieldNote) return;
		editingSelectedFieldNote = {
			...selectedFieldNote,
			title: selectedFieldNote.title ?? '',
			hypothesis_id: selectedFieldNote.hypothesis_id ?? ''
		};
		showSelectedFieldNoteMenu = false;
	}

	function cancelEditSelectedFieldNote() {
		editingSelectedFieldNote = null;
	}

	async function saveSelectedFieldNote() {
		if (!editingSelectedFieldNote) return;
		savingFieldNote = true;
		try {
			const updated = await updateFieldNote(editingSelectedFieldNote.id, {
				title: editingSelectedFieldNote.title.trim(),
				text: editingSelectedFieldNote.text.trim(),
				hypothesis_id: editingSelectedFieldNote.hypothesis_id || null
			});
			selectedFieldNote = {
				id: editingSelectedFieldNote.id,
				title: String(updated.properties?.title ?? editingSelectedFieldNote.title),
				text: String(updated.properties?.text ?? editingSelectedFieldNote.text),
				photo_path: updated.properties?.photo_path ?? editingSelectedFieldNote.photo_path,
				audio_path: updated.properties?.audio_path ?? editingSelectedFieldNote.audio_path,
				hypothesis_id: updated.properties?.hypothesis_id ?? editingSelectedFieldNote.hypothesis_id,
				created_at: updated.properties?.created_at ?? editingSelectedFieldNote.created_at
			};
			editingSelectedFieldNote = null;
			await reloadFieldNotes();
			await reloadHypotheses();
			status = 'Field note updated';
		} catch (err) {
			status = `Update failed: ${err instanceof Error ? err.message : String(err)}`;
		} finally {
			savingFieldNote = false;
		}
	}

	async function deleteSelectedFieldNote() {
		if (!selectedFieldNote) return;
		showSelectedFieldNoteMenu = false;
		if (!confirm('Delete this field note?')) return;
		try {
			await deleteFieldNote(selectedFieldNote.id);
			closeSelectedFieldNote();
			await reloadFieldNotes();
			status = 'Field note deleted';
		} catch (err) {
			status = `Delete failed: ${err instanceof Error ? err.message : String(err)}`;
		}
	}

	function toggleCog(id, visible) {
		cogVisibility = { ...cogVisibility, [id]: visible };
		const meta = secondaryLayers.find((l) => l.id === id);
		if (meta?.kind === 'vector') {
			setLayerVisibility(`vec-${id}-fill`, visible);
			setLayerVisibility(`vec-${id}-line`, visible);
		} else {
			setLayerVisibility(`cog-${id}`, visible);
		}
	}

	function setMapMode(mode) {
		if (mode !== 'flat' && mode !== '3d') return;
		mapMode = mode;
		if (mode === 'flat') {
			if (map) {
				map.setTerrain?.(null);
				map.easeTo({ pitch: 0, bearing: 0, duration: 400 });
				requestAnimationFrame(() => map?.resize());
			}
			status = 'Ready';
		} else {
			status = 'Loading 3D DEM terrain…';
		}
	}
</script>

<div class="flex h-full min-h-0 w-full">
	<aside
		class="layer-sidebar flex shrink-0 flex-col overflow-hidden bg-white font-body"
		style:width="{sidebarWidth}px"
	>
		<div class="border-b border-brand-navy/10 px-3 py-4">
			<h3 class="sidebar-section-title font-headline text-[11px] font-semibold tracking-[0.08em] text-brand-navy/55 uppercase">
				Base layer
			</h3>
			<select
				class="basemap-select w-full cursor-pointer rounded-lg border border-brand-navy/15 bg-white font-body text-sm text-brand-navy"
				value={baseLayer}
				onchange={(e) => setBaseLayer(e.currentTarget.value)}
			>
				<option value="osm">OpenStreetMap</option>
				<option value="esri">ESRI Imagery</option>
			</select>
		</div>

		<div class="min-w-0 flex-1 overflow-y-auto overflow-x-hidden px-3 py-4">
			<h3 class="sidebar-section-title font-headline text-[11px] font-semibold tracking-[0.08em] text-brand-navy/55 uppercase">
				Secondary data
			</h3>
			<div class="layer-list mb-5 flex flex-col gap-1.5">
				{#each secondaryLayers as layer, index (layer.id)}
					<div
						class="layer-row"
						class:layer-row-selected={selectedLayer?.kind === 'secondary' && selectedLayer.id === layer.id}
						class:layer-row-dragging={dragReorder.category === 'secondary' && dragReorder.index === index}
						class:layer-row-over={dragReorder.category === 'secondary' && dragOverIndex === index && dragReorder.index !== index}
						draggable="true"
						role="listitem"
						ondragstart={(e) => onRowDragStart('secondary', index, e)}
						ondragend={endLayerDrag}
						ondragover={onLayerDragOver}
						ondragenter={(e) => onLayerDragEnter('secondary', index, e)}
						ondrop={(e) => onLayerDrop('secondary', index, e)}
					>
					<button
						type="button"
						data-no-drag
						class="layer-eye"
						disabled={layer.status === 'error' || layer.map_render === false}
						title={layer.map_render === false ? 'Map rendering disabled — dataset too large' : undefined}
						aria-label={(cogVisibility[layer.id] ?? false) ? 'Hide layer' : 'Show layer'}
						onclick={(e) => {
							e.stopPropagation();
							toggleCog(layer.id, !(cogVisibility[layer.id] ?? false));
						}}
					>
						{#if cogVisibility[layer.id] ?? false}
								<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="h-4 w-4">
									<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
									<circle cx="12" cy="12" r="3" />
								</svg>
							{:else}
								<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="h-4 w-4">
									<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
									<path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
									<path d="M1 1l22 22" />
									<path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" />
								</svg>
							{/if}
						</button>
						<button
							type="button"
							class="layer-label"
							title={layer.name}
							onclick={() => selectLayer({ kind: 'secondary', id: layer.id })}
						>
							{layer.name}
						</button>
						<span class="layer-drag-handle" aria-hidden="true" title="Drag to reorder">
							<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" class="h-4 w-4">
								<circle cx="9" cy="6" r="1.4" fill="currentColor" />
								<circle cx="15" cy="6" r="1.4" fill="currentColor" />
								<circle cx="9" cy="12" r="1.4" fill="currentColor" />
								<circle cx="15" cy="12" r="1.4" fill="currentColor" />
								<circle cx="9" cy="18" r="1.4" fill="currentColor" />
								<circle cx="15" cy="18" r="1.4" fill="currentColor" />
							</svg>
						</span>
					</div>
					{#if layer.error}
						<p class="m-0 mb-1 truncate px-2 text-xs text-red-600" title={layer.error}>{layer.error}</p>
					{/if}
				{:else}
					<p class="m-0 px-1 text-xs text-brand-steel">No secondary layers configured</p>
				{/each}
			</div>

			<h3 class="sidebar-section-title font-headline text-[11px] font-semibold tracking-[0.08em] text-brand-navy/55 uppercase">
				Primary layers
			</h3>
			<div class="layer-list flex flex-col gap-1.5">
				{#each primaryLayerOrder as layerId, index (layerId)}
					<div
						class="layer-row"
						class:layer-row-selected={activePrimaryTab === layerId && selectedLayer?.kind === 'primary'}
						class:layer-row-dragging={dragReorder.category === 'primary' && dragReorder.index === index}
						class:layer-row-over={dragReorder.category === 'primary' && dragOverIndex === index && dragReorder.index !== index}
						draggable="true"
						role="listitem"
						ondragstart={(e) => onRowDragStart('primary', index, e)}
						ondragend={endLayerDrag}
						ondragover={onLayerDragOver}
						ondragenter={(e) => onLayerDragEnter('primary', index, e)}
						ondrop={(e) => onLayerDrop('primary', index, e)}
					>
						{#if layerId === 'observation-zones'}
							<button
								type="button"
								data-no-drag
								class="layer-eye"
								aria-label={showZonesLayer ? 'Hide zones on map' : 'Show zones on map'}
								onclick={(e) => {
									e.stopPropagation();
									toggleZonesLayer(!showZonesLayer);
								}}
							>
								{#if showZonesLayer}
									<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="h-4 w-4">
										<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
										<circle cx="12" cy="12" r="3" />
									</svg>
								{:else}
									<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="h-4 w-4">
										<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
										<path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
										<path d="M1 1l22 22" />
										<path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" />
									</svg>
								{/if}
							</button>
							<button
								type="button"
								class="layer-label layer-label-icon"
								onclick={() => selectPrimaryTab('observation-zones')}
							>
								<ObservationZoneIcon size="sm" />
								<span class="truncate">{PRIMARY_LAYER_LABELS[layerId]}</span>
							</button>
						{:else if layerId === 'field-notes'}
							<button
								type="button"
								data-no-drag
								class="layer-eye"
								aria-label={showFieldNotesLayer ? 'Hide notes on map' : 'Show notes on map'}
								onclick={(e) => {
									e.stopPropagation();
									toggleFieldNotesLayer(!showFieldNotesLayer);
								}}
							>
								{#if showFieldNotesLayer}
									<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="h-4 w-4">
										<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
										<circle cx="12" cy="12" r="3" />
									</svg>
								{:else}
									<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="h-4 w-4">
										<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
										<path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
										<path d="M1 1l22 22" />
										<path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" />
									</svg>
								{/if}
							</button>
							<button
								type="button"
								class="layer-label layer-label-icon"
								onclick={() => selectPrimaryTab('field-notes')}
							>
								<FieldNoteIcon size="sm" />
								<span class="truncate">{PRIMARY_LAYER_LABELS[layerId]}</span>
							</button>
						{:else if layerId === 'hypotheses'}
							<span class="layer-eye-spacer" aria-hidden="true"></span>
							<button
								type="button"
								class="layer-label layer-label-icon"
								onclick={() => selectPrimaryTab('hypotheses')}
							>
								<HypothesisIcon size="sm" />
								<span class="truncate">{PRIMARY_LAYER_LABELS[layerId]}</span>
							</button>
						{/if}
						<span class="layer-drag-handle" aria-hidden="true" title="Drag to reorder">
							<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" class="h-4 w-4">
								<circle cx="9" cy="6" r="1.4" fill="currentColor" />
								<circle cx="15" cy="6" r="1.4" fill="currentColor" />
								<circle cx="9" cy="12" r="1.4" fill="currentColor" />
								<circle cx="15" cy="12" r="1.4" fill="currentColor" />
								<circle cx="9" cy="18" r="1.4" fill="currentColor" />
								<circle cx="15" cy="18" r="1.4" fill="currentColor" />
							</svg>
						</span>
					</div>
				{/each}
			</div>
		</div>
	</aside>

	<div
		class="sidebar-resize-handle"
		class:sidebar-resize-active={sidebarResizing}
		role="separator"
		aria-orientation="vertical"
		aria-label="Resize sidebar"
		onmousedown={onSidebarResizeStart}
	></div>

	<!-- Map -->
	<div class="relative h-full min-h-0 flex-1">
		<div
			bind:this={container}
			class="h-full w-full"
			class:invisible={mapMode === '3d'}
			class:pointer-events-none={mapMode === '3d'}
		></div>

		{#if mapMode === '3d' && project?.id}
			<div class="absolute inset-0 z-[5]">
				{#key `${project.id}:${selectedLayer?.kind === 'secondary' ? selectedLayer.id : 'dem'}`}
					<Terrain3DView
						projectId={project.id}
						layerId={selectedLayer?.kind === 'secondary' ? selectedLayer.id : 'dem'}
					/>
				{/key}
			</div>
		{/if}

		<div
			class="absolute top-3 left-12 z-20 flex overflow-hidden rounded-lg border border-brand-navy/15 bg-white/95 text-xs shadow-md backdrop-blur-sm"
			role="group"
			aria-label="Map view mode"
		>
			<button
				type="button"
				class="px-3 py-1.5 font-medium transition-colors"
				class:bg-brand-navy={mapMode === 'flat'}
				class:text-white={mapMode === 'flat'}
				class:text-brand-navy={mapMode !== 'flat'}
				onclick={() => setMapMode('flat')}
			>
				Flat
			</button>
			<button
				type="button"
				class="px-3 py-1.5 font-medium transition-colors"
				class:bg-brand-navy={mapMode === '3d'}
				class:text-white={mapMode === '3d'}
				class:text-brand-navy={mapMode !== '3d'}
				onclick={() => setMapMode('3d')}
			>
				3D
			</button>
		</div>

		{#if selectedLayer?.kind === 'secondary' && mapLegendItems.length && mapMode === 'flat'}
			{@const layer = secondaryLayers.find((l) => l.id === selectedLayer.id)}
			<div
				class="pointer-events-none absolute top-3 right-3 z-10 max-h-[70%] max-w-[220px] overflow-y-auto rounded-lg border border-brand-navy/10 bg-white/95 p-3 shadow-md backdrop-blur-sm"
			>
				<p class="m-0 mb-2 text-[10px] font-semibold tracking-wide text-brand-navy/55 uppercase">
					{layer?.name ?? 'Legend'}
				</p>
				{#if layer?.render_type === 'continuous' || mapLegendItems[0]?.continuous}
					<div
						class="mb-1 h-2.5 w-full rounded border border-gray-200"
						style="background: linear-gradient(90deg, #2c7bb6, #abd9e9, #ffffbf, #fdae61, #d7191c)"
					></div>
					<div class="flex justify-between text-[10px] text-gray-500">
						<span>Low</span>
						<span>High</span>
					</div>
				{:else}
					<ul class="m-0 list-none space-y-1.5 p-0">
						{#each mapLegendItems as item}
							<li class="flex items-center gap-2 text-xs">
								<span
									class="inline-block h-3.5 w-3.5 shrink-0 rounded border border-gray-300"
									style="background-color: {item.color}"
								></span>
								<span class="text-gray-700">{item.label}</span>
							</li>
						{/each}
					</ul>
				{/if}
			</div>
		{/if}

		{#if mapMode === 'flat'}
			<div class="absolute bottom-2 left-2 z-10 max-w-[50%] rounded bg-white/90 px-2 py-1 text-sm shadow">
				{status}
			</div>
			<div
				class="absolute right-2 bottom-1 z-10 max-w-[45%] truncate rounded bg-white/80 px-2 py-0.5 text-[10px] text-gray-600 shadow-sm"
			>
				{activeAttribution}
			</div>
		{/if}
	</div>
	<div
		class="sidebar-resize-handle"
		class:sidebar-resize-active={rightSidebarResizing}
		role="separator"
		aria-orientation="vertical"
		aria-label="Resize right sidebar"
		onmousedown={onRightSidebarResizeStart}
	></div>

	<aside
		class="flex shrink-0 flex-col overflow-hidden border-l border-brand-navy/10 bg-white font-body"
		style:width="{rightSidebarWidth}px"
	>
		<div class="min-w-0 flex-1 overflow-y-auto overflow-x-hidden p-3">
			{#if selectedLayer?.kind === 'secondary'}
				{@const layer = secondaryLayers.find((l) => l.id === selectedLayer.id)}
				{@const analysis = layerAnalysis[selectedLayer.id]}
				{@const analysisBusy = layerAnalysisLoading[selectedLayer.id] && !analysis}
				{@const meaning = analysis?.meaning || layer?.meaning || layer?.interpretation || ''}
				{@const uncertainty = analysis?.uncertainty || layer?.uncertainty || ''}
				{@const fieldCheck = analysis?.field_check || layer?.field_check || ''}
				{@const evidence =
					analysis?.evidence ||
					(analysis?.stats && Object.keys(analysis.stats).length
						? Object.entries(analysis.stats)
								.map(([k, v]) => `${k}: ${v}`)
								.join('; ')
						: '')}
				<div class="rounded-lg border border-brand-navy/10 bg-white p-4">
					<h3 class="m-0 mb-1 text-base font-semibold">{layer?.name ?? 'Layer'}</h3>
					<p class="m-0 mb-4 text-xs text-gray-500">
						Evidence, interpretation, uncertainty, and field checks
					</p>

					{#if analysisBusy}
						<p class="m-0 text-sm text-gray-500">Loading watershed analysis…</p>
					{:else if analysis?.error}
						<p class="m-0 text-sm text-red-600">{analysis.error}</p>
					{:else}
						<section class="mb-4">
							<h4 class="m-0 mb-1.5 text-[11px] font-semibold tracking-wide text-brand-navy/60 uppercase">
								Evidence
							</h4>
							{#if analysis?.stats && Object.keys(analysis.stats).length}
								<dl class="m-0 space-y-1.5">
									{#each Object.entries(analysis.stats) as [key, value]}
										<div class="flex items-start justify-between gap-3 text-sm">
											<dt class="text-gray-500">{key}</dt>
											<dd class="m-0 text-right font-medium text-brand-navy">{value}</dd>
										</div>
									{/each}
								</dl>
							{:else if evidence}
								<p class="m-0 text-sm leading-relaxed text-gray-700">{evidence}</p>
							{:else}
								<p class="m-0 text-sm text-gray-500 italic">
									Field verification should fill this signal.
								</p>
							{/if}
						</section>

						<section class="mb-4">
							<h4 class="m-0 mb-1.5 text-[11px] font-semibold tracking-wide text-brand-navy/60 uppercase">
								What it may mean
							</h4>
							<p class="m-0 text-sm leading-relaxed text-gray-700">
								{meaning || '—'}
							</p>
						</section>

						<section class="mb-4">
							<h4 class="m-0 mb-1.5 text-[11px] font-semibold tracking-wide text-brand-navy/60 uppercase">
								Uncertainty
							</h4>
							<p class="m-0 text-sm leading-relaxed text-gray-700">
								{uncertainty || '—'}
							</p>
						</section>

						{#if fieldCheck}
							<div
								class="rounded-md border-l-4 border-[#0fb3a3] bg-[color-mix(in_srgb,#0fb3a3_8%,white)] px-3 py-2"
							>
								<p class="m-0 mb-1 text-[11px] font-semibold tracking-wide text-[#0a5c55] uppercase">
									Field check
								</p>
								<p class="m-0 text-sm leading-relaxed text-brand-navy">{fieldCheck}</p>
							</div>
						{/if}
					{/if}
				</div>
			{:else if selectedLayer?.kind === 'primary' && activePrimaryTab === 'observation-zones'}
				<div class="rounded-lg border border-brand-navy/10 bg-white p-4">
					<h3 class="m-0 mb-1 text-base font-semibold">Observation zones</h3>
					<p class="m-0 mb-3 text-xs text-gray-500">
						Click a zone on the map to view details, or add a new polygon.
					</p>
					<button
						type="button"
						class="flex w-full cursor-pointer items-center justify-center gap-2 rounded-lg border-0 px-3 py-2.5 font-body text-sm text-white hover:opacity-90"
						style:background-color={OBSERVATION_ZONE_COLOR}
						onclick={startObservationZoneDraw}
					>
						<span class="text-lg leading-none">+</span> Add observation zone
					</button>
					{#if zoneDraw}
						<p class="m-0 mt-3 text-xs text-amber-700">
							Drawing… click corners, double-click last point to finish.
						</p>
						<button
							type="button"
							class="mt-2 cursor-pointer border-0 bg-transparent p-0 text-sm text-gray-600 underline"
							onclick={cancelZoneDraw}
						>
							Cancel drawing
						</button>
					{/if}
				</div>

				{#if pendingZone}
					<div class="rounded-lg border border-brand-navy/10 bg-white p-4">
						<h3 class="m-0 mb-3 text-base font-semibold">New observation zone</h3>
						<label for="annot-text" class="text-sm text-gray-600">Title</label>
						<input
							id="annot-text"
							type="text"
							class="my-1.5 mb-3 box-border w-full rounded border border-gray-300 p-2 text-sm"
							bind:value={zoneText}
							placeholder="Zone title"
						/>
						<label for="annot-observations" class="text-sm text-gray-600">Observations</label>
						<textarea
							id="annot-observations"
							class="my-1.5 mb-3 box-border w-full rounded border border-gray-300 p-2 text-sm"
							bind:value={zoneObservations}
							placeholder="What did you observe?"
							rows="3"
						></textarea>
						<label for="annot-questions" class="text-sm text-gray-600">Questions</label>
						<textarea
							id="annot-questions"
							class="my-1.5 mb-3 box-border w-full rounded border border-gray-300 p-2 text-sm"
							bind:value={zoneQuestions}
							placeholder="What questions arise?"
							rows="3"
						></textarea>
						<p class="m-0 mb-2 text-sm text-gray-600">Colour</p>
						<div class="mb-4 flex flex-wrap gap-2">
							{#each ZONE_COLORS as c}
								<button
									type="button"
									class="h-8 w-8 cursor-pointer rounded-full border-2"
									class:border-gray-900={zoneColor === c.hex}
									class:border-transparent={zoneColor !== c.hex}
									style="background-color: {c.hex}"
									title={c.label}
									aria-label={c.label}
									onclick={() => (zoneColor = c.hex)}
								></button>
							{/each}
						</div>
						<div class="flex gap-2">
							<button
								class="cursor-pointer rounded border-0 bg-brand-blue px-3 py-1.5 font-body text-sm text-white disabled:opacity-60"
								disabled={savingZone}
								onclick={saveObservationZone}
							>
								{savingZone ? 'Saving…' : 'Save'}
							</button>
							<button
								class="cursor-pointer rounded border-0 bg-brand-steel px-3 py-1.5 font-body text-sm text-white hover:bg-brand-navy"
								onclick={cancelPendingZone}
							>
								Cancel
							</button>
						</div>
					</div>
				{:else if editingSelectedZone}
					<div class="rounded-lg border border-brand-navy/10 bg-white p-4">
						<h3 class="m-0 mb-3 text-base font-semibold">Edit observation zone</h3>
						<label for="edit-text" class="text-sm text-gray-600">Title</label>
						<input
							id="edit-text"
							type="text"
							class="my-1.5 mb-3 box-border w-full rounded border border-gray-300 p-2 text-sm"
							bind:value={editingSelectedZone.text}
						/>
						<label for="edit-observations" class="text-sm text-gray-600">Observations</label>
						<textarea
							id="edit-observations"
							class="my-1.5 mb-3 box-border w-full rounded border border-gray-300 p-2 text-sm"
							bind:value={editingSelectedZone.observations}
							rows="3"
						></textarea>
						<label for="edit-questions" class="text-sm text-gray-600">Questions</label>
						<textarea
							id="edit-questions"
							class="my-1.5 mb-3 box-border w-full rounded border border-gray-300 p-2 text-sm"
							bind:value={editingSelectedZone.questions}
							rows="3"
						></textarea>
						<p class="m-0 mb-2 text-sm text-gray-600">Colour</p>
						<div class="mb-4 flex flex-wrap gap-2">
							{#each ZONE_COLORS as c}
								<button
									type="button"
									class="h-8 w-8 cursor-pointer rounded-full border-2"
									class:border-gray-900={editingSelectedZone.color === c.hex}
									class:border-transparent={editingSelectedZone.color !== c.hex}
									style="background-color: {c.hex}"
									title={c.label}
									onclick={() => (editingSelectedZone.color = c.hex)}
								></button>
							{/each}
						</div>
						<div class="flex gap-2">
							<button
								class="cursor-pointer rounded border-0 bg-brand-blue px-3 py-1.5 font-body text-sm text-white disabled:opacity-60"
								disabled={savingZone}
								onclick={saveSelectedZone}
							>
								Save
							</button>
							<button
								class="cursor-pointer rounded border-0 bg-brand-steel px-3 py-1.5 font-body text-sm text-white hover:bg-brand-navy"
								onclick={cancelEditSelectedZone}
							>
								Cancel
							</button>
						</div>
					</div>
				{:else if selectedZone}
					{@const zoneTitleColor = contrastTextColor(selectedZone.color)}
					<div class="overflow-hidden rounded-lg border border-brand-navy/10 bg-white">
						<div
							class="flex items-center justify-between gap-2 px-4 py-3"
							style:background-color={selectedZone.color}
							style:color={zoneTitleColor}
						>
							<h3 class="m-0 min-w-0 flex-1 font-headline text-base leading-snug font-semibold">
								{selectedZone.text || 'Untitled zone'}
							</h3>
							<div class="flex shrink-0 items-center gap-1">
								<div class="relative">
									<button
										type="button"
										class="flex h-8 w-8 cursor-pointer items-center justify-center rounded border-0 bg-transparent hover:bg-black/10"
										style:color={zoneTitleColor}
										aria-label="More actions"
										onclick={() => (showSelectedZoneMenu = !showSelectedZoneMenu)}
									>
										<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="h-5 w-5">
											<circle cx="12" cy="5" r="1.5" />
											<circle cx="12" cy="12" r="1.5" />
											<circle cx="12" cy="19" r="1.5" />
										</svg>
									</button>
									{#if showSelectedZoneMenu}
										<div
											class="absolute right-0 z-20 mt-1 min-w-28 overflow-hidden rounded border border-gray-200 bg-white text-brand-navy shadow-lg"
										>
											<button
												type="button"
												class="block w-full cursor-pointer border-0 bg-white px-3 py-2 text-left text-sm hover:bg-gray-50"
												onclick={startEditSelectedZone}
											>
												Edit
											</button>
											<button
												type="button"
												class="block w-full cursor-pointer border-0 bg-white px-3 py-2 text-left text-sm text-red-600 hover:bg-red-50"
												onclick={deleteSelectedZone}
											>
												Delete
											</button>
										</div>
									{/if}
								</div>
								<button
									type="button"
									class="cursor-pointer rounded border border-current/30 bg-transparent px-2 py-1 text-xs hover:bg-black/10"
									style:color={zoneTitleColor}
									onclick={closeSelectedZone}
								>
									Close
								</button>
							</div>
						</div>
						<div class="p-4">
							<div class="mb-3">
								<span class="mb-0.5 block text-xs font-semibold text-gray-500 uppercase">Observations</span>
								<p class="m-0 text-sm leading-relaxed whitespace-pre-wrap text-brand-navy">
									{selectedZone.observations || '—'}
								</p>
							</div>
							<div>
								<span class="mb-0.5 block text-xs font-semibold text-gray-500 uppercase">Questions</span>
								<p class="m-0 text-sm leading-relaxed whitespace-pre-wrap text-brand-navy">
									{selectedZone.questions || '—'}
								</p>
							</div>
						</div>
					</div>
				{/if}
			{:else if selectedLayer?.kind === 'primary' && activePrimaryTab === 'hypotheses'}
				<div class="rounded-lg border border-brand-navy/10 bg-white p-4">
					<h3 class="m-0 mb-1 text-base font-semibold">Hypotheses</h3>
					<p class="m-0 mb-3 text-xs text-gray-500">
						Create hypotheses linked to observation zones. Field notes provide evidence for validation.
					</p>
					<button
						type="button"
						class="flex w-full cursor-pointer items-center justify-center gap-2 rounded-lg border-0 px-3 py-2.5 font-body text-sm text-white hover:opacity-90"
						style:background-color={HYPOTHESIS_COLOR}
						onclick={startCreateHypothesis}
					>
						<span class="text-lg leading-none">+</span> Add hypothesis
					</button>
				</div>

				{#if creatingHypothesis}
					<div class="rounded-lg border border-brand-navy/10 bg-white p-4">
						<h3 class="m-0 mb-3 text-base font-semibold">New hypothesis</h3>
						<label for="new-hypothesis" class="text-sm text-gray-600">Hypothesis</label>
						<textarea
							id="new-hypothesis"
							class="my-1.5 mb-3 box-border w-full rounded border border-gray-300 p-2 text-sm"
							bind:value={newHypothesisText}
							placeholder="What do you think is happening?"
							rows="3"
						></textarea>
						<p class="m-0 mb-2 text-sm text-gray-600">Link observation zones</p>
						{#if savedZones.length === 0}
							<p class="m-0 mb-3 text-xs text-gray-500">No observation zones yet.</p>
						{:else}
							<ul class="m-0 mb-3 max-h-36 list-none space-y-1 overflow-y-auto p-0">
								{#each savedZones as zone (zone.id)}
									<li>
										<label class="flex cursor-pointer items-center gap-2 text-sm">
											<input
												type="checkbox"
												checked={newHypothesisZoneIds.includes(zone.id)}
												onchange={() => toggleNewHypothesisZone(zone.id)}
											/>
											<span class="truncate">{zone.text || 'Untitled zone'}</span>
										</label>
									</li>
								{/each}
							</ul>
						{/if}
						{#if hypothesisError}
							<p class="m-0 mb-2 text-xs text-red-600">{hypothesisError}</p>
						{/if}
						<div class="flex gap-2">
							<button
								class="cursor-pointer rounded border-0 bg-brand-blue px-3 py-1.5 font-body text-sm text-white disabled:opacity-60"
								disabled={savingHypothesis}
								onclick={saveNewHypothesis}
							>
								{savingHypothesis ? 'Saving…' : 'Save'}
							</button>
							<button
								class="cursor-pointer rounded border-0 bg-brand-steel px-3 py-1.5 font-body text-sm text-white hover:bg-brand-navy"
								onclick={cancelCreateHypothesis}
							>
								Cancel
							</button>
						</div>
					</div>
				{:else if editingHypothesis}
					<div class="rounded-lg border border-brand-navy/10 bg-white p-4">
						<h3 class="m-0 mb-3 text-base font-semibold">
							{editingHypothesis.field_note_count > 0 ? 'Review hypothesis' : 'Edit hypothesis'}
						</h3>
						<label for="edit-hypothesis-text" class="text-sm text-gray-600">Hypothesis</label>
						<textarea
							id="edit-hypothesis-text"
							class="my-1.5 mb-3 box-border w-full rounded border border-gray-300 p-2 text-sm"
							bind:value={editingHypothesis.hypothesis}
							rows="3"
						></textarea>
						<p class="m-0 mb-2 text-sm text-gray-600">Linked observation zones</p>
						{#if savedZones.length === 0}
							<p class="m-0 mb-3 text-xs text-gray-500">No observation zones available.</p>
						{:else}
							<ul class="m-0 mb-3 max-h-28 list-none space-y-1 overflow-y-auto p-0">
								{#each savedZones as zone (zone.id)}
									<li>
										<label class="flex cursor-pointer items-center gap-2 text-sm">
											<input
												type="checkbox"
												checked={editingHypothesis.observation_zone_ids.includes(zone.id)}
												onchange={() => toggleEditHypothesisZone(zone.id)}
											/>
											<span class="truncate">{zone.text || 'Untitled zone'}</span>
										</label>
									</li>
								{/each}
							</ul>
						{/if}
						{#if editingHypothesis.field_note_count > 0}
							<label for="edit-root-cause" class="text-sm text-gray-600">Root cause</label>
							<textarea
								id="edit-root-cause"
								class="my-1.5 mb-3 box-border w-full rounded border border-gray-300 p-2 text-sm"
								bind:value={editingHypothesis.root_cause}
								placeholder="What is the underlying cause?"
								rows="3"
							></textarea>
							<label for="edit-hypothesis-status" class="text-sm text-gray-600">Status</label>
							<select
								id="edit-hypothesis-status"
								class="my-1.5 mb-3 box-border w-full rounded border border-gray-300 p-2 text-sm"
								bind:value={editingHypothesis.status}
							>
								{#each Object.entries(HYPOTHESIS_STATUS_LABELS) as [value, label]}
									<option value={value}>{label}</option>
								{/each}
							</select>
							<p class="m-0 mb-3 text-xs text-gray-500">
								{editingHypothesis.field_note_count} field note(s) linked as evidence.
							</p>
						{:else}
							<p class="m-0 mb-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
								Link field notes to this hypothesis from the Field notes tab before adding a root
								cause or changing status.
							</p>
						{/if}
						{#if hypothesisError}
							<p class="m-0 mb-2 text-xs text-red-600">{hypothesisError}</p>
						{/if}
						<div class="flex gap-2">
							<button
								class="cursor-pointer rounded border-0 bg-brand-blue px-3 py-1.5 font-body text-sm text-white disabled:opacity-60"
								disabled={savingHypothesis}
								onclick={saveEditedHypothesis}
							>
								{savingHypothesis ? 'Saving…' : 'Save'}
							</button>
							<button
								class="cursor-pointer rounded border-0 bg-brand-steel px-3 py-1.5 font-body text-sm text-white hover:bg-brand-navy"
								onclick={cancelEditHypothesis}
							>
								Cancel
							</button>
						</div>
					</div>
				{:else if selectedHypothesis}
					<div class="rounded-lg border border-brand-navy/10 bg-white p-4">
						<div class="mb-3 flex items-start justify-between gap-2">
							<div class="min-w-0 flex-1">
								<span
									class="mb-2 inline-block rounded-full px-2 py-0.5 text-xs font-medium capitalize"
									class:bg-gray-100={selectedHypothesis.status === 'untested' ||
										selectedHypothesis.status === 'discarded'}
									class:text-gray-700={selectedHypothesis.status === 'untested' ||
										selectedHypothesis.status === 'discarded'}
									class:bg-green-100={selectedHypothesis.status === 'validated'}
									class:text-green-800={selectedHypothesis.status === 'validated'}
									class:bg-red-100={selectedHypothesis.status === 'invalidated'}
									class:text-red-800={selectedHypothesis.status === 'invalidated'}
								>
									{HYPOTHESIS_STATUS_LABELS[selectedHypothesis.status] ??
										selectedHypothesis.status}
								</span>
								<p class="m-0 text-sm leading-relaxed whitespace-pre-wrap">
									{selectedHypothesis.hypothesis}
								</p>
							</div>
							<div class="flex shrink-0 items-center gap-1">
								<div class="relative">
									<button
										type="button"
										class="flex h-8 w-8 cursor-pointer items-center justify-center rounded border-0 bg-transparent text-gray-600 hover:bg-gray-100"
										aria-label="More actions"
										onclick={() => (showSelectedHypothesisMenu = !showSelectedHypothesisMenu)}
									>
										<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="h-5 w-5">
											<circle cx="12" cy="5" r="1.5" />
											<circle cx="12" cy="12" r="1.5" />
											<circle cx="12" cy="19" r="1.5" />
										</svg>
									</button>
									{#if showSelectedHypothesisMenu}
										<div
											class="absolute right-0 z-20 mt-1 min-w-28 overflow-hidden rounded border border-gray-200 bg-white shadow-lg"
										>
											<button
												type="button"
												class="block w-full cursor-pointer border-0 bg-white px-3 py-2 text-left text-sm hover:bg-gray-50"
												onclick={() => {
													showSelectedHypothesisMenu = false;
													startEditHypothesis();
												}}
											>
												Edit
											</button>
											<button
												type="button"
												class="block w-full cursor-pointer border-0 bg-white px-3 py-2 text-left text-sm text-red-600 hover:bg-red-50"
												onclick={() => {
													showSelectedHypothesisMenu = false;
													deleteSelectedHypothesis();
												}}
											>
												Delete
											</button>
										</div>
									{/if}
								</div>
								<button
									type="button"
									class="cursor-pointer rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
									onclick={closeSelectedHypothesis}
								>
									Close
								</button>
							</div>
						</div>
						{#if selectedHypothesis.root_cause && (selectedHypothesis.field_note_count ?? 0) > 0}
							<div class="mb-3">
								<span class="mb-0.5 block text-xs font-semibold text-gray-500 uppercase"
									>Root cause</span
								>
								<p class="m-0 text-sm whitespace-pre-wrap">{selectedHypothesis.root_cause}</p>
							</div>
						{/if}
						<div class="mb-3">
							<span class="mb-0.5 block text-xs font-semibold text-gray-500 uppercase"
								>Observation zones</span
							>
							{#if (selectedHypothesis.observation_zone_ids ?? []).length === 0}
								<p class="m-0 text-sm text-gray-500">None linked</p>
							{:else}
								<ul class="m-0 list-disc pl-4 text-sm">
									{#each selectedHypothesis.observation_zone_ids as zoneId}
										<li>{zoneTitleById(zoneId)}</li>
									{/each}
								</ul>
							{/if}
						</div>
						<p class="m-0 mb-3 text-xs text-gray-500">
							{selectedHypothesis.field_note_count ?? 0} field note(s) linked
						</p>
						<button
							type="button"
							class="w-full cursor-pointer rounded-lg border-0 px-3 py-2.5 font-body text-sm text-white hover:opacity-90"
							style:background-color={HYPOTHESIS_COLOR}
							onclick={startEditHypothesis}
						>
							{(selectedHypothesis.field_note_count ?? 0) > 0 ? 'Review' : 'Edit'}
						</button>
					</div>
				{:else if hypotheses.length > 0}
					<div class="rounded-lg border border-brand-navy/10 bg-white p-4">
						<h3 class="m-0 mb-2 text-sm font-semibold text-gray-700">All hypotheses</h3>
						<ul class="m-0 list-none space-y-2 p-0">
							{#each hypotheses as h (h.id)}
								<li>
									<button
										type="button"
										class="w-full cursor-pointer rounded border border-gray-200 bg-gray-50 px-3 py-2 text-left hover:bg-gray-100"
										onclick={() => openHypothesis(h)}
									>
										<span class="mb-1 block text-xs capitalize text-gray-500">{h.status}</span>
										<span class="block text-sm text-brand-navy">{hypothesisLabel(h)}</span>
									</button>
								</li>
							{/each}
						</ul>
					</div>
				{/if}
			{:else if selectedLayer?.kind === 'primary' && activePrimaryTab === 'field-notes'}
				<div class="rounded-lg border border-brand-navy/10 bg-white p-4">
					<h3 class="m-0 mb-1 text-base font-semibold">Field notes</h3>
					<p class="m-0 mb-3 text-xs text-gray-500">
						Click a note on the map to view details, or add a new point.
					</p>
					<button
						type="button"
						class="flex w-full cursor-pointer items-center justify-center gap-2 rounded-lg border-0 px-3 py-2.5 font-body text-sm text-brand-navy hover:opacity-90"
						style:background-color={FIELD_NOTE_COLOR}
						onclick={startFieldNoteAdd}
					>
						<span class="text-lg leading-none">+</span> Add field note
					</button>
					{#if addingFieldNote && !pendingPoint}
						<p class="m-0 mt-3 text-xs text-amber-700">Click the map to place the field note.</p>
						<button
							type="button"
							class="mt-2 cursor-pointer border-0 bg-transparent p-0 text-sm text-gray-600 underline"
							onclick={cancelPendingForms}
						>
							Cancel
						</button>
					{/if}
				</div>

				{#if pendingPoint}
					<div class="rounded-lg border border-brand-navy/10 bg-white p-4">
						<h3 class="m-0 mb-3 text-base font-semibold">New field note</h3>
						<label for="note-title" class="text-sm text-gray-600">Title</label>
						<input
							id="note-title"
							type="text"
							class="my-1.5 mb-3 box-border w-full rounded border border-gray-300 p-2 text-sm"
							bind:value={noteTitle}
							placeholder="Note title"
						/>
						<label for="note-text" class="text-sm text-gray-600">Notes</label>
						<textarea
							id="note-text"
							class="my-1.5 mb-3 box-border w-full rounded border border-gray-300 p-2 text-sm"
							bind:value={noteText}
							placeholder="Field note…"
							rows="4"
						></textarea>
						<label for="note-photo" class="text-sm text-gray-600">Photo (max 50MB)</label>
						<input
							id="note-photo"
							type="file"
							accept="image/*"
							class="my-1.5 mb-2 block w-full text-sm"
							onchange={onFieldNotePhotoChange}
						/>
						{#if notePhotoPreview}
							<img
								src={notePhotoPreview}
								alt="Preview"
								class="mb-3 max-h-40 w-full rounded border border-gray-200 object-cover"
							/>
						{:else if notePhoto}
							<p class="m-0 mb-3 text-xs text-gray-500">Photo: {notePhoto.name}</p>
						{/if}
						<label for="note-audio" class="text-sm text-gray-600">Audio (max 50MB)</label>
						<input
							id="note-audio"
							type="file"
							accept="audio/*"
							class="my-1.5 mb-2 block w-full text-sm"
							onchange={onFieldNoteAudioChange}
						/>
						{#if noteAudioPreview}
							<audio controls src={noteAudioPreview} class="mb-3 w-full"></audio>
						{:else if noteAudio}
							<p class="m-0 mb-3 text-xs text-gray-500">Audio: {noteAudio.name}</p>
						{/if}
						{#if noteMediaError}
							<p class="m-0 mb-2 text-xs text-red-600">{noteMediaError}</p>
						{/if}
						<label for="note-hypothesis" class="text-sm text-gray-600">Link to hypothesis</label>
						<select
							id="note-hypothesis"
							class="my-1.5 mb-3 box-border w-full rounded border border-gray-300 p-2 text-sm"
							bind:value={noteHypothesisId}
						>
							<option value="">None</option>
							{#each hypotheses as h (h.id)}
								<option value={h.id}>{hypothesisLabel(h)}</option>
							{/each}
						</select>
						<div class="flex gap-2">
							<button
								class="cursor-pointer rounded border-0 bg-blue-600 px-3 py-1.5 text-sm text-white"
								onclick={submitFieldNote}
							>
								Save
							</button>
							<button
								class="cursor-pointer rounded border-0 bg-brand-steel px-3 py-1.5 font-body text-sm text-white hover:bg-brand-navy"
								onclick={cancelPendingForms}
							>
								Cancel
							</button>
						</div>
					</div>
				{:else if editingSelectedFieldNote}
					<div class="rounded-lg border border-brand-navy/10 bg-white p-4">
						<h3 class="m-0 mb-3 text-base font-semibold">Edit field note</h3>
						<label for="edit-note-title" class="text-sm text-gray-600">Title</label>
						<input
							id="edit-note-title"
							type="text"
							class="my-1.5 mb-3 box-border w-full rounded border border-gray-300 p-2 text-sm"
							bind:value={editingSelectedFieldNote.title}
							placeholder="Note title"
						/>
						<label for="edit-note-text" class="text-sm text-gray-600">Notes</label>
						<textarea
							id="edit-note-text"
							class="my-1.5 mb-4 box-border w-full rounded border border-gray-300 p-2 text-sm"
							bind:value={editingSelectedFieldNote.text}
							rows="4"
						></textarea>
						<label for="edit-note-hypothesis" class="text-sm text-gray-600">Link to hypothesis</label>
						<select
							id="edit-note-hypothesis"
							class="my-1.5 mb-4 box-border w-full rounded border border-gray-300 p-2 text-sm"
							bind:value={editingSelectedFieldNote.hypothesis_id}
						>
							<option value="">None</option>
							{#each hypotheses as h (h.id)}
								<option value={h.id}>{hypothesisLabel(h)}</option>
							{/each}
						</select>
						<div class="flex gap-2">
							<button
								class="cursor-pointer rounded border-0 bg-brand-blue px-3 py-1.5 font-body text-sm text-white disabled:opacity-60"
								disabled={savingFieldNote}
								onclick={saveSelectedFieldNote}
							>
								{savingFieldNote ? 'Saving…' : 'Save'}
							</button>
							<button
								class="cursor-pointer rounded border-0 bg-brand-steel px-3 py-1.5 font-body text-sm text-white hover:bg-brand-navy"
								onclick={cancelEditSelectedFieldNote}
							>
								Cancel
							</button>
						</div>
					</div>
				{:else if selectedFieldNote}
					{@const photoUrl = fieldNoteMediaUrl(selectedFieldNote.photo_path)}
					{@const thumbUrl =
						photoUrl && selectedFieldNote.photo_path?.match(/\.(jpe?g|png|gif|webp)$/i)
							? fieldNoteThumbnailUrl(selectedFieldNote.photo_path, 128)
							: null}
					<div class="rounded-lg border border-brand-navy/10 bg-white p-4">
						<div class="mb-3 flex items-start gap-3">
							<div class="min-w-0 flex-1">
								<div class="mb-2 flex items-start justify-between gap-2">
									<h3 class="m-0 text-base font-semibold">
										{selectedFieldNote.title?.trim() || 'Field note'}
									</h3>
									<div class="flex shrink-0 items-center gap-1">
										<div class="relative">
											<button
												type="button"
												class="flex h-8 w-8 cursor-pointer items-center justify-center rounded border-0 bg-transparent text-gray-600 hover:bg-gray-100"
												aria-label="More actions"
												onclick={() => (showSelectedFieldNoteMenu = !showSelectedFieldNoteMenu)}
											>
												<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="h-5 w-5">
													<circle cx="12" cy="5" r="1.5" />
													<circle cx="12" cy="12" r="1.5" />
													<circle cx="12" cy="19" r="1.5" />
												</svg>
											</button>
											{#if showSelectedFieldNoteMenu}
												<div
													class="absolute right-0 z-20 mt-1 min-w-28 overflow-hidden rounded border border-gray-200 bg-white shadow-lg"
												>
													<button
														type="button"
														class="block w-full cursor-pointer border-0 bg-white px-3 py-2 text-left text-sm hover:bg-gray-50"
														onclick={startEditSelectedFieldNote}
													>
														Edit
													</button>
													<button
														type="button"
														class="block w-full cursor-pointer border-0 bg-white px-3 py-2 text-left text-sm text-red-600 hover:bg-red-50"
														onclick={deleteSelectedFieldNote}
													>
														Delete
													</button>
												</div>
											{/if}
										</div>
										<button
											type="button"
											class="cursor-pointer rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
											onclick={closeSelectedFieldNote}
										>
											Close
										</button>
									</div>
								</div>
								<div class="mb-3">
									<span class="mb-0.5 block text-xs font-semibold text-gray-500 uppercase">Notes</span>
									<p class="m-0 text-sm whitespace-pre-wrap">{selectedFieldNote.text || '—'}</p>
								</div>
								{#if selectedFieldNote.hypothesis_id}
									<div class="mb-3">
										<span class="mb-0.5 block text-xs font-semibold text-gray-500 uppercase"
											>Hypothesis</span
										>
										<p class="m-0 text-sm">
											{hypothesisLabel(
												hypotheses.find((h) => h.id === selectedFieldNote.hypothesis_id)
											)}
										</p>
									</div>
								{/if}
								{#if selectedFieldNote.audio_path}
									{@const audioUrl = fieldNoteMediaUrl(selectedFieldNote.audio_path)}
									{#if audioUrl}
										<audio controls src={audioUrl} class="w-full"></audio>
									{/if}
								{/if}
							</div>
							{#if thumbUrl}
								<button
									type="button"
									class="h-20 w-20 shrink-0 cursor-pointer overflow-hidden rounded-lg border border-brand-navy/10 bg-gray-100 p-0 hover:opacity-90"
									aria-label="Expand photo"
									onclick={() => (expandedFieldNotePhoto = photoUrl)}
								>
									<img
										src={thumbUrl}
										alt=""
										class="h-full w-full object-cover"
										loading="lazy"
										decoding="async"
									/>
								</button>
							{:else if photoUrl}
								<a
									href={photoUrl}
									target="_blank"
									rel="noopener noreferrer"
									class="flex h-20 w-20 shrink-0 items-center justify-center rounded-lg border border-brand-navy/10 bg-gray-50 text-center text-xs text-blue-600 underline"
								>
									View file
								</a>
							{/if}
						</div>
					</div>
				{/if}
			{/if}
		</div>
	</aside>

	{#if expandedFieldNotePhoto}
		<button
			type="button"
			class="fixed inset-0 z-50 flex cursor-pointer items-center justify-center border-0 bg-black/70 p-4"
			aria-label="Close photo"
			onclick={() => (expandedFieldNotePhoto = null)}
		>
			<img
				src={expandedFieldNotePhoto}
				alt="Field note photo"
				class="max-h-[90vh] max-w-[90vw] rounded-lg object-contain shadow-xl"
				onclick={(e) => e.stopPropagation()}
			/>
		</button>
	{/if}
</div>

<style>
	.sidebar-section-title {
		margin: 0 0 1.25rem;
	}

	.basemap-select {
		appearance: none;
		-webkit-appearance: none;
		box-sizing: border-box;
		min-height: 2.75rem;
		padding: 0.7rem 2.25rem 0.7rem 0.9rem;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%236b7885' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 0.75rem center;
		background-size: 1rem;
	}

	.layer-row {
		display: flex;
		min-width: 0;
		align-items: center;
		gap: 0.4rem;
		padding: 0.55rem 0.5rem;
		border-radius: 0.65rem;
		border: 1px solid transparent;
		background: transparent;
		font-size: 0.875rem;
		cursor: grab;
		transition:
			background 0.15s ease,
			border-color 0.15s ease,
			box-shadow 0.15s ease,
			opacity 0.15s ease,
			transform 0.15s ease;
	}
	.layer-row:hover {
		background: rgba(15, 179, 163, 0.06);
	}
	.layer-row-selected {
		background: color-mix(in srgb, #0fb3a3 14%, white);
		border-color: color-mix(in srgb, #0fb3a3 38%, transparent);
		box-shadow: inset 3px 0 0 #0fb3a3;
	}
	.layer-row-selected .layer-label {
		font-weight: 600;
		color: #0a5c55;
	}
	.layer-row-dragging {
		opacity: 0.55;
		cursor: grabbing;
		background: color-mix(in srgb, #0fb3a3 10%, white);
		box-shadow: 0 8px 20px -10px rgba(20, 40, 60, 0.35);
		transform: scale(0.98);
	}
	.layer-row-over {
		border-color: color-mix(in srgb, #0fb3a3 45%, transparent);
		background: color-mix(in srgb, #0fb3a3 8%, white);
	}

	.layer-eye,
	.layer-eye-spacer {
		display: flex;
		height: 1.85rem;
		width: 1.85rem;
		flex-shrink: 0;
		align-items: center;
		justify-content: center;
		border: 0;
		border-radius: 0.45rem;
		background: transparent;
		padding: 0;
		color: #6b7885;
	}
	.layer-eye {
		cursor: pointer;
	}
	.layer-eye:hover:not(:disabled) {
		background: rgba(15, 179, 163, 0.12);
		color: #1a2530;
	}
	.layer-eye:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}

	.layer-label {
		min-width: 0;
		flex: 1;
		cursor: pointer;
		border: 0;
		background: transparent;
		padding: 0.15rem 0;
		text-align: left;
		color: #1a2530;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.layer-label-icon {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.layer-drag-handle {
		display: flex;
		height: 1.85rem;
		width: 1.5rem;
		flex-shrink: 0;
		align-items: center;
		justify-content: center;
		color: #9aa5b1;
		pointer-events: none;
	}
	.layer-row:hover .layer-drag-handle {
		color: #5b6b7a;
	}
</style>
