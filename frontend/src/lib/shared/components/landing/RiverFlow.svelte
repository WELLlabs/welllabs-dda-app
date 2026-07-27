<script lang="ts">
	export let className = '';
</script>

<svg
	class={className}
	viewBox="0 0 1200 120"
	preserveAspectRatio="none"
	aria-hidden="true"
>
	<defs>
		<linearGradient id="river-grad" x1="0" y1="0" x2="1" y2="0">
			<stop offset="0%" stop-color="#1b75e0" stop-opacity="0" />
			<stop offset="45%" stop-color="#1b75e0" stop-opacity="0.75" />
			<stop offset="55%" stop-color="#7dc3ff" stop-opacity="0.85" />
			<stop offset="100%" stop-color="#1b75e0" stop-opacity="0" />
		</linearGradient>
	</defs>

	<path
		d="M0,60 C150,20 250,100 400,60 C550,20 650,100 800,60 C950,20 1050,100 1200,60"
		fill="none"
		stroke="#dbe4ef"
		stroke-width="1"
	/>

	<path
		id="river-path"
		d="M0,60 C150,20 250,100 400,60 C550,20 650,100 800,60 C950,20 1050,100 1200,60"
		fill="none"
		stroke="url(#river-grad)"
		stroke-width="1.4"
		stroke-linecap="round"
		stroke-dasharray="140 900"
	>
		<animate attributeName="stroke-dashoffset" from="0" to="-1040" dur="9s" repeatCount="indefinite" />
	</path>
</svg>
