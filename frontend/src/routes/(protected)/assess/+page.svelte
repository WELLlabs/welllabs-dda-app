<script>
	import AssessProjects from '$lib/modules/assess/components/AssessProjects.svelte';
	import AssessForms from '$lib/modules/assess/components/AssessForms.svelte';
	import AssessSubmissions from '$lib/modules/assess/components/AssessSubmissions.svelte';

	/** view: 'projects' | 'forms' | 'submissions' */
	let view = $state('projects');
	let activeProject = $state(null);
	let activeForm = $state(null);

	function openProject(project) {
		activeProject = project;
		activeForm = null;
		view = 'forms';
	}

	function openForm(form) {
		activeForm = form;
		view = 'submissions';
	}

	function toProjects() {
		view = 'projects';
		activeProject = null;
		activeForm = null;
	}

	function toForms() {
		view = 'forms';
		activeForm = null;
	}

	let pageTitle = $derived(
		view === 'submissions'
			? `${activeForm?.name ?? activeForm?.xmlFormId ?? 'Form'} · Assess`
			: view === 'forms'
				? `${activeProject?.name ?? 'Project'} · Assess`
				: 'Assess · Water Security Tool'
	);
</script>

<svelte:head>
	<title>{pageTitle}</title>
</svelte:head>

<div class="min-h-screen bg-brand-pale/20">
	{#if view === 'projects'}
		{#key 'projects'}
			<AssessProjects onOpen={openProject} />
		{/key}
	{:else if view === 'forms'}
		{#key activeProject?.id}
			<AssessForms project={activeProject} onOpen={openForm} onBack={toProjects} />
		{/key}
	{:else if view === 'submissions'}
		{#key activeForm?.xmlFormId}
			<AssessSubmissions project={activeProject} form={activeForm} onBack={toForms} onHome={toProjects} />
		{/key}
	{/if}
</div>
