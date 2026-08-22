<script>
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { session } from '$lib/shared/session.svelte.js';
	import { appPath, apiPath } from '$lib/shared/paths.js';

	let { children } = $props();

	const onCompleteProfile = $derived(page.url.pathname === appPath('/complete-profile'));

	$effect(() => {
		if (!session.loaded || !session.user) {
			if (session.loaded && !session.user) {
				const pathname = page.url.pathname;
				const apiPrefix = apiPath('');
				// Never stash API OAuth callback URLs as ?next= — they must hit FastAPI directly.
				if (pathname.startsWith(`${apiPrefix}/`) || pathname.includes('/accounts/auth/google/callback')) {
					window.location.replace(pathname + page.url.search);
					return;
				}
				const next = encodeURIComponent(pathname + page.url.search);
				goto(appPath(`/login?next=${next}`));
			}
			return;
		}
		// New Google users land here until they confirm a display name
		if (!onCompleteProfile && !(session.user.name || '').trim()) {
			goto(appPath('/complete-profile'));
		}
	});
</script>

{#if !session.loaded}
	<div class="flex h-screen items-center justify-center bg-white font-body text-brand-steel">
		Loading…
	</div>
{:else if session.user}
	{@render children?.()}
{:else}
	<div class="flex h-screen items-center justify-center bg-white font-body text-brand-steel">
		Redirecting to login…
	</div>
{/if}
