<script>
	import { appPath } from '$lib/shared/paths.js';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';
	import { fetchMelForms } from '$lib/modules/assess/mel-api';

	let forms = $state([]);
	let odkProjectId = $state(null);
	let loading = $state(true);
	let error = $state('');

	onMount(() => {
		loadForms();
	});

	async function loadForms() {
		loading = true;
		error = '';
		try {
			const res = await fetchMelForms();
			forms = res.forms ?? [];
			odkProjectId = res.odkProjectId ?? null;
		} catch (err) {
			error = String(err);
			forms = [];
		} finally {
			loading = false;
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

	function stateLabel(state) {
		if (!state) return 'Unknown';
		return String(state).replace(/_/g, ' ');
	}
</script>

<div class="relative min-h-screen bg-transparent font-body">
	<ModuleHeader title="Assess" subtitle="MEL plans" homeHref="/home">
		<button
			type="button"
			class="rounded bg-[#1b75e0] px-3 py-1.5 font-body text-sm font-medium text-white hover:bg-[#1565c0]"
			onclick={() => goto(appPath('/assess/new'))}
		>
			Create new MEL plan
		</button>
	</ModuleHeader>

	<main class="relative z-10 flex-1 overflow-auto p-6">
		<div class="mb-5 flex flex-wrap items-end justify-between gap-3">
			<div>
				<h2 class="m-0 font-headline text-lg font-semibold text-brand-navy">Your MEL forms</h2>
				<p class="m-0 mt-1 text-sm text-brand-steel">
					Forms published to the configured ODK project
					{#if odkProjectId != null}
						<span class="text-brand-navy">(ID {odkProjectId})</span>
					{/if}.
				</p>
			</div>
			<button
				type="button"
				class="action-btn"
				disabled={loading}
				onclick={loadForms}
			>
				{loading ? 'Refreshing…' : 'Refresh'}
			</button>
		</div>

		{#if error}
			<p class="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
		{/if}

		{#if loading && forms.length === 0}
			<p class="text-brand-steel">Loading MEL forms…</p>
		{:else if !loading && forms.length === 0 && !error}
			<section class="rounded-2xl border border-dashed border-brand-navy/20 bg-white px-6 py-12 text-center shadow-sm">
				<p class="m-0 font-headline text-base font-semibold text-brand-navy">No MEL plans yet</p>
				<p class="m-0 mt-2 text-sm text-brand-steel">
					Create a MEL plan to publish an intervention form into ODK Central.
				</p>
				<button
					type="button"
					class="mt-5 rounded bg-[#1b75e0] px-4 py-2 font-body text-sm font-medium text-white hover:bg-[#1565c0]"
					onclick={() => goto(appPath('/assess/new'))}
				>
					Create new MEL plan
				</button>
			</section>
		{:else}
			<div class="overflow-hidden rounded-2xl border border-brand-navy/10 bg-white shadow-sm">
				<table class="w-full border-collapse text-left text-sm">
					<thead class="bg-gray-50 text-xs tracking-wide text-brand-steel uppercase">
						<tr>
							<th class="px-4 py-3">Form</th>
							<th class="px-4 py-3">ID</th>
							<th class="px-4 py-3">State</th>
							<th class="px-4 py-3">Created</th>
						</tr>
					</thead>
					<tbody>
						{#each forms as form (form.xmlFormId)}
							<tr class="border-t border-brand-navy/8">
								<td class="px-4 py-3 font-medium text-brand-navy">{form.name}</td>
								<td class="px-4 py-3 font-mono text-xs text-brand-steel">{form.xmlFormId}</td>
								<td class="px-4 py-3 capitalize text-brand-steel">{stateLabel(form.state)}</td>
								<td class="px-4 py-3 text-brand-steel">{formatDate(form.createdAt ?? form.publishedAt)}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</main>
</div>

<style>
	.action-btn {
		cursor: pointer;
		border-radius: 0.5rem;
		border: 1px solid rgba(20, 40, 60, 0.12);
		background: white;
		padding: 0.4rem 0.75rem;
		font-family: inherit;
		font-size: 0.8125rem;
		font-weight: 500;
		color: #1a2530;
	}
</style>
