<script>
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';
	import MelFormQrModal from '$lib/modules/assess/components/MelFormQrModal.svelte';
	import { itemPath } from '$lib/shared/slug.js';
	import { assessCrumbs } from '$lib/modules/assess/breadcrumbs.js';
	import {
		exportMelPlanPdf,
		fetchMelFormCollectQr,
		fetchMelIntervention,
		fetchMelPackages,
		fetchMelPlan,
		fetchMelPlanForms
	} from '$lib/modules/assess/mel-api';

	/** @type {{ project: any, plan: any, projects?: any[] }} */
	let { project, plan, projects = [] } = $props();

	let forms = $state([]);
	let planDetail = $state(null);
	let interventionName = $state('');
	/** @type {any[]} */
	let outcomes = $state([]);
	/** @type {any[]} */
	let sessions = $state([]);
	let loading = $state(true);
	let exporting = $state(false);
	let error = $state('');

	let qrOpen = $state(false);
	let qrLoading = $state(false);
	let qrError = $state('');
	/** @type {any} */
	let qrForm = $state(null);
	/** @type {any} */
	let qrPayload = $state(null);

	const slugBase = $derived(itemPath('/assess', project, projects));
	const planBase = $derived(`${slugBase}/plans/${plan.id}`);
	const crumbs = $derived(assessCrumbs({ projects, project, plan }));

	const outcomeIds = $derived.by(() => {
		const json = planDetail?.plan_json || plan?.plan_json || {};
		return Array.isArray(json.outcome_ids) ? json.outcome_ids : [];
	});

	const indicatorCount = $derived(
		outcomes.reduce((n, o) => n + (o.indicators?.length || 0), 0)
	);

	onMount(load);

	async function load() {
		loading = true;
		error = '';
		try {
			const [formsRes, detail, intervention] = await Promise.all([
				fetchMelPlanForms(project.id, plan.id),
				fetchMelPlan(project.id, plan.id).catch(() => plan),
				fetchMelIntervention(plan.intervention_slug).catch(() => null)
			]);
			forms = formsRes.forms ?? [];
			planDetail = detail;
			interventionName = intervention?.name || plan.intervention_slug;

			const ids = Array.isArray(detail?.plan_json?.outcome_ids)
				? detail.plan_json.outcome_ids
				: [];
			const selected = (intervention?.outcomes ?? []).filter(
				(o) => o.must_measure || ids.includes(o.id)
			);
			outcomes = selected;

			if (plan.intervention_slug && (ids.length || selected.length)) {
				try {
					const packages = await fetchMelPackages({
						interventionSlug: plan.intervention_slug,
						outcomeIds: ids.length ? ids : selected.map((o) => o.id),
						projectId: project.id,
						planId: plan.id
					});
					sessions = packages.packages ?? [];
				} catch {
					sessions = [];
				}
			} else {
				sessions = [];
			}
		} catch (err) {
			error = String(err);
		} finally {
			loading = false;
		}
	}

	async function handleExport() {
		if (!plan.intervention_slug) return;
		exporting = true;
		error = '';
		try {
			const ids = outcomeIds.length > 0 ? outcomeIds : [];
			const { blob, filename } = await exportMelPlanPdf({
				interventionSlug: plan.intervention_slug,
				outcomeIds: ids,
				projectId: project.id,
				planId: plan.id
			});
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

	function formatDate(iso) {
		if (!iso) return '—';
		try {
			return new Date(iso).toLocaleString(undefined, {
				year: 'numeric',
				month: 'short',
				day: 'numeric',
				hour: '2-digit',
				minute: '2-digit'
			});
		} catch {
			return iso;
		}
	}

	function formDashboardHref(form) {
		return `${planBase}/forms/${encodeURIComponent(form.xmlFormId)}`;
	}

	async function showQr(form) {
		qrForm = form;
		qrOpen = true;
		qrLoading = true;
		qrError = '';
		qrPayload = null;
		try {
			const res = await fetchMelFormCollectQr(project.id, plan.id, form.xmlFormId);
			qrPayload = res.collectQr ?? null;
			if (!qrPayload?.payload) {
				qrError = 'Collect QR could not be generated.';
			}
		} catch (err) {
			qrError = String(err);
		} finally {
			qrLoading = false;
		}
	}

	function scheduleLabel(pkg) {
		const parts = [pkg.title || pkg.id];
		if (pkg.schedule) parts.push(pkg.schedule);
		if (pkg.suggested_fields?.length != null) {
			parts.push(`${pkg.suggested_fields.length} fields`);
		}
		return parts.filter(Boolean).join(' · ');
	}
</script>

<div class="relative flex min-h-screen flex-col bg-transparent font-body">
	<ModuleHeader title="Assess" titleHref="/assess" wide fullProjectTitle {crumbs}>
		<button type="button" onclick={() => goto(`${planBase}/new`)}>Edit plan</button>
		<button type="button" disabled={loading} onclick={load}>
			{loading ? 'Refreshing…' : 'Refresh'}
		</button>
	</ModuleHeader>

	<main class="relative z-10 flex min-h-0 flex-1 flex-col overflow-auto p-6">
		{#if error}
			<p class="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 font-body text-sm text-red-700">
				{error}
			</p>
		{/if}

		{#if loading}
			<p class="font-body text-brand-steel">Loading plan…</p>
		{:else}
			<div class="plan-layout">
				<aside class="stats-sidebar" aria-label="Plan stats">
					<div class="sidebar-main">
						<header class="sidebar-title-block">
							<h1 class="m-0 font-display text-2xl text-brand-navy">{plan.name}</h1>
							<p class="m-0 mt-1 font-body text-sm text-brand-steel">
								{interventionName || 'Intervention'}
							</p>
						</header>

						<section class="stats" aria-label="Plan summary counts">
							<div class="stat">
								<p class="stat-label">Outcomes</p>
								<p class="stat-value">{outcomes.length}</p>
							</div>
							<div class="stat">
								<p class="stat-label">Indicators</p>
								<p class="stat-value">{indicatorCount}</p>
							</div>
							<div class="stat">
								<p class="stat-label">MEL sessions</p>
								<p class="stat-value">{sessions.length}</p>
							</div>
							<div class="stat">
								<p class="stat-label">ODK forms</p>
								<p class="stat-value">{forms.length}</p>
							</div>
						</section>

						<section class="detail-block" aria-label="Outcomes and indicators">
							<h2 class="detail-title">Outcomes & indicators</h2>
							{#if outcomes.length === 0}
								<p class="m-0 font-body text-sm text-brand-steel">No outcomes selected yet.</p>
							{:else}
								<ul class="outcome-list m-0 list-none p-0">
									{#each outcomes as outcome (outcome.id)}
										<li class="outcome-item">
											<p class="m-0 font-headline text-sm font-semibold text-brand-navy">
												{outcome.title || outcome.outcome || outcome.name || outcome.id}
												{#if outcome.must_measure}
													<span class="must">Required</span>
												{/if}
											</p>
											{#if outcome.indicators?.length}
												<ul class="indicator-list">
													{#each outcome.indicators as ind, ii (typeof ind === 'string' ? ind : ind.id || `${outcome.id}-${ii}`)}
														<li>
															{typeof ind === 'string'
																? ind
																: ind.name || ind.indicator || ind.title || ind.id}
														</li>
													{/each}
												</ul>
											{:else}
												<p class="m-0 mt-1 font-body text-xs text-brand-steel">No indicators listed</p>
											{/if}
										</li>
									{/each}
								</ul>
							{/if}
						</section>

						<section class="detail-block" aria-label="MEL sessions">
							<h2 class="detail-title">MEL sessions</h2>
							{#if sessions.length === 0}
								<p class="m-0 font-body text-sm text-brand-steel">No MEL sessions for this plan yet.</p>
							{:else}
								<ul class="session-list m-0 list-none p-0">
									{#each sessions as pkg (pkg.id)}
										<li class="session-item">
											<p class="m-0 font-headline text-sm font-semibold text-brand-navy">
												{pkg.title || pkg.id}
											</p>
											<p class="m-0 mt-0.5 font-body text-xs text-brand-steel">
												{scheduleLabel(pkg)}
											</p>
										</li>
									{/each}
								</ul>
							{/if}
						</section>
					</div>

					<div class="sidebar-actions">
						<button
							type="button"
							class="sidebar-secondary-btn"
							onclick={() => goto(`${planBase}/new?forms=1`)}
						>
							Edit ODK forms
						</button>
						<button
							type="button"
							class="export-btn"
							disabled={exporting || loading}
							onclick={handleExport}
						>
							{exporting ? 'Exporting…' : 'Export'}
						</button>
					</div>
				</aside>

				<section class="forms-section" aria-label="ODK forms">
					<header class="forms-head">
						<h2 class="m-0 font-display text-2xl text-brand-navy">ODK forms</h2>
						<p class="m-0 mt-1 font-body text-sm text-brand-steel">
							Published forms for this MEL plan
						</p>
					</header>

					{#if forms.length === 0}
						<div class="forms-empty">
							No forms yet.
							<button
								type="button"
								class="text-[#1b75e0] underline"
								onclick={() => goto(`${planBase}/new?forms=1`)}
							>
								Edit ODK forms
							</button>
							to publish from this MEL plan.
						</div>
					{:else}
						<ul class="form-grid m-0 list-none p-0">
							{#each forms as form, i (form.id)}
								<li class="form-card" style="--delay: {i * 40}ms">
									<div class="form-main min-w-0">
										<p class="m-0 font-display text-lg text-brand-navy">{form.name}</p>
										<p class="m-0 mt-1 font-body text-sm text-brand-steel">
											{form.packageTitle || form.packageId || 'Form'}
										</p>
										<p class="m-0 mt-2 font-mono text-[11px] tracking-wide text-brand-steel">
											{form.xmlFormId}
										</p>
										<p class="m-0 mt-1 font-body text-xs text-brand-steel">
											{formatDate(form.createdAt)}
										</p>
									</div>
									<div class="form-actions">
										<button type="button" class="ghost-btn" onclick={() => showQr(form)}>
											Show QR
										</button>
										<button
											type="button"
											class="dashboard-btn"
											onclick={() => goto(formDashboardHref(form))}
										>
											Dashboard
											<svg
												xmlns="http://www.w3.org/2000/svg"
												viewBox="0 0 24 24"
												fill="none"
												stroke="currentColor"
												stroke-width="2"
												class="h-3.5 w-3.5"
											>
												<path
													d="M5 12h14M13 6l6 6-6 6"
													stroke-linecap="round"
													stroke-linejoin="round"
												/>
											</svg>
										</button>
									</div>
								</li>
							{/each}
						</ul>
					{/if}
				</section>
			</div>
		{/if}
	</main>
</div>

<MelFormQrModal
	open={qrOpen}
	formName={qrForm?.name || ''}
	packageTitle={qrForm?.packageTitle || ''}
	xmlFormId={qrForm?.xmlFormId || ''}
	collectQr={qrPayload}
	loading={qrLoading}
	error={qrError}
	onClose={() => {
		qrOpen = false;
	}}
/>

<style>
	.sidebar-secondary-btn {
		width: 100%;
		flex: none;
		cursor: pointer;
		border-radius: 0.5rem;
		border: 1px solid color-mix(in srgb, var(--color-brand-navy, #1a2530) 14%, transparent);
		background: white;
		padding: 0.55rem 1rem;
		font-family: var(--font-body);
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--color-brand-navy, #1a2530);
	}
	.sidebar-secondary-btn:hover {
		border-color: color-mix(in srgb, #1b75e0 40%, transparent);
		color: #1565c0;
	}
	.export-btn {
		width: 100%;
		flex: none;
		cursor: pointer;
		border-radius: 0.5rem;
		border: 1px solid color-mix(in srgb, #1b75e0 40%, transparent);
		background: #1b75e0;
		padding: 0.55rem 1rem;
		font-family: var(--font-body);
		font-size: 0.875rem;
		font-weight: 600;
		color: white;
	}
	.export-btn:hover:not(:disabled) {
		background: #1565c0;
	}
	.export-btn:disabled {
		opacity: 0.55;
		cursor: not-allowed;
	}
	.plan-layout {
		display: grid;
		grid-template-columns: minmax(16rem, 19.5rem) minmax(0, 1fr);
		gap: 0;
		align-items: stretch;
		flex: 1;
		min-height: calc(100vh - 8.5rem);
		border-radius: 0.85rem;
		border: 1px solid color-mix(in srgb, var(--color-brand-navy, #1a2530) 10%, transparent);
		overflow: hidden;
		background: white;
	}
	.stats-sidebar {
		display: flex;
		flex-direction: column;
		justify-content: space-between;
		gap: 1.25rem;
		min-height: 100%;
		padding: 1rem 0.85rem;
		border-right: 1px solid color-mix(in srgb, var(--color-brand-navy, #1a2530) 10%, transparent);
		background: white;
		font-family: var(--font-body);
		overflow: auto;
	}
	.sidebar-actions {
		display: flex;
		flex-direction: column;
		gap: 0.55rem;
		flex: none;
	}
	.sidebar-main {
		display: flex;
		flex-direction: column;
		gap: 1.15rem;
		min-width: 0;
	}
	.sidebar-title-block {
		padding: 0 0.15rem;
	}
	.stats {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.55rem;
	}
	.stat {
		border-radius: 0.65rem;
		border: 1px solid color-mix(in srgb, var(--color-brand-navy, #1a2530) 10%, transparent);
		background: white;
		padding: 0.75rem 0.8rem;
	}
	.stat-label,
	.detail-title {
		margin: 0;
		font-family: var(--font-headline);
		font-size: 11px;
		font-weight: 600;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: color-mix(in srgb, var(--color-brand-navy, #1a2530) 55%, transparent);
	}
	.stat-value {
		margin: 0.3rem 0 0;
		font-family: var(--font-display);
		font-size: 1.55rem;
		color: var(--color-brand-navy, #1a2530);
		line-height: 1;
	}
	.detail-title {
		margin: 0 0 0.75rem;
	}
	.detail-block {
		padding-top: 0.15rem;
	}
	.outcome-list,
	.session-list {
		display: flex;
		flex-direction: column;
		gap: 0.85rem;
	}
	.must {
		margin-left: 0.4rem;
		display: inline-block;
		border-radius: 0.25rem;
		background: color-mix(in srgb, #1b75e0 12%, white);
		padding: 0.05rem 0.35rem;
		font-family: var(--font-body);
		font-size: 0.65rem;
		font-weight: 600;
		color: #1565c0;
		text-transform: none;
		letter-spacing: 0;
	}
	.indicator-list {
		margin: 0.35rem 0 0;
		padding-left: 1.1rem;
		font-family: var(--font-body);
		font-size: 0.78rem;
		color: var(--color-brand-steel, #56646f);
		line-height: 1.45;
	}
	.session-item {
		padding-bottom: 0.65rem;
		border-bottom: 1px solid color-mix(in srgb, var(--color-brand-navy, #1a2530) 8%, transparent);
	}
	.session-item:last-child {
		padding-bottom: 0;
		border-bottom: none;
	}
	.forms-section {
		min-width: 0;
		display: flex;
		flex-direction: column;
		align-items: stretch;
		gap: 0.85rem;
		padding: 1rem 1.15rem 1.15rem;
		background: transparent;
	}
	.forms-head {
		margin: 0;
		padding: 0;
		min-height: 3.4rem;
	}
	.forms-empty {
		border-radius: 0.85rem;
		border: 1px dashed color-mix(in srgb, var(--color-brand-navy, #1a2530) 18%, transparent);
		background: color-mix(in srgb, var(--color-brand-navy, #1a2530) 2%, white);
		padding: 2.5rem 1.5rem;
		text-align: center;
		font-family: var(--font-body);
		font-size: 0.875rem;
		color: var(--color-brand-steel, #56646f);
	}
	.form-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.85rem;
		align-items: stretch;
	}
	.form-card {
		display: flex;
		flex-direction: column;
		justify-content: space-between;
		gap: 1rem;
		min-height: 11.5rem;
		padding: 1.1rem 1.15rem;
		border-radius: 0.65rem;
		border: 1px solid color-mix(in srgb, var(--color-brand-navy, #1a2530) 10%, transparent);
		background: white;
		animation: rise 0.45s ease both;
		animation-delay: var(--delay);
	}
	.form-card:hover {
		border-color: color-mix(in srgb, #1b75e0 35%, transparent);
	}
	.form-actions {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		margin-top: auto;
	}
	.ghost-btn {
		cursor: pointer;
		border-radius: 0.5rem;
		border: 1px solid color-mix(in srgb, var(--color-brand-navy, #1a2530) 14%, transparent);
		background: white;
		padding: 0.55rem 0.9rem;
		font-family: var(--font-body);
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--color-brand-navy, #1a2530);
	}
	.ghost-btn:hover {
		border-color: color-mix(in srgb, #1b75e0 40%, transparent);
		color: #1565c0;
	}
	.dashboard-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		flex: none;
		cursor: pointer;
		border-radius: 0.5rem;
		border: 1px solid color-mix(in srgb, #1b75e0 40%, transparent);
		background: #1b75e0;
		padding: 0.55rem 0.95rem;
		font-family: var(--font-body);
		font-size: 0.8125rem;
		font-weight: 600;
		color: white;
	}
	.dashboard-btn:hover {
		background: #1565c0;
	}
	@keyframes rise {
		from {
			opacity: 0;
			transform: translateY(8px);
		}
		to {
			opacity: 1;
			transform: none;
		}
	}
	@media (max-width: 900px) {
		.plan-layout {
			grid-template-columns: 1fr;
			min-height: 0;
		}
		.stats-sidebar {
			border-right: none;
			border-bottom: 1px solid color-mix(in srgb, var(--color-brand-navy, #1a2530) 10%, transparent);
			max-height: none;
		}
		.form-grid {
			grid-template-columns: 1fr;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.form-card {
			animation: none;
		}
	}
</style>
