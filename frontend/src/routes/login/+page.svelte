<script>
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { login, requestVerifyEmail, startGoogleAuth } from '$lib/modules/accounts/api.js';
	import { session } from '$lib/shared/session.svelte.js';
	import ContourBackground from '$lib/shared/components/landing/ContourBackground.svelte';

	let email = $state('');
	let password = $state('');
	let submitting = $state(false);
	let error = $state('');
	let needsVerify = $state(false);
	let resendMsg = $state('');
	let googleBusy = $state(false);

	function isUnverifiedError(message) {
		const m = String(message).toLowerCase();
		return m.includes('verify') || m.includes('not verified') || m.includes('login_user_not_verified');
	}

	async function handleSubmit(e) {
		e.preventDefault();
		if (!email.trim() || !password) return;
		submitting = true;
		error = '';
		needsVerify = false;
		resendMsg = '';
		try {
			const user = await login(email.trim(), password);
			session.setUser(user);
			const next = page.url.searchParams.get('next') || '/home';
			goto(next);
		} catch (err) {
			const msg = String(err.message ?? err);
			error = msg;
			needsVerify = isUnverifiedError(msg);
		} finally {
			submitting = false;
		}
	}

	async function resendVerify() {
		resendMsg = '';
		try {
			await requestVerifyEmail(email.trim());
			resendMsg = 'Verification email sent — check your inbox.';
		} catch (err) {
			resendMsg = String(err.message ?? err);
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
	<title>Sign in · DDA</title>
</svelte:head>

<div class="relative flex min-h-screen items-center justify-center overflow-hidden bg-void px-4 font-body">
	<ContourBackground intensity="ambient" />

	<div class="relative z-10 w-full max-w-sm rounded-[20px] border border-hairline bg-panel p-8 shadow-glass">
		<span class="font-mono text-[11px] uppercase tracking-[0.2em] text-diagnose">Welcome back</span>
		<h1 class="mt-2 font-display text-2xl text-ink">Sign in</h1>
		<p class="mt-1 font-body text-[13px] text-ink-dim">Access your watershed workspace.</p>

		<form onsubmit={handleSubmit} class="mt-7 flex flex-col gap-4">
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
					class="w-full rounded-lg border border-hairline bg-panel-raised px-3 py-2.5 font-body text-[14px] text-ink placeholder:text-ink-faint focus:border-diagnose/60 focus:outline-none focus:ring-1 focus:ring-diagnose/40"
					bind:value={password}
					autocomplete="current-password"
				/>
				<p class="m-0 mt-1.5 text-right">
					<a href="/forgot-password" class="font-mono text-[11px] text-diagnose hover:underline">Forgot password?</a>
				</p>
			</div>

			{#if error}
				<p class="m-0 font-mono text-[12px] text-red-400">{error}</p>
			{/if}
			{#if needsVerify}
				<button
					type="button"
					class="cursor-pointer text-left font-mono text-[12px] text-diagnose hover:underline"
					onclick={resendVerify}
				>
					Resend verification email
				</button>
			{/if}
			{#if resendMsg}
				<p class="m-0 font-mono text-[12px] text-ink-dim">{resendMsg}</p>
			{/if}

			<button
				type="submit"
				class="mt-2 cursor-pointer rounded-full bg-brand-blue px-4 py-2.5 font-body text-[14px] font-semibold text-white shadow-glass transition-all duration-200 hover:bg-brand-deep disabled:cursor-not-allowed disabled:opacity-50"
				disabled={submitting || !email.trim() || !password}
			>
				{submitting ? 'Signing in…' : 'Sign in'}
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
			{googleBusy ? 'Redirecting to Google…' : 'Sign in with Google'}
		</button>

		<p class="mt-6 text-center font-body text-[13px] text-ink-dim">
			Don't have an account?
			<a href="/register" class="font-medium text-diagnose hover:underline">Register</a>
		</p>
	</div>
</div>
