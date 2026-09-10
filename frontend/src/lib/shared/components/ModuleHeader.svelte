<script>
	import AppBrand from '$lib/shared/components/AppBrand.svelte';
	import UserMenu from '$lib/shared/components/UserMenu.svelte';
	import { appPath } from '$lib/shared/paths.js';

	/**
	 * @typedef {{ label: string, href?: string }} Crumb
	 * @typedef {import('svelte').Snippet} Snippet
	 * @type {{
	 *   title?: string,
	 *   project?: string,
	 *   subtitle?: string,
	 *   homeHref?: string,
	 *   titleHref?: string,
	 *   wide?: boolean,
	 *   fullProjectTitle?: boolean,
	 *   crumbs?: Crumb[],
	 *   children?: Snippet
	 * }}
	 */
	let {
		title = '',
		project = '',
		subtitle = '',
		homeHref = '/home',
		titleHref = '',
		wide = true,
		fullProjectTitle = false,
		crumbs = [],
		children
	} = $props();

	const trail = $derived(
		(crumbs?.length
			? crumbs
			: [
					...(title ? [{ label: title, href: titleHref || undefined }] : []),
					...(project ? [{ label: project }] : [])
				]
		).map((item) => (item.href ? { ...item, href: appPath(item.href) } : item))
	);

	const showSecondRow = $derived(trail.length > 0 || Boolean(children));
	const diagnoseCrumbBar = $derived(title === 'Diagnose' || titleHref === '/diagnose');
</script>

<header class="hdr" class:hdr-wide={wide} class:hdr-with-bar={showSecondRow}>
	<div
		class="hdr-inner mx-auto flex flex-col gap-2"
		class:max-w-6xl={!wide}
		class:max-w-none={wide}
	>
		<!-- Top: brand + About + account -->
		<div class="flex items-center justify-between gap-3">
			<AppBrand homeHref={homeHref} compact />

			<div class="flex min-w-0 shrink-0 items-center gap-2 sm:gap-3">
				<a href={appPath('/about')} class="action-btn">About the Toolbox</a>
				<UserMenu variant="light" />
			</div>
		</div>
	</div>

	<!-- Below: breadcrumb + page actions inline -->
	{#if showSecondRow}
		<div class="second-row" class:second-row-diagnose={diagnoseCrumbBar}>
			<div
				class="second-row-inner mx-auto"
				class:max-w-6xl={!wide}
				class:max-w-none={wide}
			>
				{#if trail.length}
					<nav
						class="crumb"
						class:crumb-wrap={fullProjectTitle || crumbs?.length}
						aria-label="Breadcrumb"
					>
						{#each trail as item, i (item.label + (item.href || '') + i)}
							{#if i > 0}<span class="sep">/</span>{/if}
							{#if item.href}
								<a
									href={item.href}
									class="crumb-link font-display"
									class:crumb-current={i === trail.length - 1}
									title={item.label}>{item.label}</a
								>
							{:else}
								<span
									class="crumb-current font-body"
									class:crumb-project-full={fullProjectTitle || crumbs?.length}
									title={subtitle || item.label}>{item.label}</span
								>
							{/if}
						{/each}
					</nav>
				{:else}
					<span></span>
				{/if}

				{#if children}
					<div class="actions flex flex-wrap items-center justify-end gap-1.5">
						{@render children()}
					</div>
				{/if}
			</div>
		</div>
	{/if}
</header>

<style>
	.hdr {
		position: sticky;
		top: 0;
		z-index: 40;
		padding: 0.75rem 0 0.65rem;
		border-bottom: 1px solid rgba(20, 40, 60, 0.08);
		background: rgba(255, 255, 255, 0.78);
		backdrop-filter: blur(14px);
	}
	.hdr-with-bar {
		padding-bottom: 0;
	}

	.hdr-inner {
		width: 100%;
		padding-left: 0.75rem;
		padding-right: 1.5rem;
	}
	@media (min-width: 768px) {
		.hdr-inner {
			padding-left: 1.5rem;
			padding-right: 2.5rem;
		}
	}

	.second-row {
		margin-top: 0.65rem;
		border-top: 1px solid rgba(20, 40, 60, 0.06);
	}

	.second-row-inner {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem 1rem;
		flex-wrap: wrap;
		min-width: 0;
		width: 100%;
		padding: 0.55rem 0.75rem 0.6rem;
	}
	@media (min-width: 768px) {
		.second-row-inner {
			padding-left: 1.5rem;
			padding-right: 2.5rem;
		}
	}

	.second-row-diagnose {
		margin-top: 0.55rem;
		background:
			linear-gradient(
				180deg,
				rgba(125, 195, 255, 0.1) 0%,
				rgba(242, 247, 252, 0.98) 42%,
				rgba(242, 247, 252, 0.98) 58%,
				rgba(125, 195, 255, 0.09) 100%
			);
		border-top-color: rgba(125, 195, 255, 0.12);
	}
	.second-row-diagnose .sep {
		color: color-mix(in srgb, #1b75e0 35%, #b3bcc5);
	}
	.second-row-diagnose .crumb-link {
		color: #3969a7;
	}
	.second-row-diagnose .crumb-link:hover {
		color: #1a2530;
	}
	.second-row-diagnose .crumb-link.crumb-current,
	.second-row-diagnose .crumb-current {
		color: #1a2530;
	}

	.crumb {
		display: inline-flex;
		align-items: baseline;
		gap: 0.45rem;
		min-width: 0;
		flex: 1 1 auto;
		overflow: hidden;
		white-space: nowrap;
	}
	.sep {
		color: #b3bcc5;
		font-size: 0.95rem;
		flex: none;
	}
	.crumb-link {
		font-size: 0.95rem;
		font-weight: 500;
		color: #6b7885;
		text-decoration: none;
	}
	.crumb-link:hover {
		color: #1a2530;
	}
	.crumb-link.crumb-current,
	.crumb-current {
		font-size: 0.95rem;
		font-weight: 700;
		color: #1a2530;
		overflow: hidden;
		text-overflow: ellipsis;
		max-width: 16rem;
	}
	.crumb-wrap {
		flex-wrap: wrap;
		white-space: normal;
		overflow: visible;
		row-gap: 0.15rem;
	}
	.crumb-project-full,
	.crumb-wrap .crumb-current,
	.crumb-wrap .crumb-link.crumb-current {
		max-width: none;
		overflow: visible;
		text-overflow: unset;
		white-space: normal;
		line-height: 1.25;
	}

	.action-btn,
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
		white-space: nowrap;
		transition:
			background 0.15s ease,
			border-color 0.15s ease,
			opacity 0.15s ease;
	}
	.action-btn:hover,
	.actions :global(button:hover:not(:disabled)),
	.actions :global(a.action-btn:hover) {
		background: rgba(15, 179, 163, 0.08);
		border-color: color-mix(in srgb, #1b75e0 35%, transparent);
	}
	.actions :global(button:disabled) {
		cursor: not-allowed;
		opacity: 0.55;
	}
	.actions :global(button.primary) {
		border-color: color-mix(in srgb, #1b75e0 40%, transparent);
		background: color-mix(in srgb, #1b75e0 14%, white);
		color: #0a7a70;
	}
	.actions :global(button.primary:hover:not(:disabled)) {
		background: color-mix(in srgb, #1b75e0 22%, white);
	}
	.actions :global(button.icon-btn) {
		display: inline-grid;
		place-items: center;
		padding: 0.4rem;
		min-width: 2rem;
		min-height: 2rem;
	}
</style>
