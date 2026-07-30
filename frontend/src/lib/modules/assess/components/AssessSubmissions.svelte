<script>
	import { fade, fly, scale } from 'svelte/transition';
	import { fetchSubmissions } from '$lib/modules/assess/api';

	/** @type {{ project: any, form: any, onBack: () => void, onHome: () => void }} */
	let { project, form, onBack, onHome } = $props();

	let rows = $state([]);
	let loading = $state(true);
	let error = $state('');
	let query = $state('');
	let selected = $state(null);

	const HIDDEN = new Set(['__id', '__system']);

	$effect(() => {
		if (project?.id && form?.xmlFormId) loadSubmissions(project.id, form.xmlFormId);
	});

	async function loadSubmissions(projectId, xmlFormId) {
		loading = true;
		error = '';
		rows = [];
		selected = null;
		try {
			const data = await fetchSubmissions(projectId, xmlFormId);
			rows = Array.isArray(data) ? data : (data?.value ?? []);
		} catch (err) {
			error = String(err);
		} finally {
			loading = false;
		}
	}

	// Derive scalar columns from the union of keys across all submissions.
	let columns = $derived.by(() => {
		const seen = new Set();
		const cols = [];
		for (const r of rows) {
			for (const k of Object.keys(r ?? {})) {
				if (HIDDEN.has(k) || seen.has(k)) continue;
				const v = r[k];
				if (v === null || typeof v !== 'object') {
					seen.add(k);
					cols.push(k);
				}
			}
		}
		return cols.slice(0, 6);
	});

	let filtered = $derived(
		query.trim()
			? rows.filter((r) => JSON.stringify(r).toLowerCase().includes(query.trim().toLowerCase()))
			: rows
	);

	function prettyKey(k) {
		return String(k)
			.replace(/[_.]/g, ' ')
			.replace(/([a-z])([A-Z])/g, '$1 $2')
			.replace(/\b\w/g, (c) => c.toUpperCase())
			.trim();
	}

	function cell(v) {
		if (v === null || v === undefined || v === '') return '—';
		if (typeof v === 'boolean') return v ? 'Yes' : 'No';
		if (typeof v === 'object') return Array.isArray(v) ? `${v.length} item(s)` : '{…}';
		return String(v);
	}

	function submittedAt(r) {
		const d = r?.__system?.submissionDate;
		if (!d) return '—';
		const dt = new Date(d);
		return Number.isNaN(dt.getTime()) ? d : dt.toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' });
	}

	function submitter(r) {
		return r?.__system?.submitterName ?? r?.__system?.submitterId ?? 'Unknown';
	}

	function reviewState(r) {
		return r?.__system?.reviewState ?? null;
	}

	// Flatten a submission for the detail drawer.
	function flatten(obj, prefix = '', out = []) {
		for (const [k, v] of Object.entries(obj ?? {})) {
			if (k === '__id') continue;
			const key = prefix ? `${prefix}.${k}` : k;
			if (v && typeof v === 'object' && !Array.isArray(v)) {
				flatten(v, key, out);
			} else {
				out.push([key, v]);
			}
		}
		return out;
	}

	let detailRows = $derived(selected ? flatten(selected) : []);

	function downloadJson() {
		const blob = new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `${form?.xmlFormId ?? 'submissions'}.json`;
		a.click();
		URL.revokeObjectURL(url);
	}
</script>

<div class="relative min-h-screen bg-transparent font-body">
	<!-- Breadcrumb -->
	<div class="sticky top-0 z-30 border-b border-brand-navy/10 bg-white/80 backdrop-blur-md">
		<div class="mx-auto flex max-w-6xl items-center gap-2 px-6 py-3 md:px-10">
			<button class="rounded-full border border-brand-navy/15 bg-white px-3 py-1.5 font-body text-sm text-brand-navy transition hover:border-brand-blue hover:text-brand-blue" onclick={onHome}>Projects</button>
			<span class="text-brand-steel/50">/</span>
			<button class="max-w-[10rem] truncate rounded-full border border-brand-navy/15 bg-white px-3 py-1.5 font-body text-sm text-brand-navy transition hover:border-brand-blue hover:text-brand-blue" onclick={onBack}>{project?.name}</button>
			<span class="text-brand-steel/50">/</span>
			<span class="truncate font-headline text-sm font-semibold text-brand-navy">{form?.name ?? form?.xmlFormId}</span>
		</div>
	</div>

	<!-- Hero -->
	<div class="relative overflow-hidden">
		<div class="subs-hero absolute inset-0"></div>
		<div class="relative z-10 mx-auto flex max-w-6xl flex-col gap-4 px-6 py-8 md:flex-row md:items-end md:justify-between md:px-10">
			<div in:fly={{ y: 14, duration: 400 }}>
				<p class="m-0 font-body text-xs font-semibold tracking-[0.2em] text-brand-steel uppercase">{form?.xmlFormId}</p>
				<h1 class="m-0 mt-1 font-headline text-3xl font-semibold text-brand-navy">Submissions</h1>
				<div class="mt-2 flex items-center gap-2">
					<span class="inline-flex items-center gap-1.5 rounded-full bg-brand-blue/10 px-3 py-1 font-body text-sm font-semibold text-brand-blue">
						<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="h-4 w-4"><path d="M4 7h16M4 12h16M4 17h10" stroke-linecap="round" /></svg>
						{rows.length} record{rows.length === 1 ? '' : 's'}
					</span>
				</div>
			</div>
			<div class="flex items-center gap-2" in:fly={{ y: 14, duration: 400, delay: 80 }}>
				<div class="relative">
					<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-brand-steel"><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" stroke-linecap="round" /></svg>
					<input type="text" placeholder="Search records…" bind:value={query} class="w-52 rounded-full border border-brand-navy/15 bg-white/90 py-2 pr-3 pl-9 font-body text-sm text-brand-navy shadow-sm outline-none transition focus:border-brand-blue focus:ring-2 focus:ring-brand-blue/20" />
				</div>
				<button class="flex items-center gap-1.5 rounded-full border border-brand-navy/15 bg-white px-3.5 py-2 font-body text-sm font-medium text-brand-navy transition hover:border-brand-blue hover:text-brand-blue disabled:opacity-50" disabled={rows.length === 0} onclick={downloadJson}>
					<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" class="h-4 w-4"><path d="M12 3v12M7 10l5 5 5-5M5 21h14" stroke-linecap="round" stroke-linejoin="round" /></svg>
					JSON
				</button>
			</div>
		</div>
	</div>

	<main class="relative z-10 mx-auto max-w-6xl px-6 py-6 md:px-10">
		{#if error}
			<div in:fade class="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 font-body text-sm text-red-700">{error}</div>
		{/if}

		{#if loading}
			<div class="overflow-hidden rounded-2xl border border-brand-navy/10 bg-white shadow-sm">
				{#each Array(6) as _, i (i)}
					<div class="flex items-center gap-4 border-b border-brand-navy/5 px-4 py-3.5 last:border-0">
						<div class="h-4 w-4 animate-pulse rounded bg-brand-navy/10"></div>
						<div class="h-4 flex-1 animate-pulse rounded bg-brand-navy/10"></div>
						<div class="h-4 w-24 animate-pulse rounded bg-brand-navy/10"></div>
					</div>
				{/each}
			</div>
		{:else if rows.length === 0}
			<div in:fade class="mx-auto mt-10 max-w-md rounded-2xl border border-dashed border-brand-steel/40 bg-white p-8 text-center shadow-sm">
				<div class="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-steel/10 text-brand-steel">
					<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" class="h-7 w-7"><path d="M4 7h16M4 12h16M4 17h10" stroke-linecap="round" /></svg>
				</div>
				<h3 class="m-0 font-headline text-lg font-semibold text-brand-navy">No submissions yet</h3>
				<p class="m-0 mt-1 font-body text-sm text-brand-steel">Data collected for this form will appear here.</p>
			</div>
		{:else}
			<div class="overflow-x-auto rounded-2xl border border-brand-navy/10 bg-white shadow-sm">
				<table class="w-full border-collapse font-body text-sm">
					<thead>
						<tr class="border-b border-brand-navy/10 bg-brand-navy/[0.03] text-left">
							<th class="px-4 py-3 font-headline text-xs font-semibold tracking-wide text-brand-steel uppercase">#</th>
							{#each columns as col (col)}
								<th class="px-4 py-3 font-headline text-xs font-semibold tracking-wide text-brand-steel uppercase whitespace-nowrap">{prettyKey(col)}</th>
							{/each}
							<th class="px-4 py-3 font-headline text-xs font-semibold tracking-wide text-brand-steel uppercase whitespace-nowrap">Submitted</th>
							<th class="px-4 py-3"></th>
						</tr>
					</thead>
					<tbody>
						{#each filtered as row, i (row.__id ?? i)}
							<tr
								in:fade={{ duration: 150, delay: Math.min(i, 12) * 20 }}
								class="group cursor-pointer border-b border-brand-navy/5 transition-colors last:border-0 hover:bg-brand-sky/10"
								onclick={() => (selected = row)}
							>
								<td class="px-4 py-3 font-mono text-xs text-brand-steel">{i + 1}</td>
								{#each columns as col (col)}
									<td class="max-w-[16rem] truncate px-4 py-3 text-brand-navy" title={cell(row[col])}>{cell(row[col])}</td>
								{/each}
								<td class="px-4 py-3 whitespace-nowrap text-brand-steel">
									<div class="flex flex-col">
										<span>{submittedAt(row)}</span>
										<span class="text-[11px] text-brand-steel/70">{submitter(row)}</span>
									</div>
								</td>
								<td class="px-4 py-3 text-right">
									<span class="inline-flex items-center gap-1 font-body text-xs font-medium text-brand-blue opacity-0 transition-opacity group-hover:opacity-100">
										View
										<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="h-3.5 w-3.5"><path d="M9 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round" /></svg>
									</span>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			{#if filtered.length === 0}
				<p class="mt-6 text-center font-body text-sm text-brand-steel">No records match “{query}”.</p>
			{/if}
		{/if}
	</main>

	<!-- Detail drawer -->
	{#if selected}
		<div class="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true">
			<button class="absolute inset-0 cursor-default bg-brand-navy/40 backdrop-blur-sm" aria-label="Close details" transition:fade={{ duration: 200 }} onclick={() => (selected = null)}></button>
			<aside class="relative flex h-full w-full max-w-lg flex-col bg-white shadow-2xl" transition:fly={{ x: 400, duration: 280 }}>
				<header class="drawer-head flex items-start justify-between gap-3 px-6 py-5 text-white">
					<div class="min-w-0">
						<p class="m-0 font-body text-xs tracking-wide text-white/80 uppercase">Submission</p>
						<h2 class="m-0 mt-0.5 truncate font-headline text-lg font-semibold text-white">{form?.name ?? form?.xmlFormId}</h2>
						<p class="m-0 mt-1 font-mono text-[11px] break-all text-white/70">{selected.__id}</p>
					</div>
					<button class="shrink-0 rounded-full bg-white/15 p-1.5 text-white transition hover:bg-white/25" aria-label="Close" onclick={() => (selected = null)}>
						<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="h-5 w-5"><path fill-rule="evenodd" d="M4.3 4.3a1 1 0 0 1 1.4 0L10 8.6l4.3-4.3a1 1 0 1 1 1.4 1.4L11.4 10l4.3 4.3a1 1 0 0 1-1.4 1.4L10 11.4l-4.3 4.3a1 1 0 0 1-1.4-1.4L8.6 10 4.3 5.7a1 1 0 0 1 0-1.4z" clip-rule="evenodd" /></svg>
					</button>
				</header>
				<div class="min-h-0 flex-1 overflow-y-auto px-6 py-4">
					<dl class="flex flex-col divide-y divide-brand-navy/10">
						{#each detailRows as [key, value] (key)}
							<div class="flex flex-col gap-0.5 py-2.5">
								<dt class="font-body text-[11px] font-semibold tracking-wide text-brand-steel uppercase">{prettyKey(key)}</dt>
								<dd class="m-0 font-body text-sm break-words text-brand-navy">{cell(value)}</dd>
							</div>
						{/each}
					</dl>
				</div>
			</aside>
		</div>
	{/if}
</div>

<style>
	.subs-hero {
		background:
			radial-gradient(120% 140% at 100% 0%, color-mix(in srgb, #7dc3ff 20%, transparent), transparent 60%),
			radial-gradient(120% 120% at 0% 0%, color-mix(in srgb, #3969a7 12%, transparent), transparent 55%);
	}
	.drawer-head {
		background: linear-gradient(135deg, #00296b, #3969a7);
	}
</style>
