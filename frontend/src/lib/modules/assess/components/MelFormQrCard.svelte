<script>
	import QRCode from 'qrcode';

	/**
	 * @type {{
	 *   formName?: string,
	 *   packageTitle?: string,
	 *   xmlFormId?: string,
	 *   fieldCount?: number | null,
	 *   collectQr?: { payload?: string, instructions?: string, projectName?: string } | null,
	 *   compact?: boolean,
	 *   sidebar?: boolean
	 * }}
	 */
	let {
		formName = '',
		packageTitle = '',
		xmlFormId = '',
		fieldCount = null,
		collectQr = null,
		compact = false,
		sidebar = false
	} = $props();

	/** @type {HTMLCanvasElement | null} */
	let canvasEl = $state(null);
	/** @type {HTMLDivElement | null} */
	let artEl = $state(null);
	let renderError = $state('');
	let qrWidth = $state(200);

	$effect(() => {
		if (!sidebar || !artEl) return;
		const update = () => {
			const w = Math.floor(artEl?.clientWidth || 0);
			if (w > 0 && Math.abs(w - qrWidth) > 1) qrWidth = w;
		};
		update();
		const ro = new ResizeObserver(update);
		ro.observe(artEl);
		return () => ro.disconnect();
	});

	$effect(() => {
		const payload = collectQr?.payload;
		if (!payload || !canvasEl) {
			renderError = '';
			return;
		}
		const width = sidebar ? Math.max(148, qrWidth) : compact ? 160 : 200;
		QRCode.toCanvas(canvasEl, payload, {
			errorCorrectionLevel: 'M',
			margin: 1,
			width,
			color: { dark: '#1a2530', light: '#ffffff' }
		})
			.then(() => {
				renderError = '';
			})
			.catch((err) => {
				renderError = String(err);
			});
	});
</script>

<article class="qr-card" class:compact class:sidebar>
	<div class="qr-meta min-w-0">
		<p class="m-0 font-display text-base text-[#1a2530]">
			{formName || packageTitle || 'Form'}
		</p>
		{#if packageTitle && formName && packageTitle !== formName}
			<p class="m-0 mt-0.5 font-body text-sm text-[#56646f]">{packageTitle}</p>
		{/if}
		{#if xmlFormId}
			<p class="m-0 mt-1 font-mono text-[11px] text-[#6b7885] break-all">{xmlFormId}</p>
		{/if}
		{#if fieldCount != null}
			<p class="m-0 mt-1 font-body text-xs text-[#56646f]">{fieldCount} fields</p>
		{/if}
		{#if collectQr?.instructions && !sidebar}
			<p class="m-0 mt-2 font-body text-xs leading-relaxed text-[#56646f]">
				{collectQr.instructions}
			</p>
		{/if}
	</div>
	<div class="qr-art" bind:this={artEl}>
		{#if collectQr?.payload}
			<canvas bind:this={canvasEl}></canvas>
			{#if renderError}
				<p class="m-0 mt-1 font-body text-xs text-red-700">{renderError}</p>
			{/if}
		{:else}
			<p class="m-0 font-body text-xs text-[#56646f]">QR unavailable</p>
		{/if}
	</div>
	{#if sidebar && collectQr?.instructions}
		<p class="m-0 font-body text-xs leading-relaxed text-[#56646f]">
			{collectQr.instructions}
		</p>
	{/if}
</article>

<style>
	.qr-card {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 1rem 1.1rem;
		border-radius: 0.85rem;
		border: 1px solid rgba(20, 40, 60, 0.1);
		background: white;
	}
	.qr-art {
		flex: none;
		display: flex;
		flex-direction: column;
		align-items: center;
	}
	.qr-art canvas {
		display: block;
		border-radius: 0.4rem;
		border: 1px solid rgba(20, 40, 60, 0.08);
	}
	.qr-card.sidebar {
		flex-direction: column;
		align-items: stretch;
		justify-content: flex-start;
		flex-wrap: nowrap;
		gap: 0.7rem;
		padding: 0;
		border: none;
		border-radius: 0;
		background: transparent;
	}
	.qr-card.sidebar .qr-art {
		width: 100%;
		align-items: stretch;
	}
	.qr-card.sidebar .qr-art canvas {
		width: 100%;
		height: auto;
	}
</style>
