<script>
	import { onMount } from 'svelte';
	import QRCode from 'qrcode';

	/**
	 * @type {{
	 *   open: boolean,
	 *   formName?: string,
	 *   packageTitle?: string,
	 *   xmlFormId?: string,
	 *   collectQr?: { payload?: string, instructions?: string, projectName?: string, serverUrl?: string } | null,
	 *   loading?: boolean,
	 *   error?: string,
	 *   onClose?: () => void
	 * }}
	 */
	let {
		open = false,
		formName = '',
		packageTitle = '',
		xmlFormId = '',
		collectQr = null,
		loading = false,
		error = '',
		onClose = () => {}
	} = $props();

	/** @type {HTMLCanvasElement | null} */
	let canvasEl = $state(null);
	let renderError = $state('');

	$effect(() => {
		if (!open) return;
		const payload = collectQr?.payload;
		if (!payload || !canvasEl) {
			renderError = '';
			return;
		}
		QRCode.toCanvas(canvasEl, payload, {
			errorCorrectionLevel: 'M',
			margin: 2,
			width: 220,
			color: { dark: '#1a2530', light: '#ffffff' }
		}).then(() => {
			renderError = '';
		}).catch((err) => {
			renderError = String(err);
		});
	});

	function handleKeydown(e) {
		if (e.key === 'Escape') onClose();
	}

	onMount(() => {
		window.addEventListener('keydown', handleKeydown);
		return () => window.removeEventListener('keydown', handleKeydown);
	});
</script>

{#if open}
	<div class="overlay" role="presentation" onclick={onClose}>
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="qr-title"
			onclick={(e) => e.stopPropagation()}
		>
			<div class="modal-head">
				<div class="min-w-0">
					<h2 id="qr-title" class="m-0 font-display text-xl text-[#1a2530]">Collect QR</h2>
					<p class="m-0 mt-1 truncate font-body text-sm text-[#56646f]">
						{formName || packageTitle || 'Form'}
					</p>
				</div>
				<button type="button" class="close-btn" onclick={onClose} aria-label="Close">×</button>
			</div>

			{#if xmlFormId}
				<p class="m-0 mt-2 font-mono text-[11px] text-[#6b7885]">{xmlFormId}</p>
			{/if}

			<div class="qr-body">
				{#if loading}
					<p class="font-body text-sm text-[#56646f]">Loading QR…</p>
				{:else if error}
					<p class="font-body text-sm text-red-700">{error}</p>
				{:else if !collectQr?.payload}
					<p class="font-body text-sm text-[#56646f]">
						QR is unavailable. Check ODK configuration and try again.
					</p>
				{:else}
					<canvas bind:this={canvasEl} class="qr-canvas"></canvas>
					{#if renderError}
						<p class="mt-2 font-body text-sm text-red-700">{renderError}</p>
					{/if}
					<p class="m-0 mt-3 max-w-xs text-center font-body text-xs leading-relaxed text-[#56646f]">
						{collectQr.instructions ||
							'Scan with ODK Collect to add this project, then open Get Blank Form.'}
					</p>
					{#if collectQr.projectName}
						<p class="m-0 mt-2 font-body text-[11px] text-[#6b7885]">
							Project: {collectQr.projectName}
						</p>
					{/if}
				{/if}
			</div>
		</div>
	</div>
{/if}

<style>
	.overlay {
		position: fixed;
		inset: 0;
		z-index: 80;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
		background: rgba(15, 23, 32, 0.45);
	}
	.modal {
		width: min(24rem, 100%);
		border-radius: 1rem;
		border: 1px solid rgba(20, 40, 60, 0.1);
		background: white;
		padding: 1.15rem 1.25rem 1.35rem;
		box-shadow: 0 18px 40px rgba(15, 23, 32, 0.18);
	}
	.modal-head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 0.75rem;
	}
	.close-btn {
		flex: none;
		cursor: pointer;
		border: none;
		background: transparent;
		font-size: 1.5rem;
		line-height: 1;
		color: #6b7885;
		padding: 0 0.15rem;
	}
	.qr-body {
		display: flex;
		flex-direction: column;
		align-items: center;
		margin-top: 1.1rem;
		min-height: 12rem;
		justify-content: center;
	}
	.qr-canvas {
		border-radius: 0.5rem;
		border: 1px solid rgba(20, 40, 60, 0.08);
	}
</style>
