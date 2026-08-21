<script>
	import { OBSERVATION_ZONE_COLOR } from '$lib/modules/diagnose/map-constants';

	/** @type {{ size?: 'sm' | 'md', class?: string }} */
	let { size = 'md', class: className = '' } = $props();

	const box = $derived(size === 'sm' ? 'h-7 w-7 rounded-md' : 'h-10 w-10 rounded-lg');
	const icon = $derived(size === 'sm' ? 'h-3.5 w-3.5' : 'h-5 w-5');
	const bg = $derived(`color-mix(in srgb, ${OBSERVATION_ZONE_COLOR} 18%, transparent)`);
</script>

<div
	class="flex shrink-0 items-center justify-center {box} {className}"
	style:background-color={bg}
	aria-hidden="true"
>
	<svg
		xmlns="http://www.w3.org/2000/svg"
		viewBox="0 0 24 24"
		fill="none"
		stroke={OBSERVATION_ZONE_COLOR}
		stroke-width="1.75"
		class={icon}
	>
		<circle cx="12" cy="12" r="7.5" />
		<path d="M12 4.5v15M4.5 12h15" />
		<circle cx="12" cy="12" r="1.75" fill={OBSERVATION_ZONE_COLOR} stroke="none" />
	</svg>
</div>
