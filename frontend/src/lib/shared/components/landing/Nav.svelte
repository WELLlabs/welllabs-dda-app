<script lang="ts">
	import { base } from '$app/paths';
	import { appPath } from '$lib/shared/paths.js';

	let scrolled = false;

	function onScroll() {
		scrolled = window.scrollY > 12;
	}
</script>

<svelte:window on:scroll={onScroll} />

<nav
	class="fixed inset-x-0 top-0 z-50 flex items-center justify-between gap-4 px-5 py-3 transition-all duration-500 md:px-10"
	class:shadow-glass={scrolled}
	style:background-color={scrolled ? 'rgba(249, 250, 252, 0.78)' : 'transparent'}
	style:backdrop-filter={scrolled ? 'saturate(180%) blur(12px)' : 'none'}
>
	<a href={appPath('/')} class="brand group min-w-0" aria-label="Water Security Toolbox">
		<img
			src="{base}/logos/well-labs-logo.png"
			alt="WELL Labs"
			class="brand-logo"
		/>
		<svg class="brand-star" viewBox="0 0 24 24" aria-hidden="true">
			<path
				d="M12 1.6 13.7 9.1 21 12 13.7 14.9 12 22.4 10.3 14.9 3 12l7.3-2.9L12 1.6Z"
				fill="currentColor"
			/>
		</svg>
		<span class="brand-product">Water Security Toolbox</span>
	</a>

	<div class="flex shrink-0 items-center gap-2 sm:gap-3">
		<a
			href={appPath('/register')}
			class="rounded-full border border-transparent bg-brand-blue px-3.5 py-1.5 font-body text-[12px] font-semibold text-white shadow-glass transition-all duration-200 hover:bg-brand-deep sm:px-4 sm:text-[13px]"
		>
			Get started
		</a>
		<a
			href={appPath('/login')}
			class="rounded-full border border-hairline bg-panel-raised px-3.5 py-1.5 font-body text-[12px] text-ink transition-colors duration-200 hover:border-diagnose/50 hover:text-diagnose sm:px-4 sm:text-[13px]"
		>
			Sign in
		</a>
	</div>
</nav>

<style>
	.brand {
		display: flex;
		align-items: center;
		gap: 0.55rem;
		min-width: 0;
		text-decoration: none;
		color: inherit;
	}

	.brand-logo {
		height: 2.1rem;
		width: auto;
		max-width: min(42vw, 11.5rem);
		flex-shrink: 1;
		object-fit: contain;
		object-position: left center;
	}

	.brand-star {
		height: 0.85rem;
		width: 0.85rem;
		flex-shrink: 0;
		color: #1b75e0;
	}

	.brand-product {
		font-family: var(--font-body);
		font-size: 0.92rem;
		font-weight: 600;
		letter-spacing: 0.01em;
		color: #1b75e0;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	@media (min-width: 640px) {
		.brand {
			gap: 0.7rem;
		}
		.brand-logo {
			height: 2.55rem;
			max-width: 13.5rem;
		}
		.brand-product {
			font-size: 1.05rem;
		}
		.brand-star {
			height: 0.95rem;
			width: 0.95rem;
		}
	}
</style>
