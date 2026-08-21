<script>
	/** @type {{ title?: string, percent: number, logs: Array<{time?: string, message: string}>, status: 'running' | 'done' | 'error', error?: string, onClose?: () => void }} */
	let { title = 'QField', percent = 0, logs = [], status = 'running', error = '', onClose } = $props();

	let logEl = $state(null);

	$effect(() => {
		logs;
		if (logEl) {
			logEl.scrollTop = logEl.scrollHeight;
		}
	});

	function formatTime(iso) {
		if (!iso) return '';
		try {
			return new Date(iso).toLocaleTimeString([], {
				hour: '2-digit',
				minute: '2-digit',
				second: '2-digit'
			});
		} catch {
			return '';
		}
	}
</script>

<div
	class="pointer-events-auto fixed right-0 bottom-0 left-0 z-50 border-t border-brand-blue/30 bg-brand-navy/95 font-body text-white shadow-2xl backdrop-blur-sm"
	role="status"
	aria-live="polite"
	aria-label="QField packaging progress"
>
	<div class="flex items-center gap-3 border-b border-brand-blue/30 px-4 py-2">
		<div class="min-w-0 flex-1">
			<div class="mb-1 flex items-center justify-between gap-2 text-sm">
				<span class="font-headline font-medium">
				{#if status === 'running'}
					{title}…
				{:else if status === 'done'}
					{title} — complete
				{:else}
					{title} — failed
				{/if}
				</span>
				<span class="tabular-nums text-brand-sky/80">{Math.round(percent)}%</span>
			</div>
			<div class="h-2 overflow-hidden rounded-full bg-brand-navy">
				<div
					class="h-full rounded-full transition-all duration-300 ease-out {status === 'error'
						? 'bg-red-500'
						: status === 'done'
							? 'bg-brand-blue'
							: 'bg-brand-sky'}"
					style="width: {Math.max(status === 'running' ? 2 : 0, percent)}%"
				></div>
			</div>
		</div>
		{#if status !== 'running' && onClose}
			<button
				type="button"
				class="shrink-0 cursor-pointer rounded border border-brand-blue/50 bg-brand-deep px-2.5 py-1 font-body text-xs text-white hover:bg-brand-blue/30"
				onclick={onClose}
			>
				Dismiss
			</button>
		{/if}
	</div>

	<div bind:this={logEl} class="max-h-36 overflow-y-auto px-4 py-2 font-mono text-xs leading-relaxed">
		{#if error}
			<p class="m-0 mb-2 text-red-300">{error}</p>
		{/if}
		{#each logs as entry, i (i)}
			<div class="flex gap-2 text-white/90">
				{#if entry.time}
					<span class="shrink-0 text-brand-sky/60">{formatTime(entry.time)}</span>
				{/if}
				<span class="min-w-0 break-words">{entry.message}</span>
			</div>
		{/each}
		{#if logs.length === 0 && status === 'running'}
			<p class="m-0 text-brand-sky/60">Starting…</p>
		{/if}
	</div>
</div>
