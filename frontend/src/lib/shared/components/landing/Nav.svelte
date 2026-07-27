<script lang="ts">
	let scrolled = false;

	function onScroll() {
		scrolled = window.scrollY > 12;
	}
</script>

<svelte:window on:scroll={onScroll} />

<nav
	class="fixed inset-x-0 top-0 z-50 flex items-center justify-between px-6 py-4 transition-all duration-500 md:px-10"
	class:shadow-glass={scrolled}
	style:background-color={scrolled
		? 'rgba(249, 250, 252, 0.55)'
		: 'transparent'}
	style:backdrop-filter={scrolled
		? 'saturate(180%) blur(12px)'
		: 'none'}
>
	<div class="flex items-center gap-3">
		<svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
			<circle cx="12" cy="12" r="10.5" stroke="#4FD1C5" stroke-width="1" opacity="0.5" />
			<circle cx="12" cy="12" r="6.5" stroke="#4FD1C5" stroke-width="1" opacity="0.8" />
			<circle cx="12" cy="12" r="2.5" fill="#4FD1C5" />
		</svg>
		<span class="font-display text-[15px] font-semibold tracking-wide text-ink">Water security Tool</span>
	</div>

	<!--
	<div class="hidden items-center gap-8 font-body text-[13px] text-ink-dim md:flex">
		<a href="#workspaces" class="transition-colors hover:text-ink">Workspaces</a>
		<a href="#continue" class="transition-colors hover:text-ink">Dashboard</a>
		<a href="#projects" class="transition-colors hover:text-ink">Projects</a>
	</div>
	-->

	<div class="flex items-center gap-3">
		<a
			href="/register"
			class="rounded-full border border-transparent bg-brand-blue px-4 py-1.5 font-body text-[13px] font-semibold text-white shadow-glass transition-all duration-200 hover:bg-brand-deep"
		>
			Get started
		</a>
		<a
			href="/login"
			class="rounded-full border border-hairline bg-panel-raised px-4 py-1.5 font-body text-[13px] text-ink transition-colors duration-200 hover:border-diagnose/50 hover:text-diagnose"
		>
			Sign in
		</a>
	</div>
</nav>
