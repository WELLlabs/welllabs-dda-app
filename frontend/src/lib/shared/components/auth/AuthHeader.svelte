<script lang="ts">
	export let variant: 'login' | 'register' = 'login';
</script>

<nav
	class="fixed inset-x-0 top-0 z-50 flex items-center justify-between border-b border-hairline px-6 py-4 md:px-10"
	style:background-color="rgba(9, 13, 16, 0.5)"
	style:backdrop-filter="saturate(180%) blur(14px)"
	style:-webkit-backdrop-filter="saturate(180%) blur(14px)"
>
	<a href="/" class="flex items-center gap-3">
		<svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
			<circle cx="12" cy="12" r="10.5" stroke="#4FD1C5" stroke-width="1" opacity="0.5" />
			<circle cx="12" cy="12" r="6.5" stroke="#4FD1C5" stroke-width="1" opacity="0.8" />
			<circle cx="12" cy="12" r="2.5" fill="#4FD1C5" />
		</svg>
		<span class="font-display text-[15px] font-semibold tracking-wide text-ink">Water security Tool</span>
	</a>

	<div class="flex items-center gap-3 font-mono text-[11px] text-ink-faint">
		{#if variant === 'login'}
			<span class="hidden sm:inline">New here?</span>
			<a
				href="/register"
				class="rounded-full border border-hairline bg-panel-raised px-4 py-1.5 font-body text-[13px] text-ink transition-colors duration-200 hover:border-diagnose/50 hover:text-diagnose"
			>
				Create account
			</a>
		{:else}
			<span class="hidden sm:inline">Already registered?</span>
			<a
				href="/login"
				class="rounded-full border border-hairline bg-panel-raised px-4 py-1.5 font-body text-[13px] text-ink transition-colors duration-200 hover:border-diagnose/50 hover:text-diagnose"
			>
				Sign in
			</a>
		{/if}
	</div>
</nav>