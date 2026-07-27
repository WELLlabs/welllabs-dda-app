<script lang="ts">
	// Full-page ambient backdrop for the landing route.
	// Soft gradient wash + drifting brand-colour glows + faint topographic contours.

	// Deterministic contour rings (topographic feel), generated once.
	const rings = Array.from({ length: 7 }, (_, i) => {
		const base = 120 + i * 70;
		const wobble = 26 + i * 3;
		return { r: base, wobble, opacity: 0.5 - i * 0.05, accent: i % 3 === 0 };
	});

	function ringPath(r: number, wobble: number, seed: number) {
		const points = 26;
		let d = '';
		for (let i = 0; i <= points; i++) {
			const angle = (i / points) * Math.PI * 2;
			const n = Math.sin(angle * 3 + seed) * wobble + Math.cos(angle * 5 - seed) * (wobble * 0.4);
			const radius = r + n;
			const x = 720 + Math.cos(angle) * radius;
			const y = 420 + Math.sin(angle) * radius * 0.62;
			d += (i === 0 ? 'M' : 'L') + x.toFixed(1) + ',' + y.toFixed(1) + ' ';
		}
		return d + 'Z';
	}
</script>

<div class="landing-bg" aria-hidden="true">
	<div class="wash"></div>

	<div class="glow g1"></div>
	<div class="glow g2"></div>
	<div class="glow g3"></div>
	<div class="glow g4"></div>

	<svg class="contours" viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice">
		<defs>
			<linearGradient id="lbg-accent" x1="0" y1="0" x2="1" y2="1">
				<stop offset="0%" stop-color="#0d983b" stop-opacity="0.55" />
				<stop offset="100%" stop-color="#7dc3ff" stop-opacity="0.55" />
			</linearGradient>
		</defs>
		{#each rings as ring, i}
			<path
				d={ringPath(ring.r, ring.wobble, i * 1.4)}
				fill="none"
				stroke={ring.accent ? 'url(#lbg-accent)' : '#d3deec'}
				stroke-width={ring.accent ? 1.1 : 0.7}
				opacity={ring.opacity}
			/>
		{/each}
	</svg>

	<div class="vignette"></div>
</div>

<style>
	.landing-bg {
		position: fixed;
		inset: 0;
		z-index: 0;
		overflow: hidden;
		pointer-events: none;
	}

	.wash {
		position: absolute;
		inset: 0;
		background:
			radial-gradient(120% 80% at 50% -10%, #ffffff 0%, #f4f8fc 45%, #eef4fb 100%);
	}

	.glow {
		position: absolute;
		border-radius: 9999px;
		filter: blur(100px);
		opacity: 0.5;
		will-change: transform;
		animation: drift 26s ease-in-out infinite;
	}
	.g1 {
		top: -12%;
		left: -8%;
		width: 46vw;
		height: 46vw;
		background: radial-gradient(circle, rgba(13, 152, 59, 0.24), transparent 70%);
	}
	.g2 {
		top: 8%;
		right: -12%;
		width: 44vw;
		height: 44vw;
		background: radial-gradient(circle, rgba(125, 195, 255, 0.3), transparent 70%);
		animation-delay: -7s;
	}
	.g3 {
		bottom: -16%;
		left: 10%;
		width: 42vw;
		height: 42vw;
		background: radial-gradient(circle, rgba(213, 180, 67, 0.22), transparent 70%);
		animation-delay: -13s;
	}
	.g4 {
		bottom: -8%;
		right: 6%;
		width: 38vw;
		height: 38vw;
		background: radial-gradient(circle, rgba(57, 105, 167, 0.2), transparent 70%);
		animation-delay: -19s;
	}
	@keyframes drift {
		0%, 100% { transform: translate(0, 0) scale(1); }
		33% { transform: translate(3%, 4%) scale(1.08); }
		66% { transform: translate(-3%, 2%) scale(0.96); }
	}

	.contours {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		opacity: 0.5;
		animation: sway 40s ease-in-out infinite;
	}
	@keyframes sway {
		0%, 100% { transform: translate3d(0, 0, 0) scale(1.02); }
		50% { transform: translate3d(-1.5%, 1%, 0) scale(1.06); }
	}

	.vignette {
		position: absolute;
		inset: 0;
		background: radial-gradient(120% 90% at 50% 40%, transparent 55%, rgba(0, 41, 107, 0.05) 100%);
	}

	@media (prefers-reduced-motion: reduce) {
		.glow, .contours { animation: none; }
	}
</style>
