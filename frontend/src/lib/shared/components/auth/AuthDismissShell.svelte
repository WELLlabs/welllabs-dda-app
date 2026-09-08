<script>
	import { goto } from '$app/navigation';
	import ContourBackground from '$lib/shared/components/landing/ContourBackground.svelte';
	import { appPath } from '$lib/shared/paths.js';

	/** @type {{ children?: import('svelte').Snippet, labelledBy?: string }} */
	let { children, labelledBy = undefined } = $props();

	function dismiss() {
		goto(appPath('/'));
	}

	function onKeydown(e) {
		if (e.key === 'Escape') dismiss();
	}

	function onBackdropClick(e) {
		if (e.target === e.currentTarget) dismiss();
	}
</script>

<svelte:window onkeydown={onKeydown} />

<!-- Click outside the card returns to the landing page -->
<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
<div
	class="relative flex min-h-screen items-center justify-center overflow-hidden bg-void px-4 font-body"
	onclick={onBackdropClick}
	role="presentation"
>
	<ContourBackground intensity="ambient" />

	<div
		class="relative z-10 w-full max-w-sm rounded-[20px] border border-hairline bg-panel p-8 pt-10 shadow-glass"
		role="dialog"
		aria-modal="true"
		aria-labelledby={labelledBy}
		onclick={(e) => e.stopPropagation()}
	>
		<button
			type="button"
			class="absolute top-3 right-3 flex h-8 w-8 cursor-pointer items-center justify-center rounded-full text-ink-faint transition-colors hover:bg-panel-raised hover:text-ink"
			aria-label="Close"
			onclick={dismiss}
		>
			<svg
				xmlns="http://www.w3.org/2000/svg"
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				stroke-width="2"
				class="h-4 w-4"
			>
				<path d="M18 6 6 18M6 6l12 12" stroke-linecap="round" />
			</svg>
		</button>
		{@render children?.()}
	</div>
</div>
