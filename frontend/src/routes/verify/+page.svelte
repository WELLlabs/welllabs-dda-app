<script>
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { verifyEmail } from '$lib/modules/accounts/api.js';
	import ContourBackground from '$lib/shared/components/landing/ContourBackground.svelte';

	let status = $state('Verifying…');
	let ok = $state(false);

	onMount(async () => {
		const token = page.url.searchParams.get('token');
		if (!token) {
			status = 'Missing verification token.';
			return;
		}
		try {
			await verifyEmail(token);
			ok = true;
			status = 'Email verified. You can sign in now.';
		} catch (err) {
			status = String(err.message ?? err);
		}
	});
</script>

<svelte:head>
	<title>Verify email · DDA</title>
</svelte:head>

<div class="relative flex min-h-screen items-center justify-center overflow-hidden bg-void px-4 font-body">
	<ContourBackground intensity="ambient" />
	<div class="relative z-10 w-full max-w-sm rounded-[20px] border border-hairline bg-panel p-8 shadow-glass">
		<span class="font-mono text-[11px] uppercase tracking-[0.2em] text-diagnose">Email</span>
		<h1 class="mt-2 font-display text-2xl text-ink">Verification</h1>
		<p class="mt-3 font-body text-[14px] text-ink-dim">{status}</p>
		{#if ok}
			<button
				type="button"
				class="mt-6 w-full cursor-pointer rounded-full bg-brand-blue px-4 py-2.5 font-body text-[14px] font-semibold text-white"
				onclick={() => goto('/login')}
			>
				Sign in
			</button>
		{/if}
	</div>
</div>
