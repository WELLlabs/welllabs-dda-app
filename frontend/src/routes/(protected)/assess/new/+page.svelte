<script>
	import { appPath } from '$lib/shared/paths.js';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	onMount(() => {
		goto(appPath('/assess'), { replaceState: true });
	});
</script>

<svelte:head>
	<title>Assess</title>
</svelte:head>

<p class="p-6 text-brand-steel">Redirecting to MEL projects…</p>
