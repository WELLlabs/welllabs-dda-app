<script>
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';
	import { appPath } from '$lib/shared/paths.js';
	import { ABOUT_DOCS_NAV } from '$lib/docs/about/nav.js';

	let { children } = $props();

	const activeSlug = $derived(page.params.slug || 'overview');
</script>

<div class="docs-shell flex min-h-screen flex-col bg-gray-50 font-body">
	<ModuleHeader title="About the Toolbox" />

	<div
		class="docs-frame mx-auto flex w-full max-w-6xl flex-1 overflow-hidden border-brand-navy/10 bg-white md:my-6 md:rounded-xl md:border md:shadow-sm"
	>
		<aside class="docs-toc hidden w-52 shrink-0 border-r border-brand-navy/10 lg:w-56 md:block">
			<nav class="sticky top-0 max-h-[calc(100vh-5rem)] overflow-y-auto px-3 py-5" aria-label="Documentation">
				<p
					class="m-0 mb-2 px-2 font-headline text-[10px] font-semibold tracking-[0.1em] text-brand-navy/45 uppercase"
				>
					Documentation
				</p>
				<ul class="m-0 flex list-none flex-col gap-0.5 p-0">
					{#each ABOUT_DOCS_NAV as item (item.slug)}
						<li>
							<a
								href={appPath(`/about/${item.slug}`)}
								class="toc-link block rounded-md px-2 py-1.5 text-[13px] leading-snug transition-colors"
								class:toc-link-active={activeSlug === item.slug}
							>
								{item.shortTitle || item.title}
							</a>
						</li>
					{/each}
				</ul>
			</nav>
		</aside>

		<div class="min-w-0 flex-1 bg-white">
			<nav
				class="border-b border-brand-navy/10 px-4 py-3 md:hidden"
				aria-label="Documentation (mobile)"
			>
				<label class="sr-only" for="about-doc-select">Section</label>
				<select
					id="about-doc-select"
					class="w-full rounded-lg border border-brand-navy/15 bg-white px-3 py-2 font-body text-sm text-brand-navy"
					value={activeSlug}
					onchange={(e) => {
						void goto(appPath(`/about/${e.currentTarget.value}`));
					}}
				>
					{#each ABOUT_DOCS_NAV as item (item.slug)}
						<option value={item.slug}>{item.shortTitle || item.title}</option>
					{/each}
				</select>
			</nav>

			{@render children?.()}
		</div>
	</div>
</div>

<style>
	.toc-link {
		color: var(--color-brand-steel, #5a6b7d);
		text-decoration: none;
	}
	.toc-link:hover {
		background: color-mix(in srgb, var(--color-brand-sky, #e8f1fb) 70%, white);
		color: var(--color-brand-navy, #00296b);
	}
	.toc-link-active {
		background: color-mix(in srgb, var(--color-brand-sky, #e8f1fb) 90%, white);
		color: var(--color-brand-navy, #00296b);
		font-weight: 600;
	}
	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		padding: 0;
		margin: -1px;
		overflow: hidden;
		clip: rect(0, 0, 0, 0);
		white-space: nowrap;
		border: 0;
	}
</style>
