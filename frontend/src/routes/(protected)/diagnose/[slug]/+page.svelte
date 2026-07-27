<script>
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import MapView from '$lib/modules/diagnose/components/MapView.svelte';
	import PackageProgressPanel from '$lib/shared/components/PackageProgressPanel.svelte';
	import {
		fetchProjects,
		packageToQfieldStream,
		syncFromQfieldStream
	} from '$lib/modules/diagnose/api';
	import { findBySlug } from '$lib/shared/slug.js';

	let slug = $derived(page.params.slug);

	let currentProject = $state(null);
	let loading = $state(true);
	let loadError = $state('');
	let packaging = $state(false);
	let syncing = $state(false);
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

	async function loadProject(slugValue) {
		loading = true;
		loadError = '';
		currentProject = null;
		try {
			const data = await fetchProjects();
			const match = findBySlug(data.projects ?? [], slugValue);
			if (!match) {
				loadError = 'Project not found';
				return;
			}
			// fetchProjects() already returns the full project shape (_SELECT).
			currentProject = match;
		} catch (err) {
			loadError = String(err);
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		loadProject(slug);
	});

	function backToProjects() {
		goto('/diagnose');
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
		if (!currentProject || packaging || syncing) return;
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
		if (!currentProject || syncing || packaging) return;
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
</script>

<svelte:head>
	<title>{currentProject ? `${currentProject.name} · Diagnose` : 'Diagnose'}</title>
</svelte:head>

{#if loading}
	<div class="flex h-screen items-center justify-center bg-white font-body text-brand-steel">
		Loading project…
	</div>
{:else if loadError || !currentProject}
	<div class="flex h-screen flex-col items-center justify-center gap-4 bg-white font-body">
		<p class="m-0 text-brand-navy">{loadError || 'Project not found'}</p>
		<button
			class="cursor-pointer rounded bg-brand-blue px-4 py-2 font-body text-white hover:bg-brand-deep"
			onclick={backToProjects}
		>
			← Back to projects
		</button>
	</div>
{:else}
	<div class="relative flex h-screen flex-col bg-white font-body">
		<header class="flex items-center justify-between bg-brand-navy px-6 py-3 text-white">
			<div class="flex items-center gap-3">
				<button
					class="cursor-pointer rounded border border-brand-sky/40 bg-transparent px-2 py-1 font-body text-sm text-white hover:bg-white/10"
					onclick={backToProjects}
				>
					← Projects
				</button>
				<div>
					<h1 class="m-0 font-headline text-lg font-semibold">{currentProject.name}</h1>
					<p class="m-0 font-body text-xs text-brand-sky/90">{currentProject.watershed_name}</p>
				</div>
			</div>
			<nav class="flex flex-wrap gap-1.5">
				<button
					class="cursor-pointer rounded border border-brand-sky/40 bg-transparent px-3 py-1.5 font-body text-sm text-white hover:bg-white/10"
					onclick={() => goto(`/diagnose/${slug}/members`)}
				>
					Members
				</button>
				<button
					class="cursor-pointer rounded border border-brand-sky/40 bg-transparent px-3 py-1.5 font-body text-sm text-white hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60"
					disabled={packaging || syncing}
					onclick={handlePackage}
				>
					{packaging ? 'Packaging…' : 'Package to QField'}
				</button>
				<button
					class="cursor-pointer rounded border border-brand-blue bg-brand-blue px-3 py-1.5 font-body text-sm text-white hover:bg-brand-deep disabled:cursor-not-allowed disabled:opacity-60"
					disabled={packaging || syncing}
					onclick={handleSync}
				>
					{syncing ? 'Syncing…' : 'Sync from QField'}
				</button>
			</nav>
		</header>

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
					status={packaging || syncing ? 'running' : panelStatus}
					error={panelError}
					onClose={dismissPanel}
				/>
			{/if}
		</main>
	</div>
{/if}
