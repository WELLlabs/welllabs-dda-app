<script lang="ts">
	import { onMount } from 'svelte';
	import { animate, stagger } from 'motion';
	import { appPath } from '$lib/shared/paths.js';
	import RiverFlow from './RiverFlow.svelte';

	/** @type {HTMLElement[]} */
	let lines: HTMLElement[] = [];
	let sub: HTMLElement;
	let cta: HTMLElement;

	const headline = [
		{ lead: 'Diagnose', rest: ' watershed problems.' },
		{ lead: 'Design', rest: ' optimal solutions.' },
		{ lead: 'Assess', rest: ' impact simply.' }
	];

	onMount(() => {
		animate(
			lines,
			{ opacity: [0, 1], transform: ['translateY(18px)', 'translateY(0)'] },
			{ duration: 0.85, delay: stagger(0.12), easing: [0.16, 1, 0.3, 1] }
		);
		animate(
			sub,
			{ opacity: [0, 1], transform: ['translateY(10px)', 'translateY(0)'] },
			{ duration: 0.75, delay: 0.5, easing: [0.16, 1, 0.3, 1] }
		);
		animate(
			cta,
			{ opacity: [0, 1], transform: ['translateY(8px)', 'translateY(0)'] },
			{ duration: 0.7, delay: 0.7, easing: [0.16, 1, 0.3, 1] }
		);
	});
</script>

<section
	class="relative flex min-h-screen w-full items-center justify-center overflow-hidden bg-transparent pb-24 pt-28"
>
	<div class="relative z-10 mx-auto flex w-full max-w-5xl flex-col items-center px-6 text-center">
		<h1
			class="font-display text-[clamp(1.35rem,5.2vw,3.75rem)] leading-[1.15] tracking-tight text-ink"
		>
			{#each headline as row, i}
				<span bind:this={lines[i]} class="block whitespace-nowrap opacity-0">
					<span class="text-diagnose">{row.lead}</span>{row.rest}
				</span>
			{/each}
		</h1>

		<p
			bind:this={sub}
			class="mt-8 max-w-xl text-balance font-body text-[16px] leading-relaxed text-ink-dim opacity-0 md:text-lg"
		>
			Science-led, community-driven watershed management.
		</p>

		<div bind:this={cta} class="mt-8 opacity-0">
			<a
				href={appPath('/register')}
				class="inline-flex items-center justify-center rounded-full bg-brand-blue px-7 py-3 font-body text-[15px] font-semibold text-white shadow-glass transition-all duration-200 hover:bg-brand-deep"
			>
				Get started
			</a>
		</div>
	</div>

	<RiverFlow className="pointer-events-none absolute bottom-0 left-0 z-[5] h-24 w-full opacity-70" />
</section>
