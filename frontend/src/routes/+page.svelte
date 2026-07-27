<script lang="ts">
	import { onMount } from 'svelte';
	import { animate, inView } from 'motion';
	import Nav from '$lib/shared/components/landing/Nav.svelte';
	import LandingBackground from '$lib/shared/components/landing/LandingBackground.svelte';
	import Hero from '$lib/shared/components/landing/Hero.svelte';
	import WorkspacePanels from '$lib/shared/components/landing/WorkspacePanels.svelte';
	import MetricsOverview from '$lib/shared/components/landing/MetricsOverview.svelte';
	import Footer from '$lib/shared/components/landing/Footer.svelte';

	onMount(() => {
		const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
		const reveals = document.querySelectorAll<HTMLElement>('[data-reveal]');
		reveals.forEach((el) => {
			if (prefersReduced) {
				el.style.opacity = '1';
				return;
			}
			el.style.opacity = '0';
			inView(
				el,
				() => {
					animate(
						el,
						{ opacity: [0, 1], transform: ['translateY(24px)', 'translateY(0)'] },
						{ duration: 0.8, easing: [0.16, 1, 0.3, 1] }
					);
				},
				{ margin: '-10% 0px -10% 0px' }
			);
		});
	});
</script>

<svelte:head>
	<title>DDA</title>
	<meta name="description" content="One workspace. Every watershed. Every decision." />
</svelte:head>

<LandingBackground />

<Nav />

<main class="relative z-10 bg-transparent">
	<Hero />

	<div data-reveal>
		<WorkspacePanels />
	</div>

	<div data-reveal>
		<MetricsOverview />
	</div>

	<Footer />
</main>
