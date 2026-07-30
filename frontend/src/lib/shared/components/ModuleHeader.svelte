<script>
	import UserMenu from '$lib/shared/components/UserMenu.svelte';

	/**
	 * @typedef {import('svelte').Snippet} Snippet
	 * @type {{
	 *   title?: string,
	 *   project?: string,
	 *   subtitle?: string,
	 *   homeHref?: string,
	 *   titleHref?: string,
	 *   wide?: boolean,
	 *   children?: Snippet
	 * }}
	 */
	let {
		title = '',
		project = '',
		subtitle = '',
		homeHref = '/home',
		titleHref = '',
		wide = false,
		children
	} = $props();
</script>

<header class="hdr" class:hdr-wide={wide}>
	<div
		class="hdr-inner mx-auto flex items-center justify-between gap-3"
		class:max-w-6xl={!wide}
		class:max-w-none={wide}
	>
		<!-- brand + breadcrumb (separate links) -->
		<div class="brand group">
			<a href={homeHref} class="brand-mark" aria-label="Home">
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" class="h-5 w-5">
					<path d="M12 3c3.5 4 6 7 6 10a6 6 0 1 1-12 0c0-3 2.5-6 6-10z" stroke-linejoin="round" />
				</svg>
			</a>
			<span class="crumb">
				<a href={homeHref} class="brand-name font-display">Water security Tool</a>
				{#if title}
					<span class="sep">/</span>
					{#if titleHref}
						<a href={titleHref} class="crumb-module font-display">{title}</a>
					{:else}
						<span class="crumb-module font-display">{title}</span>
					{/if}
				{/if}
				{#if project}
					<span class="sep">/</span>
					<span class="crumb-project font-body" title={subtitle || project}>{project}</span>
				{/if}
			</span>
		</div>

		<div class="flex min-w-0 flex-1 items-center justify-end gap-2 sm:gap-3">
			{#if children}
				<div class="actions flex flex-wrap items-center justify-end gap-1.5">
					{@render children()}
				</div>
			{/if}
			<UserMenu variant="light" />
		</div>
	</div>
</header>

<style>
	.hdr {
		position: sticky;
		top: 0;
		z-index: 40;
		padding: 0.85rem 0;
		border-bottom: 1px solid rgba(20, 40, 60, 0.08);
		background: rgba(255, 255, 255, 0.72);
		backdrop-filter: blur(14px);
	}

	.hdr-inner {
		padding-left: 1.5rem;
		padding-right: 1.5rem;
	}
	@media (min-width: 768px) {
		.hdr-inner {
			padding-left: 2.5rem;
			padding-right: 2.5rem;
		}
	}
	/* Match MapView left sidebar content inset (p-3 = 0.75rem) */
	.hdr-wide .hdr-inner {
		padding-left: 0.75rem;
		padding-right: 1.5rem;
	}
	@media (min-width: 768px) {
		.hdr-wide .hdr-inner {
			padding-right: 2.5rem;
		}
	}

	.brand { display: inline-flex; align-items: center; gap: 0.7rem; min-width: 0; }
	.brand-mark {
		display: grid;
		place-items: center;
		height: 2.25rem;
		width: 2.25rem;
		flex: none;
		border-radius: 12px;
		color: #0fb3a3;
		border: 1px solid color-mix(in srgb, #0fb3a3 28%, transparent);
		background: color-mix(in srgb, #0fb3a3 12%, white);
		transition: transform 0.3s ease, box-shadow 0.3s ease;
		text-decoration: none;
	}
	.brand:hover .brand-mark {
		transform: rotate(-6deg) scale(1.05);
		box-shadow: 0 10px 22px -12px rgba(15, 179, 163, 0.6);
	}

	.crumb {
		display: inline-flex;
		align-items: baseline;
		gap: 0.5rem;
		min-width: 0;
		overflow: hidden;
		white-space: nowrap;
	}
	.brand-name {
		font-size: 1.15rem;
		letter-spacing: 0.04em;
		background: linear-gradient(100deg, #0fb3a3, #7c5ce6);
		-webkit-background-clip: text;
		background-clip: text;
		color: transparent;
		text-decoration: none;
	}
	.brand-name:hover {
		opacity: 0.85;
	}
	.sep { color: #b3bcc5; font-size: 1rem; }
	.crumb-module {
		font-size: 1.05rem;
		font-weight: 500;
		color: #6b7885;
		text-decoration: none;
	}
	.crumb-module:hover {
		color: #1a2530;
	}
	.crumb-project {
		font-size: 1.05rem;
		font-weight: 700;
		color: #1a2530;
		overflow: hidden;
		text-overflow: ellipsis;
		max-width: 16rem;
	}

	.actions :global(button),
	.actions :global(a.action-btn) {
		cursor: pointer;
		border-radius: 0.5rem;
		border: 1px solid rgba(20, 40, 60, 0.12);
		background: white;
		padding: 0.4rem 0.75rem;
		font-family: inherit;
		font-size: 0.8125rem;
		font-weight: 500;
		color: #1a2530;
		text-decoration: none;
		transition: background 0.15s ease, border-color 0.15s ease, opacity 0.15s ease;
	}
	.actions :global(button:hover:not(:disabled)),
	.actions :global(a.action-btn:hover) {
		background: rgba(15, 179, 163, 0.08);
		border-color: color-mix(in srgb, #0fb3a3 35%, transparent);
	}
	.actions :global(button:disabled) {
		cursor: not-allowed;
		opacity: 0.55;
	}
	.actions :global(button.primary) {
		border-color: color-mix(in srgb, #0fb3a3 40%, transparent);
		background: color-mix(in srgb, #0fb3a3 14%, white);
		color: #0a7a70;
	}
	.actions :global(button.primary:hover:not(:disabled)) {
		background: color-mix(in srgb, #0fb3a3 22%, white);
	}
</style>
