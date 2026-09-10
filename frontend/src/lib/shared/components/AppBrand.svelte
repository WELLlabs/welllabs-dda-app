<script>
	import { base } from '$app/paths';
	import { appPath } from '$lib/shared/paths.js';

	/**
	 * @type {{
	 *   homeHref?: string,
	 *   showProductName?: boolean,
	 *   compact?: boolean
	 * }}
	 */
	let { homeHref = '/home', showProductName = true, compact = false } = $props();

	const home = $derived(appPath(homeHref));
</script>

<a href={home} class="brand" class:compact aria-label="Water Security Toolbox home">
	<img src="{base}/logos/well-labs-logo.png" alt="WELL Labs" class="brand-logo" />
	<svg class="brand-star" viewBox="0 0 24 24" aria-hidden="true">
		<path
			d="M12 1.6 13.7 9.1 21 12 13.7 14.9 12 22.4 10.3 14.9 3 12l7.3-2.9L12 1.6Z"
			fill="currentColor"
		/>
	</svg>
	{#if showProductName}
		<span class="brand-product">Water Security Toolbox</span>
	{/if}
</a>

<style>
	.brand {
		display: inline-flex;
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

	.brand.compact .brand-logo {
		height: 1.9rem;
		max-width: 9.5rem;
	}

	.brand-star {
		height: 0.85rem;
		width: 0.85rem;
		flex-shrink: 0;
		color: #1b75e0;
	}

	.brand-product {
		font-family: var(--font-body);
		font-size: 0.95rem;
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
			height: 2.45rem;
			max-width: 13rem;
		}
		.brand.compact .brand-logo {
			height: 2.15rem;
			max-width: 11rem;
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
