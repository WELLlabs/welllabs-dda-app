<script>
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';
	import { itemPath } from '$lib/shared/slug.js';
	import { assessCrumbs } from '$lib/modules/assess/breadcrumbs.js';
	import {
		exportMelPlanDocx,
		fetchImplementationDashboard,
		fetchMelFormCollectQr,
		fetchMelIntervention,
		fetchMelPlan,
		fetchMelPlanForms,
		saveMelPlan
	} from '$lib/modules/assess/mel-api';
	import {
		ASSET_SELECT_LOCK_IDS,
		buildParamCards,
		includedCards,
		typeLabel
	} from '$lib/modules/assess/mel-param-cards.js';
	import MelFormQrCard from '$lib/modules/assess/components/MelFormQrCard.svelte';

	/** @type {{ project: any, plan: any, projects?: any[] }} */
	let { project, plan, projects = [] } = $props();

	let loading = $state(true);
	let error = $state('');
	let mounted = $state(false);
	let dashboard = $state(null);
	let forms = $state([]);
	let cmQr = $state(null);
	let intervention = $state(null);
	let exporting = $state(false);
	let planDetail = $state(plan);
	let renaming = $state(false);
	let showRename = $state(false);
	let renameValue = $state(plan?.name || '');
	/** @type {any[]} */
	let otCards = $state([]);
	/** @type {any[]} */
	let cmCards = $state([]);

	const slugBase = $derived(itemPath('/assess', project, projects));
	const crumbs = $derived(assessCrumbs({ projects, project, plan }));
	const isImpl = $derived((plan.kind || 'plan') === 'implementation');
	const isPlot = $derived(['pmds', 'bio-mulching'].includes(String(plan.intervention_slug || '').toLowerCase()));

	const outcomeIds = $derived(planDetail?.plan_json?.outcome_ids || plan?.plan_json?.outcome_ids || []);
	const outcomes = $derived(
		(intervention?.outcomes || []).filter((o) => !outcomeIds.length || outcomeIds.includes(o.id))
	);
	const includedOt = $derived(includedCards(otCards));
	const includedCm = $derived(includedCards(cmCards));

	onMount(() => {
		mounted = true;
		load();
	});

	async function load() {
		loading = true;
		error = '';
		try {
			const [intv, detail] = await Promise.all([
				fetchMelIntervention(plan.intervention_slug),
				fetchMelPlan(project.id, plan.id).catch(() => plan)
			]);
			intervention = intv;
			planDetail = detail || plan;
			const pj = planDetail?.plan_json || {};
			otCards = buildParamCards(intv?.one_time_questions || [], pj.asset_allocation);
			cmCards = buildParamCards(intv?.cm_questions || [], pj.cm_form, {
				lockIds: ASSET_SELECT_LOCK_IDS
			});
			if (isImpl) {
				const [dash, formsRes] = await Promise.all([
					fetchImplementationDashboard(project.id, plan.id),
					fetchMelPlanForms(project.id, plan.id)
				]);
				dashboard = dash;
				forms = formsRes.forms ?? [];
				loading = false;
				// QR is secondary — don't block the dashboard on ODK.
				const form = forms.find((f) => f.packageId === 'cm-mapping') || forms[0];
				cmQr = null;
				if (form?.xmlFormId) {
					try {
						const qrRes = await fetchMelFormCollectQr(project.id, plan.id, form.xmlFormId);
						cmQr = qrRes.collectQr ?? null;
					} catch {
						cmQr = null;
					}
				}
				return;
			}
		} catch (err) {
			error = String(err);
		} finally {
			loading = false;
		}
	}

	const totals = $derived(dashboard?.totals || {});

	function fmt(v, digits = 2) {
		if (v == null || Number.isNaN(Number(v))) return '—';
		return Number(v).toLocaleString(undefined, { maximumFractionDigits: digits });
	}

	function fmtWhen(value) {
		if (!value) return '—';
		const d = new Date(value);
		if (Number.isNaN(d.getTime())) return String(value);
		return d.toLocaleString(undefined, {
			dateStyle: 'medium',
			timeStyle: 'short'
		});
	}

	function fmtDay(value) {
		if (!value) return '—';
		const d = new Date(`${String(value).slice(0, 10)}T00:00:00`);
		if (Number.isNaN(d.getTime())) return String(value);
		return d.toLocaleDateString(undefined, { dateStyle: 'medium' });
	}

	/** @param {any} ot */
	function assetCoords(ot) {
		const raw = String(ot?.fp_ot_location || ot?.bm_ot_location || '').trim();
		if (!raw) return { lat: null, lon: null };
		const parts = raw
			.split(/[,\s]+/)
			.map((p) => Number(p))
			.filter((n) => !Number.isNaN(n));
		if (parts.length < 2) return { lat: null, lon: null };
		return { lat: parts[0], lon: parts[1] };
	}

	/** Satellite static map (Esri) — OSM.de staticmap is unreliable / blocked. */
	/** @param {number} lat @param {number} lon */
	function mapThumbUrl(lat, lon) {
		const d = 0.006;
		const bbox = `${lon - d},${lat - d},${lon + d},${lat + d}`;
		return (
			'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export' +
			`?bbox=${encodeURIComponent(bbox)}&bboxSR=4326&imageSR=4326&size=640,360&format=png&f=image`
		);
	}

	/** @param {any} ot */
	function pondRect(ot) {
		const L = Number(ot?.fp_ot_length);
		const B = Number(ot?.fp_ot_breadth);
		const H = Number(ot?.fp_ot_height);
		const length = Number.isFinite(L) && L > 0 ? L : null;
		const breadth = Number.isFinite(B) && B > 0 ? B : null;
		const height = Number.isFinite(H) && H > 0 ? H : null;
		const max = Math.max(length || 1, breadth || 1);
		return {
			length,
			breadth,
			height,
			w: length ? (length / max) * 64 : 44,
			h: breadth ? (breadth / max) * 52 : 36
		};
	}

	function plotMeta(ot) {
		const area = Number(ot?.bm_ot_area_under_the_crop);
		const unit = String(ot?.bm_ot_area_unit || '').trim();
		const crop = String(ot?.bm_ot_crop_grown || '').trim();
		const season = String(ot?.bm_ot_agriculture_season || '').trim();
		const role = String(ot?.bm_ot_plot_role || '').trim();
		return {
			area: Number.isFinite(area) && area > 0 ? area : null,
			unit: unit || 'acre',
			crop: crop || null,
			season: season || null,
			role: role || null
		};
	}

	/** Group PMDS assets into treatment–control pair cards for the home grid. */
	const plotCards = $derived.by(() => {
		const list = dashboard?.assets || [];
		if (!isPlot) return list.map((a) => ({ kind: 'asset', id: a.id, asset: a }));
		const byId = new Map(list.map((a) => [String(a.id), a]));
		const used = new Set();
		/** @type {any[]} */
		const cards = [];
		for (const a of list) {
			const ot = a.ot_answers || {};
			const role = String(ot.bm_ot_plot_role || '').trim().toLowerCase();
			const controlId = String(ot.bm_ot_paired_control_asset_id || '').trim();
			if (role === 'treatment' || controlId) {
				const control = controlId ? byId.get(controlId) : null;
				used.add(String(a.id));
				if (control) used.add(String(control.id));
				cards.push({
					kind: 'pair',
					id: a.id,
					treatment: a,
					control: control || null
				});
			}
		}
		for (const a of list) {
			if (used.has(String(a.id))) continue;
			cards.push({ kind: 'solo', id: a.id, asset: a });
		}
		return cards;
	});

	function addAssetHref() {
		return `${slugBase}/plans/${plan.id}/new?assets=1&new=1`;
	}

	function editFormsHref() {
		return `${slugBase}/plans/${plan.id}/new?forms=1`;
	}

	function editAssetHref(assetId) {
		return `${slugBase}/plans/${plan.id}/new?assets=1&asset=${encodeURIComponent(assetId)}`;
	}

	function openRename() {
		renameValue = planDetail?.name || plan.name || '';
		showRename = true;
		error = '';
	}

	async function handleRename() {
		if (!renameValue.trim() || renaming) return;
		renaming = true;
		error = '';
		try {
			const updated = await saveMelPlan(project.id, plan.id, { name: renameValue.trim() });
			planDetail = { ...planDetail, name: updated.name || renameValue.trim() };
			showRename = false;
		} catch (err) {
			error = String(err);
		} finally {
			renaming = false;
		}
	}

	const cmForm = $derived(
		(forms || []).find((f) => f.packageId === 'cm-mapping') || forms[0] || null
	);

	function handlePointer(e) {
		const el = e.currentTarget;
		if (!(el instanceof HTMLElement)) return;
		const rect = el.getBoundingClientRect();
		el.style.setProperty('--mx', `${e.clientX - rect.left}px`);
		el.style.setProperty('--my', `${e.clientY - rect.top}px`);
	}

	async function handleExport() {
		exporting = true;
		error = '';
		try {
			const { blob, filename } = await exportMelPlanDocx(project.id, plan.id);
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = filename;
			a.click();
			URL.revokeObjectURL(url);
		} catch (err) {
			error = String(err);
		} finally {
			exporting = false;
		}
	}
</script>

<div class="flex h-svh max-h-svh flex-col overflow-hidden bg-transparent font-body">
	<ModuleHeader title="Assess" titleHref="/assess" wide {crumbs}>
		{#if !isImpl}
			<button type="button" onclick={handleExport} disabled={exporting || loading}>
				{exporting ? 'Exporting…' : 'Export .docx'}
			</button>
		{/if}
		{#if isImpl}
			<button type="button" onclick={openRename}>Edit intervention</button>
			<button type="button" onclick={() => goto(editFormsHref())}>Edit forms</button>
			<button type="button" class="filled" onclick={() => goto(addAssetHref())}
				>{isPlot ? 'Add farm plot' : 'Add asset'}</button
			>
		{:else}
			<button type="button" onclick={openRename}>Rename</button>
			<button type="button" onclick={() => goto(`${slugBase}/plans/${plan.id}/new`)}>Edit plan</button>
		{/if}
	</ModuleHeader>

	<main
		class="mx-auto flex min-h-0 w-full flex-1 flex-col gap-3 px-4 py-3 sm:px-6 {isImpl
			? 'max-w-none overflow-hidden'
			: 'max-w-7xl overflow-hidden'}"
	>
		<div class="shrink-0">
			<p class="m-0 text-[10px] uppercase tracking-wide text-brand-steel">
				{isImpl ? 'Intervention' : 'MEL Plan'}
			</p>
			<h1 class="m-0 mt-0.5 truncate font-headline text-xl font-semibold text-brand-navy">
				{planDetail?.name || plan.name}
			</h1>
			<p class="m-0 mt-0.5 truncate text-xs text-brand-steel">
				{intervention?.name || plan.intervention_slug}
			</p>
		</div>

		{#if error}
			<p class="m-0 shrink-0 rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs text-red-700">
				{error}
			</p>
		{/if}

		{#if loading}
			<p class="text-sm text-brand-steel">Loading…</p>
		{:else if !isImpl}
			<nav class="phase-links shrink-0" aria-label="MEL plan phases">
				<button
					type="button"
					class="phase-link"
					onclick={() => goto(`${slugBase}/plans/${plan.id}/new`)}
				>
					<span class="phase-num">1</span>
					<span>
						<span class="phase-title">Outcomes & indicators</span>
						<span class="phase-sub">{outcomes.length} selected · edit in wizard</span>
					</span>
				</button>
				<button
					type="button"
					class="phase-link"
					onclick={() => goto(`${slugBase}/plans/${plan.id}/new?step=assets`)}
				>
					<span class="phase-num">2</span>
					<span>
						<span class="phase-title">Asset allocation</span>
						<span class="phase-sub">{includedOt.length} parameters · types & options</span>
					</span>
				</button>
				<button
					type="button"
					class="phase-link"
					onclick={() => goto(`${slugBase}/plans/${plan.id}/new?step=cm`)}
				>
					<span class="phase-num">3</span>
					<span>
						<span class="phase-title">Continuous monitoring</span>
						<span class="phase-sub">{includedCm.length} parameters · types & options</span>
					</span>
				</button>
			</nav>

			<section class="plan-grid min-h-0 flex-1">
				<article class="plan-pane">
					<header class="pane-head">
						<h2>Outcomes & indicators</h2>
						<span class="count">{outcomes.length}</span>
					</header>
					<div class="pane-body">
						{#if !outcomes.length}
							<p class="empty">No outcomes selected yet.</p>
						{:else}
							{#each outcomes as outcome (outcome.id)}
								<div class="block-group">
									<p class="block-title">{outcome.title}</p>
									{#if outcome.indicators?.length}
										<ul class="ind-list">
											{#each outcome.indicators as ind}
												<li>{ind.title}</li>
											{/each}
										</ul>
									{:else}
										<p class="empty">No indicators</p>
									{/if}
								</div>
							{/each}
						{/if}
					</div>
				</article>

				<article class="plan-pane">
					<header class="pane-head">
						<h2>Asset allocation</h2>
						<span class="count">{includedOt.length}</span>
					</header>
					<p class="pane-sub">Included one-time parameters</p>
					<div class="pane-body">
						{#if !includedOt.length}
							<p class="empty">None included yet.</p>
						{:else}
							<ul class="ind-list">
								{#each includedOt as card (card.id)}
									<li>{card.label} · {typeLabel(card.input_type)}</li>
								{/each}
							</ul>
						{/if}
					</div>
				</article>

				<article class="plan-pane">
					<header class="pane-head">
						<h2>Continuous monitoring</h2>
						<span class="count">{includedCm.length}</span>
					</header>
					<p class="pane-sub">Included CM parameters</p>
					<div class="pane-body">
						{#if !includedCm.length}
							<p class="empty">None included yet.</p>
						{:else}
							<ul class="ind-list">
								{#each includedCm as card (card.id)}
									<li>{card.label} · {typeLabel(card.input_type)}</li>
								{/each}
							</ul>
						{/if}
					</div>
				</article>
			</section>
		{:else}
			<div class="impl-layout min-h-0 flex-1">
				<aside class="impl-sidebar" aria-label="Collect form and activity">
					<div class="sidebar-block">
						<p class="sidebar-kicker">Collect</p>
						{#if cmForm}
							<MelFormQrCard
								formName={cmForm.name || 'CM form'}
								packageTitle="Continuous monitoring"
								xmlFormId={cmForm.xmlFormId}
								collectQr={cmQr}
								sidebar
							/>
						{:else}
							<div class="qr-empty">
								<p class="qr-empty-title">CM form QR</p>
								<p>Publish the continuous monitoring form from Edit forms to show a Collect QR here.</p>
							</div>
						{/if}
					</div>
					<div class="sidebar-block">
						<p class="sidebar-kicker">Activity</p>
						<dl class="stat-list">
							<div>
								<dt>Submissions</dt>
								<dd>{totals.submission_count ?? 0}</dd>
							</div>
							<div>
								<dt>Last submission</dt>
								<dd>{fmtWhen(totals.last_submission_at)}</dd>
							</div>
							<div>
								<dt>Last reading</dt>
								<dd>{fmtDay(totals.last_reading_date)}</dd>
							</div>
							<div>
								<dt>{isPlot ? 'Farm plots' : 'Assets'}</dt>
								<dd>{totals.asset_count ?? (dashboard?.assets || []).length}</dd>
							</div>
						</dl>
					</div>
				</aside>

				<section class="impl-assets">
					{#if !(dashboard?.assets || []).length}
						<p class="empty-assets">
							{isPlot
								? 'No farm plots yet. Add a plot to start monitoring.'
								: 'No assets yet. Add a pond to start monitoring.'}
						</p>
					{:else}
						<div class="asset-grid">
							{#each isPlot ? plotCards : (dashboard.assets || []).map((a) => ({ kind: 'asset', id: a.id, asset: a })) as card, i (card.id)}
								{@const primary = card.treatment || card.asset}
								{@const control = card.control || null}
								{@const ot = primary?.ot_answers || {}}
								{@const loc = assetCoords(ot)}
								{@const rect = pondRect(ot)}
								{@const plot = plotMeta(ot)}
								{@const controlPlot = control ? plotMeta(control.ot_answers || {}) : null}
								{@const dashId = primary?.id}
								<div
									class="card asset-card"
									class:in={mounted}
									style="--accent: {isPlot ? '#166534' : '#1b75e0'}; --delay: {i * 50}ms"
									role="button"
									tabindex="0"
									onpointermove={handlePointer}
									onclick={() => goto(`${slugBase}/plans/${plan.id}/assets/${dashId}`)}
									onkeydown={(e) => {
										if (e.key === 'Enter' || e.key === ' ') {
											e.preventDefault();
											goto(`${slugBase}/plans/${plan.id}/assets/${dashId}`);
										}
									}}
								>
									<span class="card-spotlight" aria-hidden="true"></span>
									<span class="card-topline" aria-hidden="true"></span>
									<div class="relative z-10 flex w-full flex-col items-start gap-3">
										<div class="asset-thumb">
											{#if loc.lat != null && loc.lon != null}
												<img
													src={mapThumbUrl(loc.lat, loc.lon)}
													alt=""
													class="asset-map"
													loading="lazy"
													decoding="async"
													onerror={(e) => {
														const el = e.currentTarget;
														if (el instanceof HTMLImageElement) el.style.display = 'none';
													}}
												/>
											{:else}
												<div class="asset-map-fallback">No location</div>
											{/if}
											<div class="pond-overlay" aria-hidden="true">
												<svg viewBox="0 0 120 90" class="pond-svg">
													{#if isPlot}
														<rect x="10" y="18" width="100" height="58" rx="4" fill="rgba(22, 163, 74, 0.22)" stroke="#14532d" stroke-width="1.8" />
														<line x1="10" y1="47" x2="110" y2="47" stroke="#166534" stroke-width="1" stroke-dasharray="3 2" opacity="0.7" />
														{#each [[28, 32], [60, 32], [92, 32], [28, 62], [92, 62], [60, 47]] as [cx, cy]}
															<circle cx={cx} cy={cy} r="3.2" fill="#166534" stroke="#fff" stroke-width="1" />
														{/each}
														{#if plot.area != null}
															<text
																x="60"
																y="14"
																text-anchor="middle"
																fill="#14532d"
																stroke="#fff"
																stroke-width="3"
																paint-order="stroke"
																font-size="8"
																font-weight="700">{fmt(plot.area)} {plot.unit || ''}</text>
														{/if}
													{:else}
														<rect
															x={(120 - rect.w) / 2}
															y={(90 - rect.h) / 2}
															width={rect.w}
															height={rect.h}
															rx="3"
															fill="rgba(27, 117, 224, 0.38)"
															stroke="#0d2c4c"
															stroke-width="2"
														/>
														{#if rect.length}
															<text
																x="60"
																y={(90 - rect.h) / 2 - 5}
																text-anchor="middle"
																fill="#0d2c4c"
																stroke="#fff"
																stroke-width="3"
																paint-order="stroke"
																font-size="8"
																font-weight="700">{fmt(rect.length)} m</text>
														{/if}
														{#if rect.breadth}
															<text
																x="116"
																y="48"
																text-anchor="end"
																fill="#0d2c4c"
																stroke="#fff"
																stroke-width="3"
																paint-order="stroke"
																font-size="8"
																font-weight="700">{fmt(rect.breadth)} m</text>
														{/if}
													{/if}
												</svg>
											</div>
										</div>
										{#if isPlot && card.kind === 'pair'}
											<p class="m-0 text-[10px] font-bold uppercase tracking-wider text-[#166534]">
												Treatment · Control pair
											</p>
											<h3 class="card-title m-0 font-display text-xl">
												{(primary?.label || 'Treatment').replace(/\s*—\s*.*$/, '')}
												{#if control}
													<span class="text-[#6b7885]"> · </span>
													{(control.label || 'Control').replace(/\s*—\s*.*$/, '')}
												{/if}
											</h3>
											<p class="card-desc m-0 text-sm">
												T: {[plot.crop, plot.season, plot.area != null ? `${fmt(plot.area)} ${plot.unit}` : null]
													.filter(Boolean)
													.join(' · ') || '—'}
												{#if control}
													<br />
													C: {[controlPlot?.crop, controlPlot?.season, controlPlot?.area != null ? `${fmt(controlPlot.area)} ${controlPlot.unit}` : null]
														.filter(Boolean)
														.join(' · ') || control.label}
												{:else}
													<br /><span class="text-amber-700">No control linked yet</span>
												{/if}
											</p>
											<p class="m-0 font-mono text-[11px] tracking-wide text-[#6b7885]">
												SM savings {fmt(primary?.calculations?.sm_water_savings_m3)} m³ · Readings
												{(primary?.reading_count ?? 0) + (control?.reading_count ?? 0)}
											</p>
										{:else}
											<h3 class="card-title m-0 font-display text-xl">{primary?.label || primary?.id}</h3>
											<p class="card-desc m-0 text-sm">
												{#if isPlot}
													{[plot.role, plot.crop, plot.season, plot.area != null ? `${fmt(plot.area)} ${plot.unit}` : null]
														.filter(Boolean)
														.join(' · ') || 'Plot details —'}
												{:else if rect.length && rect.breadth && rect.height}
													{fmt(rect.length)} × {fmt(rect.breadth)} × {fmt(rect.height)} m
												{:else}
													Dimensions —
												{/if}
											</p>
											<p class="m-0 font-mono text-[11px] tracking-wide text-[#6b7885]">
												{#if isPlot}
													SM savings {fmt(primary?.calculations?.sm_water_savings_m3)} m³ · Readings
													{primary?.reading_count ?? 0}
												{:else}
													Storage {fmt(primary?.calculations?.volumetric_storage_m3)} m³ · Readings
													{primary?.reading_count ?? 0}
												{/if}
											</p>
										{/if}
										<div class="flex w-full items-center justify-between gap-2">
											<span class="cta mt-1 font-mono text-[12px]">
												{isPlot ? (card.kind === 'pair' ? 'Open pair' : 'Open plot') : 'Open asset'}
												<svg
													xmlns="http://www.w3.org/2000/svg"
													viewBox="0 0 24 24"
													fill="none"
													stroke="currentColor"
													stroke-width="2"
													class="arrow h-3.5 w-3.5"
												>
													<path d="M5 12h14M13 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round" />
												</svg>
											</span>
											<button
												type="button"
												class="asset-edit"
												onclick={(e) => {
													e.stopPropagation();
													goto(editAssetHref(dashId));
												}}
											>
												Edit
											</button>
										</div>
									</div>
								</div>
							{/each}
						</div>
					{/if}
				</section>
			</div>
		{/if}
	</main>
</div>

{#if showRename}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-brand-navy/40 p-4">
		<div class="w-full max-w-lg rounded-xl bg-white p-6 shadow-sm">
			<h2 class="m-0 mb-1 font-headline text-lg font-semibold text-brand-navy">
				{isImpl ? 'Edit intervention' : 'Rename plan'}
			</h2>
			<p class="m-0 mb-4 font-body text-sm text-brand-steel">
				This only changes the name shown in Assess.
			</p>
			<label class="mb-1 block text-sm font-medium text-brand-navy" for="mel-rename"
				>Name</label
			>
			<input
				id="mel-rename"
				class="mb-5 w-full rounded-lg border border-brand-navy/20 px-3 py-2 text-sm"
				bind:value={renameValue}
				onkeydown={(e) => {
					if (e.key === 'Enter') {
						e.preventDefault();
						handleRename();
					}
				}}
			/>
			<div class="flex justify-end gap-2">
				<button
					type="button"
					class="rounded-lg border border-brand-navy/20 px-4 py-2 text-sm"
					onclick={() => (showRename = false)}>Cancel</button
				>
				<button
					type="button"
					class="rounded-lg bg-brand-blue px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
					disabled={renaming || !renameValue.trim()}
					onclick={handleRename}
				>
					{renaming ? 'Saving…' : 'Save'}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.phase-links {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 0.55rem;
	}
	.phase-link {
		display: flex;
		align-items: flex-start;
		gap: 0.65rem;
		width: 100%;
		cursor: pointer;
		text-align: left;
		border-radius: 0.75rem;
		border: 1px solid color-mix(in srgb, var(--color-brand-navy, #1a2530) 12%, transparent);
		background: white;
		padding: 0.75rem 0.85rem;
	}
	.phase-link:hover {
		border-color: color-mix(in srgb, #1b75e0 40%, transparent);
		background: color-mix(in srgb, #1b75e0 4%, white);
	}
	.phase-num {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.4rem;
		height: 1.4rem;
		flex-shrink: 0;
		border-radius: 999px;
		background: #1b75e0;
		color: white;
		font-size: 0.7rem;
		font-weight: 700;
	}
	.phase-title {
		display: block;
		font-size: 0.85rem;
		font-weight: 600;
		color: var(--color-brand-navy, #1a2530);
	}
	.phase-sub {
		display: block;
		margin-top: 0.15rem;
		font-size: 0.7rem;
		color: var(--color-brand-steel, #56646f);
	}
	.plan-grid {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 0.65rem;
		min-height: 0;
	}
	.plan-pane {
		display: flex;
		flex-direction: column;
		min-height: 0;
		overflow: hidden;
		border-radius: 0.75rem;
		border: 1px solid color-mix(in srgb, var(--color-brand-navy, #1a2530) 12%, transparent);
		background: white;
	}
	.pane-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		flex-shrink: 0;
		padding: 0.55rem 0.75rem 0.35rem;
		border-bottom: 1px solid color-mix(in srgb, var(--color-brand-navy, #1a2530) 8%, transparent);
	}
	.pane-head h2 {
		margin: 0;
		font-family: var(--font-headline);
		font-size: 0.75rem;
		font-weight: 600;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: var(--color-brand-navy, #1a2530);
	}
	.count {
		flex-shrink: 0;
		border-radius: 999px;
		background: color-mix(in srgb, #1b75e0 12%, white);
		padding: 0.1rem 0.45rem;
		font-size: 0.65rem;
		font-weight: 600;
		color: #1565c0;
	}
	.pane-sub {
		margin: 0;
		flex-shrink: 0;
		padding: 0.25rem 0.75rem 0.4rem;
		font-size: 0.65rem;
		line-height: 1.3;
		color: var(--color-brand-steel, #56646f);
	}
	.pane-body {
		min-height: 0;
		flex: 1;
		overflow-y: auto;
		padding: 0.45rem 0.65rem 0.75rem;
	}
	.block-group + .block-group {
		margin-top: 0.65rem;
		padding-top: 0.55rem;
		border-top: 1px solid color-mix(in srgb, var(--color-brand-navy, #1a2530) 8%, transparent);
	}
	.block-title {
		margin: 0 0 0.25rem;
		font-size: 0.78rem;
		font-weight: 600;
		color: var(--color-brand-navy, #1a2530);
	}
	.ind-list {
		margin: 0;
		padding: 0;
		list-style: none;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}
	.ind-list > li {
		position: relative;
		padding-left: 0.7rem;
		font-size: 0.72rem;
		line-height: 1.35;
		color: var(--color-brand-steel, #56646f);
	}
	.ind-list > li::before {
		content: '•';
		position: absolute;
		left: 0;
		color: #1b75e0;
	}
	.empty {
		margin: 0;
		font-size: 0.72rem;
		color: var(--color-brand-steel, #56646f);
	}
	.impl-layout {
		display: grid;
		grid-template-columns: minmax(16rem, 18.5rem) minmax(0, 1fr);
		gap: 0.85rem;
		min-height: 0;
	}
	.impl-sidebar {
		display: flex;
		flex-direction: column;
		gap: 1.1rem;
		min-height: 0;
		overflow: auto;
		padding: 0.95rem 0.9rem 1.1rem;
		border-radius: 0.9rem;
		border: 1px solid color-mix(in srgb, var(--color-brand-navy, #1a2530) 12%, transparent);
		background: color-mix(in srgb, var(--color-brand-navy, #1a2530) 4%, white);
	}
	.sidebar-block {
		display: flex;
		flex-direction: column;
		gap: 0.65rem;
		min-width: 0;
	}
	.sidebar-kicker {
		margin: 0;
		font-size: 0.68rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--color-brand-steel, #56646f);
	}
	.stat-list {
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 0.55rem;
	}
	.stat-list > div {
		display: flex;
		flex-direction: column;
		gap: 0.12rem;
		padding-bottom: 0.5rem;
		border-bottom: 1px solid color-mix(in srgb, var(--color-brand-navy, #1a2530) 8%, transparent);
	}
	.stat-list > div:last-child {
		padding-bottom: 0;
		border-bottom: none;
	}
	.stat-list dt {
		font-size: 0.68rem;
		color: var(--color-brand-steel, #56646f);
	}
	.stat-list dd {
		margin: 0;
		font-size: 0.88rem;
		font-weight: 600;
		line-height: 1.3;
		color: var(--color-brand-navy, #1a2530);
		word-break: break-word;
	}
	.qr-empty {
		border-radius: 0.75rem;
		border: 1px dashed rgba(20, 40, 60, 0.18);
		background: white;
		padding: 0.85rem 0.9rem;
	}
	.qr-empty-title {
		margin: 0 0 0.35rem;
		font-size: 0.85rem;
		font-weight: 650;
		color: var(--color-brand-navy, #1a2530);
	}
	.qr-empty p {
		margin: 0;
		font-size: 0.8rem;
		line-height: 1.4;
		color: var(--color-brand-steel, #56646f);
	}
	.impl-assets {
		min-height: 0;
		overflow: auto;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}
	.empty-assets {
		margin: 0;
		font-size: 0.85rem;
		color: var(--color-brand-steel, #56646f);
	}
	.asset-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(100%, 18rem), 1fr));
		gap: 1.15rem;
	}
	.card {
		position: relative;
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		overflow: hidden;
		border-radius: 22px;
		border: 1px solid rgba(20, 40, 60, 0.08);
		background: rgba(255, 255, 255, 0.85);
		padding: 1.15rem 1.15rem 1.35rem;
		text-align: left;
		cursor: pointer;
		backdrop-filter: blur(6px);
		box-shadow:
			0 1px 0 rgba(255, 255, 255, 0.8) inset,
			0 12px 28px -20px rgba(20, 40, 60, 0.35);
		opacity: 0;
		transform: translateY(24px);
		transition:
			transform 0.35s cubic-bezier(0.2, 0.8, 0.2, 1),
			box-shadow 0.35s ease,
			border-color 0.35s ease,
			opacity 0.6s ease;
	}
	.card.in {
		opacity: 1;
		transform: translateY(0);
		transition-delay: var(--delay);
	}
	.card:hover {
		transform: translateY(-6px);
		border-color: color-mix(in srgb, var(--accent) 45%, transparent);
		box-shadow:
			0 1px 0 rgba(255, 255, 255, 0.9) inset,
			0 24px 44px -22px color-mix(in srgb, var(--accent) 50%, transparent);
	}
	.card:active {
		transform: translateY(-2px) scale(0.995);
	}
	.card:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 3px;
	}
	.card-spotlight {
		position: absolute;
		inset: 0;
		z-index: 0;
		overflow: hidden;
		border-radius: inherit;
		opacity: 0;
		transition: opacity 0.3s ease;
		background: radial-gradient(
			320px circle at var(--mx, 50%) var(--my, 0%),
			color-mix(in srgb, var(--accent) 14%, transparent),
			transparent 60%
		);
		pointer-events: none;
	}
	.card:hover .card-spotlight {
		opacity: 1;
	}
	.card-topline {
		position: absolute;
		top: 0;
		left: 0;
		z-index: 1;
		height: 3px;
		width: 100%;
		transform: scaleX(0);
		transform-origin: left;
		border-radius: 22px 22px 0 0;
		background: linear-gradient(90deg, var(--accent), transparent);
		transition: transform 0.4s cubic-bezier(0.2, 0.8, 0.2, 1);
		pointer-events: none;
	}
	.card:hover .card-topline {
		transform: scaleX(1);
	}
	.card-title {
		color: #1a2530;
	}
	.card-desc {
		color: #56646f;
	}
	.cta {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		color: color-mix(in srgb, var(--accent) 80%, black);
	}
	.cta .arrow {
		transition: transform 0.3s ease;
	}
	.card:hover .cta .arrow {
		transform: translateX(4px);
	}
	.asset-edit {
		border: 1px solid rgba(20, 40, 60, 0.12);
		background: white;
		border-radius: 999px;
		padding: 0.2rem 0.65rem;
		font-size: 0.72rem;
		font-weight: 600;
		color: #1a2530;
		cursor: pointer;
	}
	.asset-edit:hover {
		border-color: #1b75e0;
		color: #1b75e0;
	}
	.asset-thumb {
		position: relative;
		width: 100%;
		height: 9.5rem;
		overflow: hidden;
		border-radius: 14px;
		border: 1px solid rgba(20, 40, 60, 0.08);
		background: #d7e3ee;
	}
	.asset-map {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}
	.asset-map-fallback {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 100%;
		font-size: 0.75rem;
		color: #6b7885;
	}
	.pond-overlay {
		position: absolute;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		pointer-events: none;
		background: linear-gradient(180deg, rgba(13, 44, 76, 0.08), rgba(13, 44, 76, 0.18));
	}
	.pond-svg {
		width: 8.5rem;
		height: 6.4rem;
		filter: drop-shadow(0 1px 2px rgba(255, 255, 255, 0.8));
	}
	@media (prefers-reduced-motion: reduce) {
		.card {
			transition: none;
			opacity: 1;
			transform: none;
		}
	}
	@media (max-width: 960px) {
		.phase-links,
		.plan-grid {
			grid-template-columns: 1fr;
			overflow-y: auto;
		}
		.plan-pane {
			max-height: 16rem;
		}
		.impl-layout {
			grid-template-columns: 1fr;
			overflow: auto;
		}
	}
</style>
