<script>
	import { onDestroy, onMount } from 'svelte';
	import { fetchProjectStats } from '$lib/modules/design/api.js';

	/**
	 * Watershed-level summary for a Design project: AOI details plus slope, land-use
	 * and drainage stats from the same three layers the suitability engine reads.
	 * @type {{ project: any, onclose?: () => void }}
	 */
	let { project, onclose } = $props();

	const SLOPE_COLORS = ['#d9f0d3', '#a6dba0', '#f6d47a', '#ef8a47', '#c2410c'];
	const LULC_COLORS = {
		1: '#b91c1c',
		2: '#f2c94c',
		3: '#e0a526',
		4: '#c98a14',
		5: '#8c6d1f',
		6: '#d6c7a1',
		7: '#7bbf6a',
		8: '#0f5d2e',
		9: '#2f8f4e',
		10: '#9cc28a',
		11: '#4f9e9a',
		12: '#c5dd8a',
		13: '#a88b5a',
		14: '#bfb5a4',
		15: '#e7dcc4',
		16: '#1b75e0',
		17: '#6aa8ee',
		18: '#e8f1fb'
	};
	const ORDER_COLORS = ['#c9defb', '#94bdf3', '#5e9be9', '#2f78d8', '#1a5bb0', '#0d3f80', '#062a59'];
	const LULC_TOP = 6;

	let stats = $state(/** @type {any} */ (null));
	let loading = $state(true);
	let loadError = $state('');
	let showAllLulc = $state(false);
	let copied = $state(false);
	/** @type {AbortController | null} */
	let abort = null;

	const SOURCE_LABEL = {
		point: 'Micro-watershed (map point)',
		village: 'Village',
		custom: 'Uploaded boundary',
		diagnosis: 'Imported from PD project'
	};

	async function load() {
		abort?.abort();
		abort = new AbortController();
		const { signal } = abort;
		loading = true;
		loadError = '';
		try {
			const data = await fetchProjectStats(project.id, { signal });
			if (signal.aborted) return;
			stats = data;
		} catch (err) {
			if (signal.aborted || err?.name === 'AbortError') return;
			loadError = err instanceof Error ? err.message : String(err);
		} finally {
			if (!signal.aborted) loading = false;
		}
	}

	onMount(load);
	onDestroy(() => abort?.abort());

	const ws = $derived(stats?.watershed ?? null);
	const lulcRows = $derived(
		stats?.lulc?.status === 'ok' ? (showAllLulc ? stats.lulc.classes : stats.lulc.classes.slice(0, LULC_TOP)) : []
	);

	function num(v, digits = 0) {
		if (v == null || Number.isNaN(v)) return '—';
		return Number(v).toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: 0 });
	}

	function fmtDate(iso) {
		if (!iso) return '—';
		try {
			return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
		} catch {
			return iso;
		}
	}

	async function copyCentroid() {
		if (!ws) return;
		try {
			await navigator.clipboard.writeText(`${ws.centroid.lat.toFixed(6)}, ${ws.centroid.lng.toFixed(6)}`);
			copied = true;
			setTimeout(() => (copied = false), 1500);
		} catch {
			// Clipboard blocked — the value is still visible to select by hand.
		}
	}
</script>

<aside class="stats flex min-h-0 w-full flex-col border-brand-navy/10 bg-[#f7f9fc] md:w-[18rem] md:shrink-0 md:border-r" aria-label="Watershed summary">
	<div class="flex items-start justify-between gap-2 border-b border-brand-navy/10 bg-white px-4 py-3">
		<div class="min-w-0">
			<h2 class="m-0 font-headline text-base font-semibold text-brand-navy">Watershed</h2>
			<p class="m-0 mt-0.5 truncate text-xs text-brand-steel" title={project.aoi_name || project.name}>
				{project.aoi_name || project.name}
			</p>
		</div>
		{#if onclose}
			<button type="button" class="icon-btn" onclick={onclose} aria-label="Hide watershed summary" title="Hide summary">
				<svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true"><path d="M12.5 4.5 7 10l5.5 5.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" /></svg>
			</button>
		{/if}
	</div>

	<div class="min-h-0 flex-1 overflow-y-auto px-4 py-3">
		<!-- Watershed info: known from the project row, so it shows before the layers finish. -->
		<section class="card">
			<h3>Area of interest</h3>
			<dl class="kv">
				<dt>Source</dt>
				<dd>{SOURCE_LABEL[project.aoi_source] ?? project.aoi_source ?? '—'}</dd>
				{#if project.source_diagnosis_name}
					<dt>PD project</dt>
					<dd>{project.source_diagnosis_name}</dd>
				{/if}
				<dt>Area</dt>
				<dd>{num(ws?.area_ha ?? project.area_ha)} ha <span class="sub">({num((ws?.area_ha ?? project.area_ha) / 100, 2)} km²)</span></dd>
				{#if ws}
					<dt>Perimeter</dt>
					<dd>{num(ws.perimeter_km, 1)} km</dd>
					<dt>Centroid</dt>
					<dd>
						<button type="button" class="link" onclick={copyCentroid} title="Copy lat, lng">
							{ws.centroid.lat.toFixed(5)}, {ws.centroid.lng.toFixed(5)}
						</button>
						{#if copied}<span class="sub"> copied</span>{/if}
					</dd>
					{#if ws.parts > 1}
						<dt>Parts</dt>
						<dd>{ws.parts} polygons</dd>
					{/if}
					<dt>Grid</dt>
					<dd>~{num(ws.grid_res_m)} m cells</dd>
				{/if}
				<dt>Created</dt>
				<dd>{fmtDate(project.created_at)}</dd>
			</dl>
		</section>

		{#if loading}
			<div class="flex items-center gap-2 py-4 text-sm text-brand-steel" role="status">
				<span class="h-4 w-4 animate-spin rounded-full border-2 border-brand-navy/20 border-t-[#1b75e0]" aria-hidden="true"></span>
				Reading slope, land use and drainage…
			</div>
		{:else if loadError}
			<div class="py-4 text-sm">
				<p class="m-0 text-red-600">{loadError}</p>
				<button type="button" class="mt-2 cursor-pointer rounded border border-brand-navy/20 bg-white px-3 py-1 text-sm" onclick={load}>Retry</button>
			</div>
		{:else if stats}
			<!-- Slope -->
			<section class="card">
				<h3>Slope</h3>
				{#if stats.slope.status === 'ok'}
					<div class="tiles">
						<div><b>{num(stats.slope.mean_pct, 1)}%</b><span>mean</span></div>
						<div><b>{num(stats.slope.median_pct, 1)}%</b><span>median</span></div>
						<div><b>{num(stats.slope.p90_pct, 1)}%</b><span>90th pct</span></div>
					</div>
					<div class="stack" role="img" aria-label="Share of area by slope class">
						{#each stats.slope.classes as c, i (c.label)}
							{#if c.pct > 0}<span style:width="{c.pct}%" style:background-color={SLOPE_COLORS[i]} title="{c.label} {c.range}: {c.pct}%"></span>{/if}
						{/each}
					</div>
					<ul class="rows">
						{#each stats.slope.classes as c, i (c.label)}
							<li>
								<span class="sw" style:background-color={SLOPE_COLORS[i]}></span>
								<span class="lbl">{c.label} <span class="sub">{c.range}</span></span>
								<span class="val">{c.pct}%</span>
							</li>
						{/each}
					</ul>
				{:else}
					<p class="na">{stats.slope.message}</p>
				{/if}
			</section>

			<!-- Land use -->
			<section class="card">
				<h3>Land use <span class="sub">(LULC 250k)</span></h3>
				{#if stats.lulc.status === 'ok'}
					<div class="stack" role="img" aria-label="Share of area by land-use class">
						{#each stats.lulc.classes as c (c.code)}
							<span style:width="{c.pct}%" style:background-color={LULC_COLORS[c.code] ?? '#9aa5b1'} title="{c.label}: {c.pct}%"></span>
						{/each}
					</div>
					<ul class="rows">
						{#each lulcRows as c (c.code)}
							<li>
								<span class="sw" style:background-color={LULC_COLORS[c.code] ?? '#9aa5b1'}></span>
								<span class="lbl">{c.label}</span>
								<span class="val">{c.pct}% <span class="sub">· {num(c.ha)} ha</span></span>
							</li>
						{/each}
					</ul>
					{#if stats.lulc.classes.length > LULC_TOP}
						<button type="button" class="link mt-1" onclick={() => (showAllLulc = !showAllLulc)}>
							{showAllLulc ? 'Show fewer' : `Show all ${stats.lulc.classes.length} classes`}
						</button>
					{/if}
				{:else}
					<p class="na">{stats.lulc.message}</p>
				{/if}
			</section>

			<!-- Drainage -->
			<section class="card">
				<h3>Drainage</h3>
				{#if stats.drainage.status === 'ok'}
					<div class="tiles">
						<div><b>{num(stats.drainage.total_km, 1)}</b><span>km streams</span></div>
						<div><b>{num(stats.drainage.density_km_per_km2, 2)}</b><span>km / km²</span></div>
						<div><b>{stats.drainage.max_order ?? '—'}</b><span>max order</span></div>
					</div>
					{#if stats.drainage.by_order.length}
						<p class="m-0 mb-1 text-[11px] font-medium text-brand-steel">Length by Strahler order</p>
						<ul class="rows">
							{#each stats.drainage.by_order as o (o.order)}
								<li>
									<span class="lbl w-14 flex-none">Order {o.order}</span>
									<span class="bar"><span style:width="{o.pct}%" style:background-color={ORDER_COLORS[Math.min(o.order, ORDER_COLORS.length) - 1]}></span></span>
									<span class="val">{num(o.km, 1)} km</span>
								</li>
							{/each}
						</ul>
					{:else}
						<p class="na">No drainage lines inside the AOI.</p>
					{/if}
				{:else}
					<p class="na">{stats.drainage.message}</p>
				{/if}
			</section>
		{/if}
	</div>
</aside>

<style>
	@media (max-width: 767px) {
		.stats {
			max-height: 40vh;
		}
	}
	.icon-btn {
		display: grid;
		place-items: center;
		flex: none;
		width: 1.75rem;
		height: 1.75rem;
		cursor: pointer;
		border-radius: 0.4rem;
		border: 1px solid rgba(0, 48, 109, 0.15);
		background: white;
		color: #00306d;
	}
	.icon-btn:hover {
		background: rgba(0, 48, 109, 0.05);
	}
	.card {
		margin-bottom: 0.75rem;
		border-radius: 0.6rem;
		border: 1px solid rgba(0, 48, 109, 0.08);
		background: white;
		padding: 0.7rem 0.8rem;
	}
	h3 {
		margin: 0 0 0.5rem;
		font-size: 0.72rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: #00306d;
	}
	h3 .sub {
		text-transform: none;
		letter-spacing: 0;
		font-weight: 500;
	}
	.sub {
		color: #6b7885;
		font-weight: 400;
	}
	.kv {
		display: grid;
		grid-template-columns: auto 1fr;
		gap: 0.25rem 0.75rem;
		margin: 0;
		font-size: 0.75rem;
	}
	.kv dt {
		color: #6b7885;
	}
	.kv dd {
		margin: 0;
		color: #0f172a;
		font-weight: 500;
		min-width: 0;
		overflow-wrap: anywhere;
	}
	.tiles {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 0.4rem;
		margin-bottom: 0.6rem;
	}
	.tiles div {
		display: flex;
		flex-direction: column;
		border-radius: 0.45rem;
		background: #f2f5fa;
		padding: 0.4rem 0.45rem;
	}
	.tiles b {
		font-size: 0.95rem;
		color: #00306d;
		font-variant-numeric: tabular-nums;
	}
	.tiles span {
		font-size: 0.65rem;
		color: #6b7885;
	}
	.stack {
		display: flex;
		height: 0.55rem;
		overflow: hidden;
		border-radius: 999px;
		background: rgba(0, 48, 109, 0.08);
		margin-bottom: 0.5rem;
	}
	.stack span {
		display: block;
		height: 100%;
	}
	.rows {
		display: grid;
		gap: 0.3rem;
		margin: 0;
		padding: 0;
		list-style: none;
		font-size: 0.72rem;
	}
	.rows li {
		display: flex;
		align-items: center;
		gap: 0.45rem;
	}
	.sw {
		flex: none;
		width: 0.6rem;
		height: 0.6rem;
		border-radius: 0.15rem;
		box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.08);
	}
	.lbl {
		min-width: 0;
		flex: 1;
		color: #24303a;
	}
	.val {
		flex: none;
		color: #0f172a;
		font-weight: 600;
		font-variant-numeric: tabular-nums;
	}
	.bar {
		flex: 1;
		height: 0.45rem;
		overflow: hidden;
		border-radius: 999px;
		background: rgba(0, 48, 109, 0.08);
	}
	.bar span {
		display: block;
		height: 100%;
	}
	.na {
		margin: 0;
		font-size: 0.75rem;
		color: #b45309;
	}
	.link {
		cursor: pointer;
		border: 0;
		background: transparent;
		padding: 0;
		font: inherit;
		font-size: 0.75rem;
		color: #1b75e0;
		text-align: left;
	}
	.link:hover {
		text-decoration: underline;
	}
</style>
