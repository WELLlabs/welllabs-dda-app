<script>
	import AppBrand from '$lib/shared/components/AppBrand.svelte';
	import UserMenu from '$lib/shared/components/UserMenu.svelte';
	import { appPath } from '$lib/shared/paths.js';

	// name kept for backward-compat; UserMenu reads the user from session.
	let { name = '' } = $props();
</script>

<header class="hdr">
	<div class="hdr-inner flex w-full items-center justify-between gap-3">
		<AppBrand homeHref="/home" compact />

		<div class="flex min-w-0 shrink-0 items-center gap-2 sm:gap-3">
			<div class="actions flex flex-wrap items-center justify-end gap-1.5">
				<a href={appPath('/about')} class="action-btn">About the Toolbox</a>
			</div>
			<UserMenu variant="light" />
		</div>
	</div>
</header>

<style>
	.hdr {
		position: sticky;
		top: 0;
		z-index: 40;
		padding: 0.75rem 0;
		border-bottom: 1px solid rgba(20, 40, 60, 0.08);
		background: rgba(255, 255, 255, 0.78);
		backdrop-filter: blur(14px);
	}

	.hdr-inner {
		padding-left: 0.75rem;
		padding-right: 1.5rem;
	}
	@media (min-width: 768px) {
		.hdr-inner {
			padding-left: 1.5rem;
			padding-right: 2.5rem;
		}
	}

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
			border-color 0.15s ease;
	}
	.actions :global(a.action-btn:hover) {
		background: rgba(15, 179, 163, 0.08);
		border-color: color-mix(in srgb, #1b75e0 35%, transparent);
	}
</style>
