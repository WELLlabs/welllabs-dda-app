<script lang="ts">
	import { onMount } from 'svelte';
	import { animate, stagger } from 'motion';
	import RiverFlow from './RiverFlow.svelte';

	let words: HTMLElement[] = [];
	let sub: HTMLElement;
	let meta: HTMLElement;

	onMount(() => {
		animate(
			words,
			{ opacity: [0, 1], transform: ['translateY(18px)', 'translateY(0)'] },
			{ duration: 0.9, delay: stagger(0.09), easing: [0.16, 1, 0.3, 1] }
		);
		animate(sub, { opacity: [0, 1], transform: ['translateY(10px)', 'translateY(0)'] }, { duration: 0.8, delay: 0.55, easing: [0.16, 1, 0.3, 1] });
		animate(meta, { opacity: [0, 1] }, { duration: 1, delay: 0.9 });
	});

	const line = 'One Workspace. Every Watershed. Every Decision.'.split(' ');
</script>

<section class="relative flex h-screen min-h-[720px] w-full items-center justify-center overflow-hidden bg-transparent">
	<div class="relative z-10 mx-auto flex max-w-4xl flex-col items-center px-6 text-center">
		<div bind:this={meta} class="mb-7 flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.2em] text-diagnose opacity-0">
			<span class="h-1 w-1 rounded-full bg-diagnose"></span>
			Platform online  live hydrological feed
		</div>

		<h1 class="font-display text-[13vw] leading-[1.02] tracking-tight text-ink sm:text-6xl md:text-7xl lg:text-[5.5rem]">
			{#each line as word, i}
				<span
					bind:this={words[i]}
					class="mx-[0.18em] inline-block opacity-0"
					class:text-diagnose={word === 'Watershed.'}
				>{word}</span>
			{/each}
		</h1>

		<p bind:this={sub} class="mt-7 max-w-lg text-balance font-body text-[15px] leading-relaxed text-ink-dim opacity-0 md:text-base">
			Diagnose, design, and assess interventions across every basin  in one continuous field of data.
		</p>
	</div>

	<RiverFlow className="pointer-events-none absolute bottom-0 left-0 z-[5] h-24 w-full opacity-70" />

</section>
