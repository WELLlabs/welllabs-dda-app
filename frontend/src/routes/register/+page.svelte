<script>
	import { register, startGoogleAuth } from '$lib/modules/accounts/api.js';
	import ContourBackground from '$lib/shared/components/landing/ContourBackground.svelte';

	let name = $state('');
	let email = $state('');
	let password = $state('');
	let submitting = $state(false);
	let error = $state('');
	let checkEmail = $state(false);
	let googleBusy = $state(false);

	async function handleSubmit(e) {
		e.preventDefault();
		if (!name.trim() || !email.trim() || password.length < 8) return;
		submitting = true;
		error = '';
		try {
			await register(email.trim(), name.trim(), password);
			checkEmail = true;
		} catch (err) {
			error = String(err.message ?? err);
		} finally {
			submitting = false;
		}
	}

	async function handleGoogle() {
		googleBusy = true;
		error = '';
		try {
			await startGoogleAuth();
		} catch (err) {
			error = String(err.message ?? err);
			googleBusy = false;
		}
	}
</script>

<svelte:head>
	<title>Create account · DDA</title>
</svelte:head>

<div class="relative flex min-h-screen items-center justify-center overflow-hidden bg-void px-4 font-body">
	<ContourBackground intensity="ambient" />

	<div class="relative z-10 w-full max-w-sm rounded-[20px] border border-hairline bg-panel p-8 shadow-glass">
		{#if checkEmail}
			<span class="font-mono text-[11px] uppercase tracking-[0.2em] text-diagnose">Check your email</span>
			<h1 class="mt-2 font-display text-2xl text-ink">Verify to continue</h1>
			<p class="mt-3 font-body text-[14px] text-ink-dim">
				We sent a verification link to <span class="text-ink">{email}</span>. Open it, then sign in.
			</p>
			<p class="mt-6 text-center font-body text-[13px] text-ink-dim">
				<a href="/login" class="font-medium text-diagnose hover:underline">Back to sign in</a>
			</p>
		{:else}
			<span class="font-mono text-[11px] uppercase tracking-[0.2em] text-diagnose">Get started</span>
			<h1 class="mt-2 font-display text-2xl text-ink">Create an account</h1>
			<p class="mt-1 font-body text-[13px] text-ink-dim">Set up your watershed workspace.</p>

			<form onsubmit={handleSubmit} class="mt-7 flex flex-col gap-4">
				<div>
					<label class="mb-1.5 block font-mono text-[11px] uppercase tracking-wide text-ink-faint" for="name">
						Name
					</label>
					<input
						id="name"
						type="text"
						required
						class="w-full rounded-lg border border-hairline bg-panel-raised px-3 py-2.5 font-body text-[14px] text-ink placeholder:text-ink-faint focus:border-diagnose/60 focus:outline-none focus:ring-1 focus:ring-diagnose/40"
						bind:value={name}
						autocomplete="name"
					/>
				</div>
				<div>
					<label class="mb-1.5 block font-mono text-[11px] uppercase tracking-wide text-ink-faint" for="email">
						Email
					</label>
					<input
						id="email"
						type="email"
						required
						class="w-full rounded-lg border border-hairline bg-panel-raised px-3 py-2.5 font-body text-[14px] text-ink placeholder:text-ink-faint focus:border-diagnose/60 focus:outline-none focus:ring-1 focus:ring-diagnose/40"
						bind:value={email}
						autocomplete="email"
					/>
				</div>
				<div>
					<label class="mb-1.5 block font-mono text-[11px] uppercase tracking-wide text-ink-faint" for="password">
						Password
					</label>
					<input
						id="password"
						type="password"
						required
						minlength="8"
						class="w-full rounded-lg border border-hairline bg-panel-raised px-3 py-2.5 font-body text-[14px] text-ink placeholder:text-ink-faint focus:border-diagnose/60 focus:outline-none focus:ring-1 focus:ring-diagnose/40"
						bind:value={password}
						autocomplete="new-password"
					/>
					<p class="m-0 mt-1.5 font-mono text-[10px] text-ink-faint">At least 8 characters.</p>
				</div>

				{#if error}
					<p class="m-0 font-mono text-[12px] text-red-400">{error}</p>
				{/if}

				<button
					type="submit"
					class="mt-2 cursor-pointer rounded-full bg-brand-blue px-4 py-2.5 font-body text-[14px] font-semibold text-white shadow-glass transition-all duration-200 hover:bg-brand-deep disabled:cursor-not-allowed disabled:opacity-50"
					disabled={submitting || !name.trim() || !email.trim() || password.length < 8}
				>
					{submitting ? 'Creating account…' : 'Create account'}
				</button>
			</form>

			<div class="mt-5 flex items-center gap-3">
				<div class="h-px flex-1 bg-hairline"></div>
				<span class="font-mono text-[10px] uppercase tracking-wide text-ink-faint">or</span>
				<div class="h-px flex-1 bg-hairline"></div>
			</div>

			<button
				type="button"
				onclick={handleGoogle}
				disabled={googleBusy}
				class="mt-5 flex w-full cursor-pointer items-center justify-center gap-2 rounded-full border border-hairline bg-panel-raised px-4 py-2.5 font-body text-[14px] font-medium text-ink transition-colors hover:border-diagnose/40 disabled:cursor-not-allowed disabled:opacity-50"
			>
				{googleBusy ? 'Redirecting to Google…' : 'Sign up with Google'}
			</button>

			<p class="mt-6 text-center font-body text-[13px] text-ink-dim">
				Already have an account?
				<a href="/login" class="font-medium text-diagnose hover:underline">Sign in</a>
			</p>
		{/if}
	</div>
</div>
