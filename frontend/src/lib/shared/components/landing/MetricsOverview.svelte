<script lang="ts">
	import { onMount } from 'svelte';
	import { animate, inView } from 'motion';
	import { metrics } from '$lib/data/mock';

	let counters: HTMLElement[] = [];
	let sectionEl: HTMLElement;

	function sparkPoints(trend: number[]) {
		const max = Math.max(...trend);
		const min = Math.min(...trend);
		const w = 64;
		const h = 22;
		return trend
			.map((v, i) => {
				const x = (i / (trend.length - 1)) * w;
				const y = h - ((v - min) / (max - min || 1)) * h;
				return `${x.toFixed(1)},${y.toFixed(1)}`;
			})
			.join(' ');
	}

	onMount(() => {
		inView(sectionEl, () => {
			metrics.forEach((m, i) => {
				const el = counters[i];
				if (!el) return;
				const obj = { val: 0 };
				animate(
					(progress) => {
						const v = Math.round(m.value * progress);
						el.textContent = v.toLocaleString();
					},
					{ duration: 1.4, delay: i * 0.08, easing: [0.16, 1, 0.3, 1] }
				);
			});
		});
	});
</script>

<section bind:this={sectionEl} class="relative bg-transparent px-6 py-16 md:px-10">
	<div class="mx-auto max-w-6xl">
		<div class="grid grid-cols-2 gap-5 lg:grid-cols-4">
			{#each metrics as metric, i}
				<div class="rounded-[18px] border border-hairline bg-panel p-6 shadow-glass">
					<div class="flex items-start justify-between">
						<span class="font-mono text-[10px] uppercase tracking-[0.15em] text-ink-faint">{metric.label}</span>
						<svg width="64" height="22" viewBox="0 0 64 22" class="opacity-80">
							<polyline points={sparkPoints(metric.trend)} fill="none" stroke={metric.accent} stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" />
						</svg>
					</div>
					<div class="mt-4 font-display text-3xl text-ink" bind:this={counters[i]}>0</div>
				</div>
			{/each}
		</div>
	</div>
</section>
