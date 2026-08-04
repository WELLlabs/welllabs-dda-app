<script>
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { updateMe } from '$lib/modules/accounts/api.js';
	import { session } from '$lib/shared/session.svelte.js';
	import ContourBackground from '$lib/shared/components/landing/ContourBackground.svelte';

	let name = $state('');
	let submitting = $state(false);
	let error = $state('');
	let primed = $state(false);

	$effect(() => {
		if (!session.loaded || !session.user || primed) return;
		name = session.user.name || '';
		primed = true;
	});

	async function handleSubmit(e) {
		e.preventDefault();
		const trimmed = name.trim();
		if (trimmed.length < 1) {
			error = 'Please enter your name.';
			return;
		}
		submitting = true;
		error = '';
		try {
			const updated = await updateMe({ name: trimmed });
			session.setUser({
				...session.user,
				name: updated?.name ?? trimmed
			});
			const next = page.url.searchParams.get('next') || '/home';
			goto(next);
		} catch (err) {
			error = String(err.message ?? err);
		} finally {
			submitting = false;
		}
	}
</script>

<svelte:head>
	<title>Your name · DDA</title>
</svelte:head>

<div class="relative flex min-h-screen items-center justify-center overflow-hidden bg-void px-4 font-body">
	<ContourBackground intensity="ambient" />

	<div class="relative z-10 w-full max-w-sm rounded-[20px] border border-hairline bg-panel p-8 shadow-glass">
		<span class="font-mono text-[11px] uppercase tracking-[0.2em] text-diagnose">Almost there</span>
		<h1 class="mt-2 font-display text-2xl text-ink">Confirm your name</h1>
		<p class="mt-1 font-body text-[13px] text-ink-dim">
			This is how you’ll appear in projects and sharing. You can change it later in settings.
		</p>

		<form onsubmit={handleSubmit} class="mt-7 flex flex-col gap-4">
			<div>
				<label class="mb-1.5 block font-mono text-[11px] uppercase tracking-wide text-ink-faint" for="name">
					Name
				</label>
				<input
					id="name"
					type="text"
					required
					minlength="1"
					maxlength="200"
					class="w-full rounded-lg border border-hairline bg-panel-raised px-3 py-2.5 font-body text-[14px] text-ink placeholder:text-ink-faint focus:border-diagnose/60 focus:outline-none focus:ring-1 focus:ring-diagnose/40"
					bind:value={name}
					autocomplete="name"
					placeholder="Your name"
				/>
			</div>

			{#if error}
				<p class="m-0 font-mono text-[12px] text-red-400">{error}</p>
			{/if}

			<button
				type="submit"
				class="mt-2 cursor-pointer rounded-full bg-brand-blue px-4 py-2.5 font-body text-[14px] font-semibold text-white shadow-glass transition-all duration-200 hover:bg-brand-deep disabled:cursor-not-allowed disabled:opacity-50"
				disabled={submitting || !name.trim()}
			>
				{submitting ? 'Saving…' : 'Continue'}
			</button>
		</form>
	</div>
</div>
