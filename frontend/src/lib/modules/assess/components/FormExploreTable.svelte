<script>
	/** @type {{ columns: any[], rows: any[] }} */
	let { columns = [], rows = [] } = $props();

	let query = $state('');
	let sortKey = $state('');
	let sortDir = $state(1);
	let page = $state(1);
	const pageSize = 50;

	const displayCols = $derived(
		(columns || []).filter((c) => c.type !== 'geopoint').concat(
			rows.some((r) => r.lat != null) ? [{ name: '_coords', label: 'Lat / Lon', type: 'text' }] : []
		)
	);

	const filtered = $derived.by(() => {
		const q = query.trim().toLowerCase();
		let list = rows || [];
		if (q) {
			list = list.filter((row) =>
				displayCols.some((c) => {
					const v = c.name === '_coords' ? `${row.lat},${row.lon}` : row[c.name];
					return String(v ?? '')
						.toLowerCase()
						.includes(q);
				})
			);
		}
		if (sortKey) {
			list = [...list].sort((a, b) => {
				const av = sortKey === '_coords' ? a.lat : a[sortKey];
				const bv = sortKey === '_coords' ? b.lat : b[sortKey];
				if (av == null && bv == null) return 0;
				if (av == null) return 1;
				if (bv == null) return -1;
				if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * sortDir;
				return String(av).localeCompare(String(bv)) * sortDir;
			});
		}
		return list;
	});

	const pageCount = $derived(Math.max(1, Math.ceil(filtered.length / pageSize)));
	const pageRows = $derived.by(() => {
		const safePage = Math.min(page, Math.max(1, Math.ceil(filtered.length / pageSize) || 1));
		return filtered.slice((safePage - 1) * pageSize, safePage * pageSize);
	});

	function toggleSort(name) {
		if (sortKey === name) sortDir = -sortDir;
		else {
			sortKey = name;
			sortDir = 1;
		}
		page = 1;
	}

	function cellValue(row, col) {
		if (col.name === '_coords') {
			if (row.lat == null || row.lon == null) return '—';
			return `${Number(row.lat).toFixed(5)}, ${Number(row.lon).toFixed(5)}`;
		}
		const v = row[col.name];
		if (v === null || v === undefined || v === '') return '—';
		if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(2);
		return String(v);
	}
</script>

<div class="flex flex-col gap-3">
	<div class="flex flex-wrap items-center justify-between gap-3">
		<input
			type="search"
			class="w-full max-w-sm rounded-lg border border-brand-navy/15 px-3 py-2 text-sm outline-none focus:border-[#16a34a] focus:ring-2 focus:ring-[#16a34a]/20"
			placeholder="Filter rows…"
			value={query}
			oninput={(e) => {
				query = e.currentTarget.value;
				page = 1;
			}}
		/>
		<p class="m-0 text-xs text-brand-steel">
			{filtered.length} row{filtered.length === 1 ? '' : 's'}
			{#if filtered.length !== rows.length}
				(of {rows.length})
			{/if}
		</p>
	</div>

	<div class="overflow-auto rounded-xl border border-brand-navy/10 bg-white shadow-sm">
		<table class="min-w-full border-collapse text-left text-sm">
			<thead class="sticky top-0 bg-[#f0fdf4]">
				<tr>
					{#each displayCols as col (col.name)}
						<th class="border-b border-brand-navy/10 px-3 py-2 font-semibold text-brand-navy">
							<button type="button" class="inline-flex items-center gap-1 border-0 bg-transparent p-0" onclick={() => toggleSort(col.name)}>
								{col.label}
								{#if sortKey === col.name}
									<span class="text-[10px] text-[#16a34a]">{sortDir > 0 ? '▲' : '▼'}</span>
								{/if}
							</button>
						</th>
					{/each}
				</tr>
			</thead>
			<tbody>
				{#each pageRows as row, i (row.instanceId || i)}
					<tr class="odd:bg-white even:bg-[#fafafa] hover:bg-[#f0fdf4]/60">
						{#each displayCols as col (col.name)}
							<td class="border-b border-brand-navy/5 px-3 py-2 text-brand-navy/90 whitespace-nowrap">
								{cellValue(row, col)}
							</td>
						{/each}
					</tr>
				{:else}
					<tr>
						<td class="px-3 py-8 text-center text-brand-steel" colspan={displayCols.length || 1}>
							No rows match.
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	{#if pageCount > 1}
		<div class="flex items-center justify-center gap-2">
			<button type="button" class="action-btn" disabled={page <= 1} onclick={() => (page -= 1)}>Prev</button>
			<span class="text-xs text-brand-steel">Page {page} / {pageCount}</span>
			<button
				type="button"
				class="action-btn"
				disabled={page >= pageCount}
				onclick={() => (page += 1)}>Next</button
			>
		</div>
	{/if}
</div>
