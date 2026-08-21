<script>
	/** @type {{ geometry?: object | null, class?: string, circular?: boolean }} */
	let { geometry = null, class: className = '', circular = false } = $props();

	const VIEW = 64;
	const FILL = 'rgba(27, 117, 224, 0.2)';
	const STROKE = '#1b75e0';

	function buildPaths(geom) {
		if (!geom) return [];

		/** @type {number[][][][]} */
		let polygons = [];
		if (geom.type === 'Polygon') {
			polygons = [geom.coordinates];
		} else if (geom.type === 'MultiPolygon') {
			polygons = geom.coordinates;
		} else {
			return [];
		}

		let minX = Infinity;
		let minY = Infinity;
		let maxX = -Infinity;
		let maxY = -Infinity;

		for (const poly of polygons) {
			for (const ring of poly) {
				for (const [x, y] of ring) {
					minX = Math.min(minX, x);
					minY = Math.min(minY, y);
					maxX = Math.max(maxX, x);
					maxY = Math.max(maxY, y);
				}
			}
		}

		if (!Number.isFinite(minX)) return [];

		const width = maxX - minX || 1;
		const height = maxY - minY || 1;
		const pad = 10;
		const drawSize = VIEW - pad * 2;
		const scale = drawSize / Math.max(width, height);
		const drawnW = width * scale;
		const drawnH = height * scale;
		const offsetX = pad + (drawSize - drawnW) / 2;
		const offsetY = pad + (drawSize - drawnH) / 2;

		return polygons.flatMap((poly) =>
			poly.map((ring) =>
				ring
					.map(([x, y], i) => {
						const px = offsetX + (x - minX) * scale;
						const py = VIEW - offsetY - (y - minY) * scale;
						return `${i === 0 ? 'M' : 'L'}${px.toFixed(1)},${py.toFixed(1)}`;
					})
					.join(' ') + ' Z'
			)
		);
	}

	let paths = $derived(buildPaths(geometry));
</script>

{#if circular}
	<div
		class="relative flex h-full w-full items-center justify-center overflow-hidden rounded-full bg-gradient-to-br from-brand-sky/35 to-brand-blue/10 {className}"
	>
		<svg
			class="pointer-events-none absolute inset-0 h-full w-full opacity-30"
			viewBox="0 0 100 100"
			aria-hidden="true"
		>
			<ellipse cx="50" cy="50" rx="38" ry="28" fill="none" stroke="#94a3b8" stroke-width="0.6" />
			<ellipse cx="50" cy="50" rx="28" ry="20" fill="none" stroke="#94a3b8" stroke-width="0.5" />
			<ellipse cx="50" cy="50" rx="18" ry="12" fill="none" stroke="#94a3b8" stroke-width="0.4" />
		</svg>
		<svg
			viewBox="0 0 {VIEW} {VIEW}"
			preserveAspectRatio="xMidYMid meet"
			class="relative z-[1] h-[68%] w-[68%]"
			aria-hidden="true"
		>
			{#each paths as d}
				<path {d} fill={FILL} stroke={STROKE} stroke-width="1" stroke-linejoin="round" />
			{/each}
		</svg>
	</div>
{:else}
	<svg
		viewBox="0 0 {VIEW} {VIEW}"
		preserveAspectRatio="xMidYMid meet"
		class="block h-full w-full {className}"
		aria-hidden="true"
	>
		{#each paths as d}
			<path {d} fill={FILL} stroke={STROKE} stroke-width="0.75" stroke-linejoin="round" />
		{/each}
	</svg>
{/if}
