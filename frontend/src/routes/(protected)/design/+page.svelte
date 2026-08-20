<script>
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';
</script>

<svelte:head>
	<title>Design · WST fork</title>
</svelte:head>

<div class="flex h-full min-h-screen flex-col bg-white font-body">
	<ModuleHeader title="Design" />

	<main class="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
		<div
			class="flex h-16 w-16 items-center justify-center rounded-2xl"
			style:background-color="color-mix(in srgb, #0d983b 16%, transparent)"
		>
			<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#0d983b" stroke-width="1.5" class="h-8 w-8">
				<path d="M4 19.5V16l9-9 3.5 3.5-9 9H4z" stroke-linejoin="round" />
				<path d="M13 7l3.5 3.5" />
				<path d="M17.5 4.5 19.5 6.5" stroke-linecap="round" />
			</svg>
		</div>
		<h2 class="m-0 font-headline text-xl font-semibold text-brand-navy">Design module — coming soon</h2>
		<p class="m-0 max-w-md text-sm text-brand-steel">
			This module will let teams plan and design interventions on top of diagnosed watersheds.
			The API for this module is scaffolded at <code class="rounded bg-brand-pale px-1 py-0.5">/api/design</code>.
		</p>
	</main>
</div>
