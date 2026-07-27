<script lang="ts">
	export let intensity: 'hero' | 'ambient' = 'hero';

	// Deterministic pseudo-contour ring paths, generated once.
	const rings = Array.from({ length: 9 }, (_, i) => {
		const base = 60 + i * 46;
		const wobble = 18 + i * 2.2;
		return { r: base, wobble, dur: 26 + i * 4, delay: i * -3.4, opacity: 0.55 - i * 0.045 };
	});

	function ringPath(r: number, wobble: number, seed: number) {
		const points = 24;
		let d = '';
		for (let i = 0; i <= points; i++) {
			const angle = (i / points) * Math.PI * 2;
			const n = Math.sin(angle * 3 + seed) * wobble + Math.cos(angle * 5 - seed) * (wobble * 0.4);
			const radius = r + n;
			const x = 500 + Math.cos(angle) * radius;
			const y = 380 + Math.sin(angle) * radius * 0.62;
			d += (i === 0 ? 'M' : 'L') + x.toFixed(1) + ',' + y.toFixed(1) + ' ';
		}
		return d + 'Z';
	}

	const particles = Array.from({ length: 14 }, (_, i) => ({
		x: (i * 71) % 100,
		y: (i * 133) % 100,
		delay: (i % 7) * 0.7,
		dur: 6 + (i % 5)
	}));
</script>

<div class="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
	<svg
		viewBox="0 0 1000 760"
		preserveAspectRatio="xMidYMid slice"
		class="absolute inset-0 h-full w-full {intensity === 'hero' ? 'animate-drift' : ''}"
	>
		<defs>
			<radialGradient id="contour-fade" cx="50%" cy="48%" r="60%">
				<stop offset="0%" stop-color="#ffffff" stop-opacity="0" />
				<stop offset="100%" stop-color="#ffffff" stop-opacity="0.9" />
			</radialGradient>
			<linearGradient id="contour-stroke" x1="0" y1="0" x2="1" y2="1">
				<stop offset="0%" stop-color="#0d983b" />
				<stop offset="100%" stop-color="#7dc3ff" />
			</linearGradient>
		</defs>

		{#each rings as ring, i}
			<path
				d={ringPath(ring.r, ring.wobble, i * 1.3)}
				fill="none"
				stroke={i % 4 === 0 ? 'url(#contour-stroke)' : '#cdd9e8'}
				stroke-width={i % 4 === 0 ? 1.1 : 0.7}
				opacity={ring.opacity}
			/>
		{/each}

		<rect x="0" y="0" width="1000" height="760" fill="url(#contour-fade)" />
	</svg>

	{#each particles as p}
		<span
			class="absolute h-[3px] w-[3px] rounded-full bg-diagnose/70 animate-pulse-soft"
			style="left:{p.x}%; top:{p.y}%; animation-delay:{p.delay}s; animation-duration:{p.dur}s"
		></span>
	{/each}
</div>
