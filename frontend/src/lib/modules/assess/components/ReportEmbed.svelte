<script>
	// Renders a project's dashboard via Metabase embed.js from a backend-signed report payload.
	let { report } = $props();

	const tag = report.resource === 'question' ? 'metabase-question' : 'metabase-dashboard';

	// Load embed.js once and set the global config it reads on init.
	function ensureEmbedScript(instanceUrl) {
		if (typeof window === 'undefined') return;
		window.metabaseConfig = {
			instanceUrl,
			theme: { preset: 'light' },
			isGuest: true
		};
		if (document.querySelector('script[data-metabase-embed]')) return;
		const script = document.createElement('script');
		script.defer = true;
		script.src = `${instanceUrl}/app/embed.js`;
		script.setAttribute('data-metabase-embed', 'true');
		document.head.appendChild(script);
	}

	$effect(() => {
		ensureEmbedScript(report.instance_url);
	});
</script>

<!-- embed.js upgrades this element on load; updating token re-renders it in place. -->
<svelte:element this={tag} token={report.token} with-title="true" class="block h-full w-full"
></svelte:element>
