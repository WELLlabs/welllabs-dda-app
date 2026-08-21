<script>
	import { onMount } from 'svelte';
	import '../app.css';
	import { session } from '$lib/shared/session.svelte.js';

	let { children } = $props();

	onMount(() => {
		session.loadSession();
	});
</script>

<svelte:head>
	<title>WST fork</title>
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
	<link
		href="https://fonts.googleapis.com/css2?family=Josefin+Sans:wght@400;600;700&family=Montserrat:wght@400;500;600&display=swap"
		rel="stylesheet"
	/>
</svelte:head>

{@render children?.()}
