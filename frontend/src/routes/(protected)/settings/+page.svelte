<script>
	import { session } from '$lib/shared/session.svelte.js';
</script>

<svelte:head>
	<title>Account · Settings</title>
</svelte:head>

<div class="max-w-2xl">
	<h2 class="m-0 mb-5 font-headline text-lg font-semibold text-brand-navy">Account</h2>

	{#if session.user}
		<section class="rounded-2xl border border-brand-navy/10 bg-white p-5 shadow-sm">
			<div class="flex items-center gap-4">
				<div
					class="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-brand-navy text-lg font-semibold text-white"
				>
					{(session.user.name ?? '?').charAt(0).toUpperCase()}
				</div>
				<div>
					<p class="m-0 font-body text-base font-medium text-brand-navy">{session.user.name}</p>
					<p class="m-0 mt-1 text-sm text-brand-steel">{session.user.email}</p>
				</div>
			</div>
		</section>
	{/if}
</div>
