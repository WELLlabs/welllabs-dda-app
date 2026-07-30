<script>
	import { onMount, onDestroy } from 'svelte';
	import { fetchDemMesh, fetchLayerDrapeGrid } from '$lib/modules/diagnose/api.js';

	/** @type {{ projectId: string, layerId?: string }} */
	let { projectId, layerId = 'dem' } = $props();

	let plotEl = $state(null);
	let status = $state('Loading DEM…');
	let error = $state(null);
	/** Vertical aspect — lower = gentler relief. */
	let zAspect = $state(0.08);

	/** @type {any} */
	let Plotly = null;
	/** @type {{ elevations: (number|null)[][], elev_min: number, elev_max: number } | null} */
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
	let disposed = false;
	let loadToken = 0;
	let lastLoadedKey = '';

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
				contours: { z: { show: false } },
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
					contours: { z: { show: false } },
					hovertemplate: `${drapeData.title}: %{surfacecolor}<br>Elev %{z:.1f} m<extra></extra>`,
					name: drapeData.title,
					showlegend: false
				});
			}
		}

		const layout = {
			margin: { l: 0, r: 40, b: 0, t: 0 },
			paper_bgcolor: 'rgba(230, 233, 235, 1)',
			font: { family: 'Segoe UI, system-ui, sans-serif', size: 11, color: '#00306d' },
			scene: {
				xaxis: hiddenAxis,
				yaxis: hiddenAxis,
				zaxis: {
					...hiddenAxis,
					range: [meshData.elev_min - relief * 0.02, meshData.elev_max + relief * 0.05]
				},
				aspectratio: { x: 1, y: 1, z: Number(zAspect) || 0.08 },
				aspectmode: 'manual',
				dragmode: 'turntable',
				camera: {
					eye: { x: 1.15, y: -1.05, z: 0.7 },
					center: { x: 0, y: 0, z: 0 },
					up: { x: 0, y: 0, z: 1 }
				},
				bgcolor: 'rgba(245, 247, 244, 0.35)'
			},
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
				'tableRotation'
			]
		};

		await Plotly.react(plotEl, traces, layout, config);
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
		try {
			Plotly = await loadPlotly();
			meshData = await fetchDemMesh(pid);
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
		if (!plotEl || !Plotly) return;
		try {
			Plotly.relayout(plotEl, { 'scene.aspectratio': { x: 1, y: 1, z: za } });
		} catch {
			/* plot not ready yet */
		}
	});
</script>

<div class="terrain3d relative h-full w-full overflow-hidden bg-[#e6e9eb]">
	<div bind:this={plotEl} class="h-full w-full"></div>

	<div
		class="pointer-events-none absolute top-3 left-3 z-10 rounded-lg border border-brand-navy/10 bg-white/90 px-2.5 py-1.5 text-xs text-brand-navy shadow-sm backdrop-blur-sm"
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
</div>
