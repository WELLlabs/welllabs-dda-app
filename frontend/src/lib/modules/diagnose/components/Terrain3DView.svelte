<script>
	import { onMount, onDestroy } from 'svelte';
	import { fetchDemMesh, fetchLayerDrapeGrid, fetchVectorLayerData } from '$lib/modules/diagnose/api.js';

	/** @type {{
	 *   projectId: string,
	 *   layerId?: string,
	 *   overlayVisibility?: Record<string, boolean>
	 * }} */
	let {
		projectId,
		layerId = 'dem',
		overlayVisibility = {
			village_boundaries: true,
			canals: true,
			drainage: true
		}
	} = $props();

	let plotEl = $state(null);
	let status = $state('Loading DEM…');
	let error = $state(null);
	/** Vertical aspect — lower = gentler relief. */
	let zAspect = $state(0.08);
	/** Degrees — rotates the N needle to stay aligned with terrain north. */
	let northRotation = $state(0);

	/** @type {any} */
	let Plotly = null;
	/** @type {{
	 *   elevations: (number|null)[][],
	 *   elev_min: number,
	 *   elev_max: number,
	 *   bounds?: number[],
	 *   rows?: number,
	 *   cols?: number
	 * } | null} */
	let meshData = null;
	/** @type {{
	 *   values: (number|null)[][],
	 *   colorscale: any,
	 *   cmin: number,
	 *   cmax: number,
	 *   title: string,
	 *   value_type?: string,
	 *   category_labels?: string[]
	 * } | null} */
	let drapeData = null;
	/** @type {Record<string, any>} */
	let overlayGeo = $state({
		village_boundaries: null,
		canals: null,
		drainage: null
	});
	let disposed = false;
	let loadToken = 0;
	let lastLoadedKey = '';
	/** @type {((ev: any) => void) | null} */
	let relayoutHandler = null;

	const TERRAIN_LIGHTING = {
		ambient: 0.62,
		diffuse: 0.72,
		roughness: 0.78,
		specular: 0.04,
		fresnel: 0.03
	};
	/** Mute DEM underlay so layer colours read clearly. */
	const BASE_MUTED = [
		[0, '#d5d9dc'],
		[1, '#d5d9dc']
	];
	const OVERLAY_OPACITY = 1;
	/** Disable Plotly hover contour mesh (cyan hatch lines on the surface). */
	const NO_HOVER_CONTOURS = {
		x: { show: false, highlight: false },
		y: { show: false, highlight: false },
		z: { show: false, highlight: false }
	};
	const DEFAULT_CAMERA = {
		eye: { x: 1.15, y: -1.05, z: 0.7 },
		center: { x: 0, y: 0, z: 0 },
		up: { x: 0, y: 0, z: 1 }
	};

	const OVERLAY_STYLE = {
		village_boundaries: { color: '#00306d', width: 2.5, name: 'Village boundaries', kind: 'dots' },
		canals: { color: '#b5523a', width: 4, name: 'Canals', kind: 'lines' },
		drainage: { color: '#1c75e9', width: 3, name: 'Streams', kind: 'lines' }
	};

	/** Avoid Plotly.react fighting the camera after the first paint. */
	let cameraInitialized = false;
	/** @type {string} */
	let lastOverlayKey = '';
	let cameraFixGuard = false;


	async function loadPlotly() {
		if (typeof window !== 'undefined' && window.Plotly) {
			return window.Plotly;
		}
		await new Promise((resolve, reject) => {
			const existing = document.querySelector('script[data-plotly-cdn]');
			if (existing) {
				existing.addEventListener('load', () => resolve());
				existing.addEventListener('error', () => reject(new Error('Plotly CDN failed')));
				if (window.Plotly) resolve();
				return;
			}
			const s = document.createElement('script');
			s.src = 'https://cdn.plot.ly/plotly-2.35.2.min.js';
			s.async = true;
			s.dataset.plotlyCdn = '1';
			s.onload = () => resolve();
			s.onerror = () => reject(new Error('Failed to load Plotly from CDN'));
			document.head.appendChild(s);
		});
		if (!window.Plotly) throw new Error('Plotly not available');
		return window.Plotly;
	}

	/**
	 * Flip rows so north increases along Plotly y (clinton_code).
	 * @param {(number|null)[][]} grid
	 */
	function flipud(grid) {
		return grid
			.map((row) => row.map((v) => (v == null || !Number.isFinite(v) ? null : v)))
			.slice()
			.reverse();
	}

	/**
	 * Clinton: z_drape = z + relief*0.005 where layer is valid; null elsewhere (holes).
	 * @param {(number|null)[][]} z
	 * @param {(number|null)[][]} surfacecolor
	 * @param {number} lift
	 */
	function buildDrapeZ(z, surfacecolor, lift) {
		return z.map((row, r) =>
			row.map((elev, c) => {
				const sc = surfacecolor[r]?.[c];
				if (sc == null || !Number.isFinite(sc) || elev == null || !Number.isFinite(elev)) {
					return null;
				}
				return elev + lift;
			})
		);
	}

	/**
	 * @param {{ eye?: { x: number, y: number, z: number }, center?: { x: number, y: number, z: number }, up?: { x: number, y: number, z: number } }} camera
	 */
	function sanitizeCamera(camera) {
		const next = {
			eye: { ...DEFAULT_CAMERA.eye, ...(camera?.eye || {}) },
			center: { ...DEFAULT_CAMERA.center, ...(camera?.center || {}) },
			up: { ...DEFAULT_CAMERA.up, ...(camera?.up || {}) }
		};
		for (const axis of /** @type {const} */ (['x', 'y', 'z'])) {
			if (!Number.isFinite(Number(next.eye[axis]))) next.eye[axis] = DEFAULT_CAMERA.eye[axis];
			if (!Number.isFinite(Number(next.center[axis]))) next.center[axis] = DEFAULT_CAMERA.center[axis];
			if (!Number.isFinite(Number(next.up[axis]))) next.up[axis] = DEFAULT_CAMERA.up[axis];
		}
		// Keep upright turntable — don't let reset bury the camera under the terrain.
		if (next.eye.z < 0.12) next.eye.z = 0.12;
		next.up = { x: 0, y: 0, z: 1 };
		return next;
	}

	/**
	 * @param {{ eye?: { x: number, y: number, z: number }, center?: { x: number, y: number, z: number } }} camera
	 */
	function compassRotationFromCamera(camera) {
		if (!camera?.eye) return northRotation;
		const cx = camera.center?.x ?? 0;
		const cy = camera.center?.y ?? 0;
		const dx = Number(camera.eye.x) - Number(cx);
		const dy = Number(camera.eye.y) - Number(cy);
		if (!Number.isFinite(dx) || !Number.isFinite(dy) || (Math.abs(dx) < 1e-9 && Math.abs(dy) < 1e-9)) {
			return northRotation;
		}
		// Match clinton_code: north increases along +y after flipud.
		return 180 - (Math.atan2(dx, dy) * 180) / Math.PI;
	}

	async function reorientCamera() {
		if (!plotEl || !Plotly) return;
		const camera = sanitizeCamera(DEFAULT_CAMERA);
		try {
			await Plotly.relayout(plotEl, {
				'scene.camera': camera,
				'scene.dragmode': 'turntable',
				'scene.aspectmode': 'manual',
				'scene.aspectratio': { x: 1, y: 1, z: Number(zAspect) || 0.08 }
			});
			northRotation = compassRotationFromCamera(camera);
			status = 'Reoriented north · drag to rotate · scroll to zoom';
		} catch (err) {
			console.warn('Could not reorient camera', err);
		}
	}

	function bindCompass() {
		if (!plotEl || !Plotly) return;
		if (relayoutHandler && plotEl.removeListener) {
			try {
				plotEl.removeListener('plotly_relayout', relayoutHandler);
			} catch {
				/* ignore */
			}
		}
		relayoutHandler = (ev) => {
			const cam =
				ev?.['scene.camera'] ||
				plotEl?._fullLayout?.scene?.camera ||
				null;
			if (cam) northRotation = compassRotationFromCamera(cam);

			if (cameraFixGuard || !Plotly || !plotEl) return;

			const current = plotEl._fullLayout?.scene?.camera;
			const dragmode = plotEl._fullLayout?.scene?.dragmode;
			/** @type {Record<string, any>} */
			const updates = {};
			if (dragmode && dragmode !== 'turntable') {
				updates['scene.dragmode'] = 'turntable';
			}
			if (current) {
				const upBroken =
					!current.up ||
					Math.abs(Number(current.up.z) - 1) > 0.05 ||
					Math.abs(Number(current.up.x)) > 0.05 ||
					Math.abs(Number(current.up.y)) > 0.05 ||
					Number(current.eye?.z) < 0.12;
				if (upBroken) {
					const fixed = sanitizeCamera(current);
					updates['scene.camera'] = fixed;
					northRotation = compassRotationFromCamera(fixed);
				}
			}
			if (!Object.keys(updates).length) return;
			cameraFixGuard = true;
			Plotly.relayout(plotEl, updates)
				.catch(() => {})
				.finally(() => {
					cameraFixGuard = false;
				});
		};
		if (typeof plotEl.on === 'function') {
			plotEl.on('plotly_relayout', relayoutHandler);
		}
		const initial = plotEl._fullLayout?.scene?.camera;
		if (initial) northRotation = compassRotationFromCamera(initial);
	}

	/**
	 * @param {(number|null)[][]} zFlipped
	 * @param {number} plotX
	 * @param {number} plotY
	 */
	function sampleZ(zFlipped, plotX, plotY) {
		const rows = zFlipped.length;
		const cols = zFlipped[0]?.length ?? 0;
		if (rows < 1 || cols < 1) return null;
		if (plotX < 0 || plotY < 0 || plotX > cols - 1 || plotY > rows - 1) return null;
		const x0 = Math.floor(plotX);
		const y0 = Math.floor(plotY);
		const x1 = Math.min(cols - 1, x0 + 1);
		const y1 = Math.min(rows - 1, y0 + 1);
		const tx = plotX - x0;
		const ty = plotY - y0;
		const v00 = zFlipped[y0]?.[x0];
		const v10 = zFlipped[y0]?.[x1];
		const v01 = zFlipped[y1]?.[x0];
		const v11 = zFlipped[y1]?.[x1];
		const vals = [v00, v10, v01, v11].filter((v) => v != null && Number.isFinite(v));
		if (!vals.length) return null;
		const a = v00 != null && Number.isFinite(v00) ? v00 : vals[0];
		const b = v10 != null && Number.isFinite(v10) ? v10 : a;
		const c = v01 != null && Number.isFinite(v01) ? v01 : a;
		const d = v11 != null && Number.isFinite(v11) ? v11 : a;
		return (1 - tx) * (1 - ty) * a + tx * (1 - ty) * b + (1 - tx) * ty * c + tx * ty * d;
	}

	/**
	 * @param {number[]} bounds [minx,miny,maxx,maxy]
	 * @param {number} rows
	 * @param {number} cols
	 * @param {number} lon
	 * @param {number} lat
	 */
	function lonLatToPlot(bounds, rows, cols, lon, lat) {
		const [minx, miny, maxx, maxy] = bounds;
		const dx = maxx - minx || 1;
		const dy = maxy - miny || 1;
		const plotX = ((lon - minx) / dx) * (cols - 1);
		// After flipud, Plotly y increases with latitude (north).
		const plotY = ((lat - miny) / dy) * (rows - 1);
		return [plotX, plotY];
	}

	/**
	 * Densify a ring/line into plot XYZ with null breaks between parts.
	 * @param {number[][]} coords
	 * @param {(number|null)[][]} zFlipped
	 * @param {number[]} bounds
	 * @param {number} lift
	 * @param {number} step
	 */
	function drapeCoords(coords, zFlipped, bounds, lift, step = 1.6) {
		const rows = zFlipped.length;
		const cols = zFlipped[0]?.length ?? 0;
		/** @type {(number|null)[]} */
		const xs = [];
		/** @type {(number|null)[]} */
		const ys = [];
		/** @type {(number|null)[]} */
		const zs = [];
		let prev = null;
		for (const pt of coords) {
			const lon = pt[0];
			const lat = pt[1];
			if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;
			const [plotX, plotY] = lonLatToPlot(bounds, rows, cols, lon, lat);
			if (prev == null) {
				const z = sampleZ(zFlipped, plotX, plotY);
				if (z != null) {
					xs.push(plotX);
					ys.push(plotY);
					zs.push(z + lift);
					prev = [plotX, plotY];
				}
				continue;
			}
			const [px, py] = prev;
			const dist = Math.hypot(plotX - px, plotY - py);
			const n = Math.max(1, Math.ceil(dist / step));
			for (let i = 1; i <= n; i++) {
				const t = i / n;
				const x = px + (plotX - px) * t;
				const y = py + (plotY - py) * t;
				const z = sampleZ(zFlipped, x, y);
				if (z == null) {
					xs.push(null);
					ys.push(null);
					zs.push(null);
					prev = null;
					break;
				}
				xs.push(x);
				ys.push(y);
				zs.push(z + lift);
				prev = [x, y];
			}
		}
		xs.push(null);
		ys.push(null);
		zs.push(null);
		return { xs, ys, zs };
	}

	/**
	 * @param {any} geom
	 * @param {(number|null)[][]} zFlipped
	 * @param {number[]} bounds
	 * @param {number} lift
	 * @param {'dots'|'lines'} kind
	 */
	function drapeGeometry(geom, zFlipped, bounds, lift, kind) {
		/** @type {(number|null)[]} */
		const xs = [];
		/** @type {(number|null)[]} */
		const ys = [];
		/** @type {(number|null)[]} */
		const zs = [];
		if (!geom) return { xs, ys, zs };

		const pushPart = (coords) => {
			const part = drapeCoords(coords, zFlipped, bounds, lift, kind === 'dots' ? 2.2 : 1.4);
			xs.push(...part.xs);
			ys.push(...part.ys);
			zs.push(...part.zs);
		};

		const walk = (g) => {
			if (!g) return;
			if (g.type === 'LineString') pushPart(g.coordinates);
			else if (g.type === 'MultiLineString') g.coordinates.forEach(pushPart);
			else if (g.type === 'Polygon') pushPart(g.coordinates[0] || []);
			else if (g.type === 'MultiPolygon') {
				for (const poly of g.coordinates) pushPart(poly[0] || []);
			} else if (g.type === 'GeometryCollection') {
				for (const child of g.geometries || []) walk(child);
			}
		};
		walk(geom);
		return { xs, ys, zs };
	}

	/**
	 * @param {(number|null)[][]} zFlipped
	 * @param {number} relief
	 */
	function buildOverlayTraces(zFlipped, relief) {
		/** @type {Record<string, any>[]} */
		const traces = [];
		const bounds = meshData?.bounds;
		if (!bounds || bounds.length !== 4) return traces;

		for (const id of /** @type {const} */ (['village_boundaries', 'canals', 'drainage'])) {
			if (overlayVisibility?.[id] === false) continue;
			const fc = overlayGeo[id];
			const style = OVERLAY_STYLE[id];
			if (!fc?.features?.length || !style) continue;

			const lift =
				id === 'village_boundaries' ? relief * 0.035 : relief * 0.02;
			/** @type {(number|null)[]} */
			const xs = [];
			/** @type {(number|null)[]} */
			const ys = [];
			/** @type {(number|null)[]} */
			const zs = [];

			for (const f of fc.features) {
				const part = drapeGeometry(f.geometry, zFlipped, bounds, lift, style.kind);
				xs.push(...part.xs);
				ys.push(...part.ys);
				zs.push(...part.zs);
			}

			const finite = xs.some((v) => v != null && Number.isFinite(v));
			if (!finite) continue;

			if (style.kind === 'dots') {
				traces.push({
					type: 'scatter3d',
					mode: 'markers',
					x: xs,
					y: ys,
					z: zs,
					marker: { size: 1.6, color: style.color, opacity: 0.85 },
					name: style.name,
					showlegend: false,
					hoverinfo: 'skip'
				});
			} else {
				traces.push({
					type: 'scatter3d',
					mode: 'lines',
					x: xs,
					y: ys,
					z: zs,
					line: { color: style.color, width: style.width },
					name: style.name,
					showlegend: false,
					hoverinfo: 'skip'
				});
			}
		}
		return traces;
	}

	async function render() {
		if (!plotEl || !meshData || !Plotly) return;
		const z = flipud(meshData.elevations);
		const relief = Math.max(meshData.elev_max - meshData.elev_min, 1);
		const useDrape = Boolean(
			drapeData && layerId && layerId !== 'dem' && drapeData.value_type !== 'dem'
		);

		const hiddenAxis = {
			visible: false,
			title: '',
			showgrid: false,
			showspikes: false,
			showticklabels: false,
			zeroline: false,
			showbackground: false,
			showline: false,
			ticks: ''
		};

		/** @type {Record<string, any>[]} */
		const traces = [
			{
				type: 'surface',
				z,
				colorscale: useDrape ? BASE_MUTED : 'Earth',
				cmin: meshData.elev_min,
				cmax: meshData.elev_max,
				showscale: !useDrape,
				colorbar: useDrape
					? undefined
					: {
							title: { text: 'Elevation (m)', side: 'right' },
							thickness: 14,
							len: 0.55,
							x: 1.02
						},
				lighting: TERRAIN_LIGHTING,
				lightposition: { x: 1000, y: 1000, z: 2000 },
				contours: NO_HOVER_CONTOURS,
				hoverinfo: useDrape ? 'skip' : 'z',
				hovertemplate: useDrape ? undefined : 'Elev %{z:.1f} m<extra></extra>',
				name: 'Base Terrain',
				showlegend: false
			}
		];

		if (useDrape) {
			const surfacecolor = flipud(drapeData.values);
			const lift = relief * 0.01;
			const zDrape = buildDrapeZ(z, surfacecolor, lift);
			const labels = drapeData.category_labels || [];
			const isCat = drapeData.value_type === 'categorical' && labels.length > 0;
			const filled = surfacecolor.some((row) => row.some((v) => v != null && Number.isFinite(v)));

			/** @type {Record<string, any>} */
			const colorbar = {
				title: { text: drapeData.title, side: 'top' },
				thickness: 14,
				len: 0.35,
				x: 0.02,
				y: 0.22,
				bgcolor: 'rgba(255,255,255,0.88)',
				bordercolor: 'rgba(31,54,43,0.25)',
				borderwidth: 1
			};
			if (isCat) {
				colorbar.tickvals = labels.map((_, i) => i);
				colorbar.ticktext = labels;
			}

			if (filled) {
				traces.push({
					type: 'surface',
					z: zDrape,
					surfacecolor,
					colorscale: drapeData.colorscale,
					cmin: drapeData.cmin,
					cmax: drapeData.cmax,
					showscale: true,
					colorbar,
					opacity: OVERLAY_OPACITY,
					lighting: TERRAIN_LIGHTING,
					lightposition: { x: 1000, y: 1000, z: 2000 },
					contours: NO_HOVER_CONTOURS,
					hoverinfo: 'text',
					hovertemplate: `${drapeData.title}: %{surfacecolor}<br>Elev %{z:.1f} m<extra></extra>`,
					name: drapeData.title,
					showlegend: false
				});
			}
		}

		traces.push(...buildOverlayTraces(z, relief));

		/** @type {Record<string, any>} */
		const scene = {
			xaxis: hiddenAxis,
			yaxis: hiddenAxis,
			zaxis: {
				...hiddenAxis,
				range: [meshData.elev_min - relief * 0.02, meshData.elev_max + relief * 0.05]
			},
			aspectratio: { x: 1, y: 1, z: Number(zAspect) || 0.08 },
			aspectmode: 'manual',
			dragmode: 'turntable',
			bgcolor: 'rgba(245, 247, 244, 0.35)'
		};
		// Only set camera on first paint — later reacts must not clobber user rotation
		// (and must not fight Plotly's "last saved state" reset).
		if (!cameraInitialized) {
			scene.camera = sanitizeCamera(DEFAULT_CAMERA);
		}

		const layout = {
			margin: { l: 0, r: 40, b: 0, t: 0 },
			paper_bgcolor: 'rgba(230, 233, 235, 1)',
			font: { family: 'Segoe UI, system-ui, sans-serif', size: 11, color: '#00306d' },
			scene,
			uirevision: `terrain-${layerId || 'dem'}`
		};

		const config = {
			responsive: true,
			displayModeBar: true,
			displaylogo: false,
			modeBarButtonsToRemove: [
				'toImage',
				'sendDataToCloud',
				'hoverClosest3d',
				'orbitRotation',
				'tableRotation',
				// These leave turntable drag broken; compass click reorients instead.
				'resetCameraLastSave3d',
				'resetCameraDefault3d'
			]
		};

		await Plotly.react(plotEl, traces, layout, config);
		cameraInitialized = true;
		bindCompass();
		const cam = plotEl._fullLayout?.scene?.camera || DEFAULT_CAMERA;
		northRotation = compassRotationFromCamera(cam);

		if (useDrape) {
			const filled = flipud(drapeData.values).some((row) =>
				row.some((v) => v != null && Number.isFinite(v))
			);
			status = filled
				? `${drapeData.title} draped · drag to rotate · scroll to zoom`
				: `${drapeData.title}: no coverage in this watershed`;
		} else {
			status = 'DEM · drag to rotate · scroll to zoom';
		}
	}

	async function loadOverlays(pid) {
		const ids = ['village_boundaries', 'canals', 'drainage'];
		const results = await Promise.allSettled(ids.map((id) => fetchVectorLayerData(id, pid)));
		/** @type {Record<string, any>} */
		const next = { ...overlayGeo };
		results.forEach((res, i) => {
			const id = ids[i];
			if (res.status === 'fulfilled' && res.value?.features) {
				next[id] = res.value;
			} else {
				next[id] = next[id] ?? null;
				if (res.status === 'rejected') {
					console.warn(`3D overlay ${id} failed`, res.reason);
				}
			}
		});
		overlayGeo = next;
	}

	async function loadAll(pid, lid) {
		const key = `${pid}:${lid || 'dem'}`;
		if (key === lastLoadedKey && meshData) {
			await render();
			return;
		}
		const token = ++loadToken;
		error = null;
		status = 'Loading DEM mesh…';
		drapeData = null;
		cameraInitialized = false;
		try {
			Plotly = await loadPlotly();
			meshData = await fetchDemMesh(pid);
			if (disposed || token !== loadToken) return;

			status = 'Loading overlays…';
			await loadOverlays(pid);
			if (disposed || token !== loadToken) return;

			if (lid && lid !== 'dem') {
				status = `Draping ${lid}…`;
				try {
					drapeData = await fetchLayerDrapeGrid(lid, pid);
				} catch (drapeErr) {
					console.warn('Drape failed, showing DEM only', drapeErr);
					drapeData = null;
					error = drapeErr instanceof Error ? drapeErr.message : String(drapeErr);
				}
			} else {
				drapeData = null;
			}
			if (disposed || token !== loadToken) return;
			lastLoadedKey = key;
			status = 'Rendering…';
			await render();
		} catch (err) {
			if (token !== loadToken) return;
			error = err instanceof Error ? err.message : String(err);
			status = 'Failed to load terrain';
		}
	}

	onMount(() => {
		disposed = false;
	});

	onDestroy(() => {
		disposed = true;
		if (plotEl && relayoutHandler) {
			try {
				plotEl.removeEventListener?.('plotly_relayout', relayoutHandler);
				plotEl.removeListener?.('plotly_relayout', relayoutHandler);
			} catch {
				/* ignore */
			}
		}
		if (plotEl && Plotly) {
			try {
				Plotly.purge(plotEl);
			} catch {
				/* ignore */
			}
		}
	});

	$effect(() => {
		const pid = projectId;
		const lid = layerId || 'dem';
		if (!pid || !plotEl) return;
		loadAll(pid, lid);
	});

	$effect(() => {
		const za = Number(zAspect) || 0.08;
		if (!plotEl || !Plotly || !meshData) return;
		try {
			Plotly.relayout(plotEl, { 'scene.aspectratio': { x: 1, y: 1, z: za } });
		} catch {
			/* plot not ready yet */
		}
	});

	$effect(() => {
		const key = [
			overlayVisibility?.village_boundaries ? '1' : '0',
			overlayVisibility?.canals ? '1' : '0',
			overlayVisibility?.drainage ? '1' : '0'
		].join('');
		if (!plotEl || !Plotly || !meshData) return;
		if (key === lastOverlayKey) return;
		lastOverlayKey = key;
		render();
	});
</script>

<div class="terrain3d relative h-full w-full overflow-hidden bg-[#e6e9eb]">
	<div bind:this={plotEl} class="h-full w-full"></div>

	<!-- Status sits below the 2D/3D mode toggle (top-left) to avoid overlap -->
	<div
		class="pointer-events-none absolute top-14 left-3 z-10 max-w-[min(280px,55vw)] rounded-lg border border-brand-navy/10 bg-white/90 px-2.5 py-1.5 text-xs text-brand-navy shadow-sm backdrop-blur-sm"
	>
		{#if error}
			<span class="text-red-700">{error}</span>
		{:else}
			{status}
		{/if}
	</div>

	<label
		class="absolute bottom-3 left-3 z-10 flex items-center gap-2 rounded-lg border border-brand-navy/10 bg-white/90 px-2.5 py-1.5 text-xs text-brand-navy shadow-sm backdrop-blur-sm"
	>
		<span class="whitespace-nowrap opacity-70">Relief</span>
		<input
			type="range"
			min="0.04"
			max="0.22"
			step="0.01"
			bind:value={zAspect}
			class="w-24 accent-brand-navy"
		/>
		<span class="w-8 tabular-nums opacity-70">{Number(zAspect).toFixed(2)}</span>
	</label>

	<!-- Compass + legend: bottom-right, clear of Plotly modebar (top-right) -->
	<div class="absolute right-3 bottom-3 z-10 flex flex-col items-end gap-2">
		<button
			type="button"
			class="flex cursor-pointer flex-col items-center gap-1 rounded-lg border-0 bg-transparent p-0"
			title="Click to reorient north"
			aria-label="Reorient map north"
			onclick={reorientCamera}
		>
			<div
				class="relative flex h-14 w-14 items-center justify-center rounded-full border border-brand-navy/15 bg-white/95 shadow-md backdrop-blur-sm transition hover:border-brand-navy/40 hover:shadow-lg"
			>
				<div
					class="absolute inset-0 flex items-center justify-center"
					style="transform: rotate({northRotation}deg)"
				>
					<svg viewBox="0 0 40 40" class="h-10 w-10" aria-hidden="true">
						<path d="M20 6 L24 22 L20 19 L16 22 Z" fill="#b91c1c" />
						<path d="M20 34 L24 22 L20 25 L16 22 Z" fill="#00306d" />
					</svg>
				</div>
			</div>
			<span
				class="rounded bg-white/90 px-1.5 py-0.5 text-[10px] font-semibold text-brand-navy shadow-sm"
				>North · click to reset</span
			>
		</button>

		<div
			class="pointer-events-none rounded-lg border border-brand-navy/10 bg-white/90 px-2.5 py-1.5 text-[10px] text-brand-navy shadow-sm backdrop-blur-sm"
		>
			<ul class="m-0 list-none space-y-1 p-0">
				<li class="flex items-center gap-1.5">
					<span class="inline-block h-2 w-2 rounded-full bg-[#00306d]"></span> Villages
				</li>
				<li class="flex items-center gap-1.5">
					<span class="inline-block h-0.5 w-3 bg-[#1c75e9]"></span> Streams
				</li>
				<li class="flex items-center gap-1.5">
					<span class="inline-block h-0.5 w-3 bg-[#b5523a]"></span> Canals
				</li>
			</ul>
		</div>
	</div>
</div>
