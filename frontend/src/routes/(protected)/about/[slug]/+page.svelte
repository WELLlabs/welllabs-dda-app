<script>
	import { appPath } from '$lib/shared/paths.js';
	import { ABOUT_DOCS_NAV } from '$lib/docs/about/nav.js';

	/** @type {{ data: { slug: string, title: string, html: string, headings: { id: string, text: string, depth: number }[] } }} */
	let { data } = $props();

	const navIndex = $derived(ABOUT_DOCS_NAV.findIndex((d) => d.slug === data.slug));
	const prev = $derived(navIndex > 0 ? ABOUT_DOCS_NAV[navIndex - 1] : null);
	const next = $derived(
		navIndex >= 0 && navIndex < ABOUT_DOCS_NAV.length - 1 ? ABOUT_DOCS_NAV[navIndex + 1] : null
	);
</script>

<svelte:head>
	<title>{data.title} · About · Water Security Toolbox</title>
</svelte:head>

<div class="docs-page flex min-h-full gap-0">
	<article class="docs-prose min-w-0 flex-1 px-5 py-6 sm:px-8 sm:py-8 lg:px-10">
		{@html data.html}

		<nav
			class="mt-10 flex flex-wrap items-stretch justify-between gap-3 border-t border-brand-navy/10 pt-6"
			aria-label="Adjacent pages"
		>
			{#if prev}
				<a class="pager-link" href={appPath(`/about/${prev.slug}`)}>
					<span class="pager-label">Previous</span>
					<span class="pager-title">{prev.shortTitle || prev.title}</span>
				</a>
			{:else}
				<span></span>
			{/if}
			{#if next}
				<a class="pager-link pager-link-next" href={appPath(`/about/${next.slug}`)}>
					<span class="pager-label">Next</span>
					<span class="pager-title">{next.shortTitle || next.title}</span>
				</a>
			{/if}
		</nav>
	</article>

	{#if data.headings.length}
		<aside class="on-this-page hidden w-44 shrink-0 border-l border-brand-navy/10 px-4 py-8 xl:block xl:w-48">
			<nav class="sticky top-6" aria-label="On this page">
				<p
					class="m-0 mb-2 font-headline text-[10px] font-semibold tracking-[0.1em] text-brand-navy/45 uppercase"
				>
					On this page
				</p>
				<ul class="m-0 flex list-none flex-col gap-1.5 p-0">
					{#each data.headings as h (h.id)}
						<li style:padding-left="{Math.max(0, h.depth - 2) * 0.65}rem">
							<a class="otp-link" href={`#${h.id}`}>{h.text}</a>
						</li>
					{/each}
				</ul>
			</nav>
		</aside>
	{/if}
</div>

<style>
	.docs-prose :global(h1) {
		margin: 0 0 1rem;
		padding-bottom: 0.75rem;
		border-bottom: 1px solid color-mix(in srgb, var(--color-brand-navy, #00296b) 10%, transparent);
		font-family: var(--font-headline);
		font-size: 1.5rem;
		font-weight: 600;
		color: var(--color-brand-navy, #00296b);
		line-height: 1.3;
	}
	.docs-prose :global(h2) {
		margin: 1.75rem 0 0.6rem;
		font-family: var(--font-headline);
		font-size: 1.05rem;
		font-weight: 600;
		color: var(--color-brand-navy, #00296b);
		scroll-margin-top: 1.25rem;
	}
	.docs-prose :global(h3) {
		margin: 1.25rem 0 0.45rem;
		font-family: var(--font-headline);
		font-size: 0.95rem;
		font-weight: 600;
		color: var(--color-brand-navy, #00296b);
		scroll-margin-top: 1.25rem;
	}
	.docs-prose :global(p),
	.docs-prose :global(li) {
		font-size: 15px;
		line-height: 1.7;
		color: var(--color-brand-steel, #5a6b7d);
	}
	.docs-prose :global(p) {
		margin: 0.85rem 0 0;
	}
	.docs-prose :global(p:first-of-type) {
		margin-top: 0;
	}
	.docs-prose :global(ul),
	.docs-prose :global(ol) {
		margin: 0.65rem 0 0;
		padding-left: 1.4rem;
		color: var(--color-brand-steel, #5a6b7d);
	}
	/* Tailwind preflight clears markers — restore for docs */
	.docs-prose :global(ul) {
		list-style-type: disc;
	}
	.docs-prose :global(ol) {
		list-style-type: decimal;
	}
	.docs-prose :global(li) {
		display: list-item;
		padding-left: 0.15rem;
	}
	.docs-prose :global(li + li) {
		margin-top: 0.4rem;
	}
	.docs-prose :global(li::marker) {
		color: var(--color-brand-navy, #00296b);
	}
	.docs-prose :global(a) {
		color: var(--color-brand-blue, #1b75e0);
		font-weight: 500;
		text-decoration: underline;
		text-decoration-color: color-mix(in srgb, var(--color-brand-blue, #1b75e0) 30%, transparent);
		text-underline-offset: 2px;
	}
	.docs-prose :global(a:hover) {
		text-decoration-color: var(--color-brand-blue, #1b75e0);
	}
	.docs-prose :global(strong) {
		color: var(--color-brand-navy, #00296b);
		font-weight: 600;
	}
	.pager-link {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		min-width: min(100%, 11rem);
		padding: 0.65rem 0.8rem;
		border-radius: 0.5rem;
		border: 1px solid color-mix(in srgb, var(--color-brand-navy, #00296b) 12%, transparent);
		text-decoration: none;
		background: #fff;
		transition: border-color 0.15s ease, background 0.15s ease;
	}
	.pager-link:hover {
		border-color: color-mix(in srgb, var(--color-brand-blue, #1b75e0) 45%, transparent);
		background: color-mix(in srgb, var(--color-brand-sky, #e8f1fb) 40%, white);
	}
	.pager-link-next {
		text-align: right;
		margin-left: auto;
	}
	.pager-label {
		font-size: 11px;
		font-weight: 600;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--color-brand-steel, #5a6b7d);
	}
	.pager-title {
		font-size: 13px;
		font-weight: 600;
		color: var(--color-brand-navy, #00296b);
	}
	.otp-link {
		display: block;
		font-size: 12px;
		line-height: 1.35;
		color: var(--color-brand-steel, #5a6b7d);
		text-decoration: none;
	}
	.otp-link:hover {
		color: var(--color-brand-navy, #00296b);
	}
</style>
