<script>
	import { FIELD_NOTE_COLOR } from '$lib/modules/diagnose/map-constants';

	/** @type {{ size?: 'sm' | 'md', class?: string }} */
	let { size = 'md', class: className = '' } = $props();

	const box = $derived(size === 'sm' ? 'h-7 w-7 rounded-md' : 'h-10 w-10 rounded-lg');
	const icon = $derived(size === 'sm' ? 'h-3.5 w-3.5' : 'h-5 w-5');
	const bg = $derived(`color-mix(in srgb, ${FIELD_NOTE_COLOR} 22%, transparent)`);
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
		stroke={FIELD_NOTE_COLOR}
		stroke-width="1.75"
		class={icon}
	>
		<path
			stroke-linejoin="round"
			d="M8 4h8a2 2 0 0 1 2 2v14l-4-2.5L10 20V6a2 2 0 0 1 2-2H8"
		/>
		<path d="M10 8h6M10 11.5h6M10 15h4" stroke-linecap="round" />
	</svg>
</div>
