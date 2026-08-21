<script>
	import QRCode from 'qrcode';

	/**
	 * @type {{
	 *   formName?: string,
	 *   packageTitle?: string,
	 *   xmlFormId?: string,
	 *   fieldCount?: number | null,
	 *   collectQr?: { payload?: string, instructions?: string, projectName?: string } | null,
	 *   compact?: boolean
	 * }}
	 */
	let {
		formName = '',
		packageTitle = '',
		xmlFormId = '',
		fieldCount = null,
		collectQr = null,
		compact = false
	} = $props();

	/** @type {HTMLCanvasElement | null} */
	let canvasEl = $state(null);
	let renderError = $state('');

	$effect(() => {
		const payload = collectQr?.payload;
		if (!payload || !canvasEl) {
			renderError = '';
			return;
		}
		QRCode.toCanvas(canvasEl, payload, {
			errorCorrectionLevel: 'M',
			margin: 2,
			width: compact ? 160 : 200,
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

<article class="qr-card" class:compact>
	<div class="qr-meta min-w-0">
		<p class="m-0 font-display text-base text-[#1a2530]">
			{formName || packageTitle || 'Form'}
		</p>
		{#if packageTitle && formName && packageTitle !== formName}
			<p class="m-0 mt-0.5 font-body text-sm text-[#56646f]">{packageTitle}</p>
		{/if}
		{#if xmlFormId}
			<p class="m-0 mt-1 font-mono text-[11px] text-[#6b7885]">{xmlFormId}</p>
		{/if}
		{#if fieldCount != null}
			<p class="m-0 mt-1 font-body text-xs text-[#56646f]">{fieldCount} fields</p>
		{/if}
		{#if collectQr?.instructions}
			<p class="m-0 mt-2 font-body text-xs leading-relaxed text-[#56646f]">
				{collectQr.instructions}
			</p>
		{/if}
	</div>
	<div class="qr-art">
		{#if collectQr?.payload}
			<canvas bind:this={canvasEl}></canvas>
			{#if renderError}
				<p class="m-0 mt-1 font-body text-xs text-red-700">{renderError}</p>
			{/if}
		{:else}
			<p class="m-0 font-body text-xs text-[#56646f]">QR unavailable</p>
		{/if}
	</div>
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
		border-radius: 0.4rem;
		border: 1px solid rgba(20, 40, 60, 0.08);
	}
</style>
