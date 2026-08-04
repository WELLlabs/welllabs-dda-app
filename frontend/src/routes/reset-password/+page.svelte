<script>
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { resetPassword } from '$lib/modules/accounts/api.js';
	import ContourBackground from '$lib/shared/components/landing/ContourBackground.svelte';

	let password = $state('');
	let submitting = $state(false);
	let error = $state('');
	let done = $state(false);
	const token = $derived(page.url.searchParams.get('token') || '');

	async function handleSubmit(e) {
		e.preventDefault();
		if (!token || password.length < 8) return;
		submitting = true;
		error = '';
		try {
			await resetPassword(token, password);
			done = true;
		} catch (err) {
			error = String(err.message ?? err);
		} finally {
			submitting = false;
		}
	}
</script>

<svelte:head>
	<title>Reset password · DDA</title>
</svelte:head>

<div class="relative flex min-h-screen items-center justify-center overflow-hidden bg-void px-4 font-body">
	<ContourBackground intensity="ambient" />
	<div class="relative z-10 w-full max-w-sm rounded-[20px] border border-hairline bg-panel p-8 shadow-glass">
		{#if done}
			<span class="font-mono text-[11px] uppercase tracking-[0.2em] text-diagnose">Done</span>
			<h1 class="mt-2 font-display text-2xl text-ink">Password updated</h1>
			<button
				type="button"
				class="mt-6 w-full cursor-pointer rounded-full bg-brand-blue px-4 py-2.5 font-body text-[14px] font-semibold text-white"
				onclick={() => goto('/login')}
			>
				Sign in
			</button>
		{:else}
			<span class="font-mono text-[11px] uppercase tracking-[0.2em] text-diagnose">Account</span>
			<h1 class="mt-2 font-display text-2xl text-ink">Reset password</h1>
			{#if !token}
				<p class="mt-3 font-mono text-[12px] text-red-400">Missing reset token. Use the link from your email.</p>
			{:else}
				<form onsubmit={handleSubmit} class="mt-7 flex flex-col gap-4">
					<div>
						<label class="mb-1.5 block font-mono text-[11px] uppercase tracking-wide text-ink-faint" for="password">
							New password
						</label>
						<input
							id="password"
							type="password"
							required
							minlength="8"
							class="w-full rounded-lg border border-hairline bg-panel-raised px-3 py-2.5 font-body text-[14px] text-ink focus:border-diagnose/60 focus:outline-none focus:ring-1 focus:ring-diagnose/40"
							bind:value={password}
							autocomplete="new-password"
						/>
					</div>
					{#if error}
						<p class="m-0 font-mono text-[12px] text-red-400">{error}</p>
					{/if}
					<button
						type="submit"
						class="mt-2 cursor-pointer rounded-full bg-brand-blue px-4 py-2.5 font-body text-[14px] font-semibold text-white disabled:opacity-50"
						disabled={submitting || password.length < 8}
					>
						{submitting ? 'Saving…' : 'Save password'}
					</button>
				</form>
			{/if}
		{/if}
	</div>
</div>
