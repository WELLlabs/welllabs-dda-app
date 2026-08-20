<script>
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { findBySlug, itemPath } from '$lib/shared/slug.js';
	import { fetchMelProjects } from '$lib/modules/assess/mel-api';

	let slug = $derived(page.params.slug);

	onMount(async () => {
		try {
			const res = await fetchMelProjects();
			const projects = res.projects ?? [];
			const project = findBySlug(projects, slug);
			if (project) {
				goto(itemPath('/assess', project, projects), { replaceState: true });
				return;
			}
		} catch {
			// fall through
		}
		goto('/assess', { replaceState: true });
	});
</script>

<p class="p-6 text-brand-steel">Redirecting…</p>
