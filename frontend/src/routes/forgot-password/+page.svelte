<script>
	import { forgotPassword } from '$lib/modules/accounts/api.js';
	import ContourBackground from '$lib/shared/components/landing/ContourBackground.svelte';

	let email = $state('');
	let submitting = $state(false);
	let message = $state('');
	let error = $state('');

	async function handleSubmit(e) {
		e.preventDefault();
		if (!email.trim()) return;
		submitting = true;
		error = '';
		message = '';
		try {
			await forgotPassword(email.trim());
			message = 'If that email is registered, a reset link is on its way.';
		} catch (err) {
			error = String(err.message ?? err);
		} finally {
			submitting = false;
		}
	}
</script>

<svelte:head>
	<title>Forgot password · DDA</title>
</svelte:head>

<div class="relative flex min-h-screen items-center justify-center overflow-hidden bg-void px-4 font-body">
	<ContourBackground intensity="ambient" />
	<div class="relative z-10 w-full max-w-sm rounded-[20px] border border-hairline bg-panel p-8 shadow-glass">
		<span class="font-mono text-[11px] uppercase tracking-[0.2em] text-diagnose">Account</span>
		<h1 class="mt-2 font-display text-2xl text-ink">Forgot password</h1>
		<p class="mt-1 font-body text-[13px] text-ink-dim">We'll email you a reset link.</p>

		<form onsubmit={handleSubmit} class="mt-7 flex flex-col gap-4">
			<div>
				<label class="mb-1.5 block font-mono text-[11px] uppercase tracking-wide text-ink-faint" for="email">
					Email
				</label>
				<input
					id="email"
					type="email"
					required
					class="w-full rounded-lg border border-hairline bg-panel-raised px-3 py-2.5 font-body text-[14px] text-ink focus:border-diagnose/60 focus:outline-none focus:ring-1 focus:ring-diagnose/40"
					bind:value={email}
					autocomplete="email"
				/>
			</div>
			{#if error}
				<p class="m-0 font-mono text-[12px] text-red-400">{error}</p>
			{/if}
			{#if message}
				<p class="m-0 font-mono text-[12px] text-ink-dim">{message}</p>
			{/if}
			<button
				type="submit"
				class="mt-2 cursor-pointer rounded-full bg-brand-blue px-4 py-2.5 font-body text-[14px] font-semibold text-white disabled:opacity-50"
				disabled={submitting || !email.trim()}
			>
				{submitting ? 'Sending…' : 'Send reset link'}
			</button>
		</form>
		<p class="mt-6 text-center font-body text-[13px] text-ink-dim">
			<a href="/login" class="font-medium text-diagnose hover:underline">Back to sign in</a>
		</p>
	</div>
</div>
