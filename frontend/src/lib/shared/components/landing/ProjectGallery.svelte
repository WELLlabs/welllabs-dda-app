<script lang="ts">
	import { galleryProjects, type ProjectStatus } from '$lib/data/mock';

	const statusStyles: Record<ProjectStatus, string> = {
		Active: 'text-diagnose border-diagnose/30 bg-diagnose/10',
		'In Review': 'text-assess border-assess/30 bg-assess/10',
		Survey: 'text-design border-design/30 bg-design/10',
		Complete: 'text-ink-dim border-hairline bg-panel-raised'
	};

	function terrainPath(seed: number) {
		let d = 'M0,';
		const points = 8;
		for (let i = 0; i <= points; i++) {
			const x = (i / points) * 320;
			const y = 60 + Math.sin(i * seed) * 26 + Math.cos(i * seed * 0.6) * 14;
			d += (i === 0 ? '' : ' L' + x.toFixed(1) + ',') + y.toFixed(1);
		}
		return d;
	}
</script>

<section id="projects" class="relative bg-void py-20">
	<div class="mx-auto mb-10 max-w-6xl px-6 md:px-10">
		<span class="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-faint">Across the network</span>
		<h2 class="mt-2 font-display text-3xl text-ink md:text-4xl">Watershed projects.</h2>
	</div>

	<div class="no-scrollbar flex gap-5 overflow-x-auto px-6 pb-4 md:px-10" style="scroll-snap-type: x mandatory;">
		{#each galleryProjects as project, i}
			<div
				class="group relative h-[340px] w-[300px] shrink-0 overflow-hidden rounded-[20px] border border-hairline bg-panel shadow-glass transition-transform duration-500 hover:-translate-y-1 md:w-[340px]"
				style="scroll-snap-align: start;"
			>
				<div class="absolute inset-0" style="background: radial-gradient(ellipse at 30% 20%, {project.hue}22 0%, #0D131900 65%);"></div>
				<svg viewBox="0 0 320 220" class="absolute inset-x-0 top-0 h-[220px] w-full opacity-70" preserveAspectRatio="none">
					{#each [1, 1.4, 1.8] as seed, si}
						<path d={terrainPath(seed + i * 0.3)} fill="none" stroke={project.hue} stroke-width="0.8" opacity={0.5 - si * 0.12} />
					{/each}
				</svg>

				<span class="absolute right-4 top-4 rounded-full border px-3 py-1 font-mono text-[10px] uppercase tracking-wide {statusStyles[project.status]}">
					{project.status}
				</span>

				<div class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-panel via-panel/90 to-transparent p-5 pt-14">
					<p class="font-mono text-[10px] text-ink-faint">{project.coords}</p>
					<h3 class="mt-1 font-display text-xl text-ink">{project.name}</h3>
					<p class="mt-1 font-body text-[12px] text-ink-dim">{project.basin}</p>
				</div>
			</div>
		{/each}

		<div class="w-1 shrink-0"></div>
	</div>
</section>
