<script>
	import { appPath } from '$lib/shared/paths.js';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import MapView from '$lib/modules/diagnose/components/MapView.svelte';
	import PackageProgressPanel from '$lib/shared/components/PackageProgressPanel.svelte';
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';
	import { onDestroy } from 'svelte';
	import {
		fetchProjects,
		fetchProject,
		packageToQfieldStream,
		syncFromQfieldStream,
		exportDiagnosisPdfStream,
		downloadDiagnosisPdf
	} from '$lib/modules/diagnose/api';
	import { findBySlug } from '$lib/shared/slug.js';

	let slug = $derived(page.params.slug);

	let currentProject = $state(null);
	let loading = $state(true);
	let loadError = $state('');
	let packaging = $state(false);
	let syncing = $state(false);
	let exportingPdf = $state(false);
	let syncMsg = $state('');
	let syncError = $state(false);
	let syncPending = $state(false);
	let mapRefreshKey = $state(0);

	// Shared progress panel (used for both package and sync)
	let panelTitle = $state('Packaging to QField');
	let panelPercent = $state(0);
	let panelLogs = $state([]);
	let panelStatus = $state('running');
	let panelError = $state('');
	let showPanel = $state(false);
	/** @type {AbortController | null} */
	let opAbort = null;
	/** @type {AbortController | null} */
	let loadAbort = null;
	let loadGen = 0;

	async function loadProject(slugValue) {
		const gen = ++loadGen;
		loadAbort?.abort();
		loadAbort = new AbortController();
		const { signal } = loadAbort;

		loading = true;
		loadError = '';
		currentProject = null;
		try {
			// Slim list for slug→id only (no full-precision watershed geoms).
			const data = await fetchProjects({ signal });
			if (signal.aborted || gen !== loadGen) return;
			const match = findBySlug(data.projects ?? [], slugValue);
			if (!match) {
				loadError = 'Project not found';
				return;
			}
			// Full project (precise watershed_geometry) for the map.
			currentProject = await fetchProject(match.id, { signal });
		} catch (err) {
			if (err?.name === 'AbortError' || signal.aborted || gen !== loadGen) return;
			const raw = err instanceof Error ? err.message : String(err);
			loadError = /502|503|504|Upstream|Cloudflare|timed out|Failed to fetch/i.test(raw)
				? 'The server was busy finishing the previous project. Wait a moment and try again.'
				: raw;
		} finally {
			if (gen === loadGen) loading = false;
		}
	}

	$effect(() => {
		loadProject(slug);
	});

	onDestroy(() => {
		loadAbort?.abort();
		opAbort?.abort();
	});

	function backToProjects() {
		loadAbort?.abort();
		goto(appPath('/diagnose'));
	}

	function retryLoad() {
		loadError = '';
		loadProject(slug);
	}

	function dismissPanel() {
		if (opAbort) {
			opAbort.abort();
			opAbort = null;
		}
		packaging = false;
		syncing = false;
		showPanel = false;
		panelStatus = 'running';
		panelPercent = 0;
		panelLogs = [];
		panelError = '';
	}

	function appendLog(message, time) {
		panelLogs = [...panelLogs, { message, time }];
	}

	async function handlePackage() {
		if (!currentProject || packaging || syncing || exportingPdf) return;
		packaging = true;
		showPanel = true;
		panelTitle = 'Packaging to QField';
		syncMsg = '';
		syncPending = false;
		panelPercent = 0;
		panelLogs = [];
		panelStatus = 'running';
		panelError = '';
		opAbort = new AbortController();

		try {
			await packageToQfieldStream(currentProject.id, {
				signal: opAbort.signal,
				onProgress: (percent, message, time) => {
					panelPercent = percent;
					appendLog(message, time);
				},
				onDone: () => {
					panelStatus = 'done';
					panelPercent = 100;
				},
				onError: (message) => {
					panelError = message;
				}
			});
			panelStatus = 'done';
			panelPercent = 100;
		} catch (err) {
			if (err?.name === 'AbortError') return;
			panelStatus = 'error';
			panelError = String(err);
			appendLog(String(err));
		} finally {
			opAbort = null;
			packaging = false;
		}
	}

	async function handleSync() {
		if (!currentProject || syncing || packaging || exportingPdf) return;
		syncing = true;
		showPanel = true;
		panelTitle = 'Syncing from QField';
		syncMsg = '';
		syncError = false;
		syncPending = false;
		panelPercent = 0;
		panelLogs = [];
		panelStatus = 'running';
		panelError = '';
		opAbort = new AbortController();

		try {
			const result = await syncFromQfieldStream(currentProject.id, {
				signal: opAbort.signal,
				onProgress: (percent, message, time) => {
					panelPercent = percent;
					appendLog(message, time);
				},
				onDone: (res) => {
					panelStatus = 'done';
					panelPercent = 100;
					syncMsg = res?.message ?? '';
					syncPending = (res?.pending_media ?? 0) > 0;
					mapRefreshKey += 1;
				},
				onError: (message) => {
					panelError = message;
				}
			});
			panelStatus = 'done';
			panelPercent = 100;
			if (result) {
				syncMsg = result.message ?? '';
				syncPending = (result.pending_media ?? 0) > 0;
				mapRefreshKey += 1;
			}
		} catch (err) {
			if (err?.name === 'AbortError') return;
			panelStatus = 'error';
			panelError = String(err);
			syncError = true;
			syncMsg = String(err);
			appendLog(String(err));
		} finally {
			opAbort = null;
			syncing = false;
		}
	}

	async function handleExportPdf() {
		if (!currentProject || exportingPdf || packaging || syncing) return;
		exportingPdf = true;
		showPanel = true;
		panelTitle = 'Exporting diagnosis PDF';
		syncMsg = '';
		syncError = false;
		panelPercent = 0;
		panelLogs = [];
		panelStatus = 'running';
		panelError = '';
		opAbort = new AbortController();

		try {
			const result = await exportDiagnosisPdfStream(currentProject.id, {
				signal: opAbort.signal,
				onProgress: (percent, message, time) => {
					panelPercent = percent;
					appendLog(message, time);
				},
				onDone: () => {
					panelStatus = 'done';
					panelPercent = 100;
				},
				onError: (message) => {
					panelError = message;
				}
			});
			panelStatus = 'done';
			panelPercent = 100;
			const filename = result?.filename || result?.download_path;
			if (!filename) throw new Error('Export finished without a downloadable file');
			const { blob, filename: dlName } = await downloadDiagnosisPdf(currentProject.id, filename, {
				signal: opAbort.signal
			});
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = dlName || filename;
			document.body.appendChild(a);
			a.click();
			a.remove();
			URL.revokeObjectURL(url);
			appendLog(`Downloaded ${dlName || filename}`);
		} catch (err) {
			if (err?.name === 'AbortError') return;
			panelStatus = 'error';
			panelError = String(err);
			syncError = true;
			syncMsg = String(err);
			appendLog(String(err));
		} finally {
			opAbort = null;
			exportingPdf = false;
		}
	}
</script>

<svelte:head>
	<title>{currentProject ? `${currentProject.name} · Diagnose` : 'Diagnose'}</title>
</svelte:head>

{#if loading}
	<div
		class="flex h-screen flex-col items-center justify-center gap-4 bg-white px-6 font-body"
		role="status"
		aria-live="polite"
	>
		<div
			class="h-10 w-10 animate-spin rounded-full border-2 border-brand-navy/20 border-t-brand-blue"
			aria-hidden="true"
		></div>
		<p class="m-0 font-headline text-lg font-semibold text-brand-navy">Loading project…</p>
		<p class="m-0 text-sm text-brand-steel">Fetching project details</p>
	</div>
{:else if loadError || !currentProject}
	<div class="flex h-screen flex-col items-center justify-center gap-4 bg-white px-6 font-body">
		<p class="m-0 max-w-md text-center text-brand-navy">{loadError || 'Project not found'}</p>
		<div class="flex flex-wrap items-center justify-center gap-2">
			{#if loadError}
				<button
					type="button"
					class="cursor-pointer rounded bg-brand-blue px-4 py-2 font-body text-white hover:bg-brand-deep"
					onclick={retryLoad}
				>
					Retry
				</button>
			{/if}
			<button
				type="button"
				class="cursor-pointer rounded border border-brand-navy/20 bg-white px-4 py-2 font-body text-brand-navy hover:bg-brand-sky/20"
				onclick={backToProjects}
			>
				← Back to projects
			</button>
		</div>
	</div>
{:else}
	<div class="relative flex h-screen flex-col bg-white font-body">
		<ModuleHeader
			title="Diagnose"
			titleHref="/diagnose"
			project={currentProject.name}
			subtitle={currentProject.watershed_name}
			wide
		>
			<button type="button" onclick={() => goto(appPath(`/diagnose/${slug}/members`))}>Members</button>
			<button type="button" disabled={packaging || syncing || exportingPdf} onclick={handleExportPdf}>
				{exportingPdf ? 'Exporting PDF…' : 'Export PDF'}
			</button>
			<button type="button" disabled={packaging || syncing || exportingPdf} onclick={handlePackage}>
				{packaging ? 'Packaging…' : 'Package to QField'}
			</button>
			<button type="button" disabled={packaging || syncing || exportingPdf} onclick={handleSync}>
				{syncing ? 'Syncing…' : 'Sync from QField'}
			</button>
		</ModuleHeader>

		{#if syncMsg && !syncing}
			<div
				class="flex items-start justify-between gap-2 border-b px-4 py-2 {syncError
					? 'border-red-200 bg-red-50 text-red-800'
					: syncPending
						? 'border-amber-200 bg-amber-50 text-amber-900'
						: 'border-brand-blue/25 bg-white text-brand-navy'}"
			>
				<span class="text-sm">{syncMsg}</span>
				<button
					onclick={() => {
						syncMsg = '';
						syncError = false;
						syncPending = false;
					}}
					class="ml-2 shrink-0 cursor-pointer rounded p-0.5 opacity-60 hover:opacity-100 {syncError
						? 'hover:bg-red-200'
						: syncPending
							? 'hover:bg-amber-200'
							: 'hover:bg-brand-sky/30'}"
					aria-label="Dismiss"
				>
					<svg
						xmlns="http://www.w3.org/2000/svg"
						class="h-4 w-4"
						viewBox="0 0 20 20"
						fill="currentColor"
					>
						<path
							fill-rule="evenodd"
							d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
							clip-rule="evenodd"
						/>
					</svg>
				</button>
			</div>
		{/if}

		<main class="relative min-h-0 flex-1 overflow-hidden">
			{#key currentProject.id}
				<div class="h-full">
					<MapView project={currentProject} refreshKey={mapRefreshKey} />
				</div>
			{/key}

			{#if showPanel}
				<PackageProgressPanel
					title={panelTitle}
					percent={panelPercent}
					logs={panelLogs}
					status={packaging || syncing || exportingPdf ? 'running' : panelStatus}
					error={panelError}
					onClose={dismissPanel}
				/>
			{/if}
		</main>
	</div>
{/if}
