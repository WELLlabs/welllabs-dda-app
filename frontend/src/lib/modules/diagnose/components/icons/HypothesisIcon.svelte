<script>
	import { HYPOTHESIS_COLOR } from '$lib/modules/diagnose/map-constants';

	/** @type {{ size?: 'sm' | 'md', class?: string }} */
	let { size = 'md', class: className = '' } = $props();

	const box = $derived(size === 'sm' ? 'h-7 w-7 rounded-md' : 'h-10 w-10 rounded-lg');
	const icon = $derived(size === 'sm' ? 'h-3.5 w-3.5' : 'h-5 w-5');
	const bg = $derived(`color-mix(in srgb, ${HYPOTHESIS_COLOR} 20%, transparent)`);
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
		stroke={HYPOTHESIS_COLOR}
		stroke-width="1.75"
		class={icon}
	>
		<path
			stroke-linecap="round"
			stroke-linejoin="round"
			d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.2 11.1c.4.3.7.7.9 1.2L10 17h4l.3-1.7c.2-.5.5-.9.9-1.2A6 6 0 0 0 12 3z"
		/>
		<path stroke-linecap="round" d="M12 7v3M12 13h.01" />
	</svg>
</div>
