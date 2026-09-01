<script>
	/** @type {{
	 *   id?: string,
	 *   label?: string,
	 *   placeholder?: string,
	 *   options?: Array<{ value: string, label: string }>,
	 *   value?: string,
	 *   disabled?: boolean,
	 *   loading?: boolean,
	 *   emptyText?: string,
	 *   onChange?: (value: string) => void
	 * }} */
	let {
		id = 'searchable-select',
		label = '',
		placeholder = 'Search…',
		options = [],
		value = $bindable(''),
		disabled = false,
		loading = false,
		emptyText = 'No matches',
		onChange
	} = $props();

	let open = $state(false);
	let filter = $state('');
	let rootEl;

	const selectedLabel = $derived(
		options.find((o) => o.value === value)?.label ?? (value ? value : '')
	);

	const filtered = $derived.by(() => {
		const q = filter.trim().toLowerCase();
		if (!q) return options.slice(0, 300);
		return options.filter((o) => o.label.toLowerCase().includes(q)).slice(0, 300);
	});

	function toggle() {
		if (disabled) return;
		open = !open;
		if (open) filter = '';
	}

	function pick(opt) {
		value = opt.value;
		open = false;
		filter = '';
		onChange?.(opt.value);
	}

	function onDocClick(e) {
		if (!rootEl?.contains(e.target)) open = false;
	}

	$effect(() => {
		if (typeof document === 'undefined') return;
		if (open) {
			document.addEventListener('click', onDocClick);
			return () => document.removeEventListener('click', onDocClick);
		}
	});
</script>

<div class="relative" bind:this={rootEl}>
	{#if label}
		<label class="mb-1 block font-body text-sm font-medium text-brand-navy" for={id}>{label}</label>
	{/if}
	<button
		id={id}
		type="button"
		class="flex w-full items-center justify-between rounded border border-brand-navy/20 bg-white px-3 py-2 text-left font-body text-sm disabled:opacity-50"
		{disabled}
		aria-haspopup="listbox"
		aria-expanded={open}
		onclick={toggle}
	>
		<span class={value ? 'text-brand-navy' : 'text-brand-steel'}>
			{loading ? 'Loading…' : selectedLabel || placeholder}
		</span>
		<span class="text-brand-steel" aria-hidden="true">▾</span>
	</button>

	{#if open && !disabled}
		<div
			class="absolute z-30 mt-1 w-full overflow-hidden rounded border border-brand-navy/15 bg-white shadow-md"
			role="listbox"
		>
			<input
				type="search"
				class="w-full border-0 border-b border-brand-navy/10 px-3 py-2 font-body text-sm outline-none"
				placeholder={placeholder}
				bind:value={filter}
				onclick={(e) => e.stopPropagation()}
			/>
			<ul class="m-0 max-h-52 list-none overflow-auto p-0">
				{#if filtered.length === 0}
					<li class="px-3 py-2 text-sm text-brand-steel">{emptyText}</li>
				{:else}
					{#each filtered as opt (opt.value)}
						<li>
							<button
								type="button"
								class="w-full px-3 py-2 text-left font-body text-sm hover:bg-brand-sky/30 {opt.value ===
								value
									? 'bg-brand-sky/20'
									: ''}"
								onclick={() => pick(opt)}
							>
								{opt.label}
							</button>
						</li>
					{/each}
				{/if}
			</ul>
		</div>
	{/if}
</div>
