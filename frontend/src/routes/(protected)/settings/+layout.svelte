<script>
	import { page } from '$app/state';
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';

	let { children } = $props();

	const navItems = [
		{ href: '/settings', label: 'Account' },
		{ href: '/settings/organizations', label: 'Organizations' },
		{ href: '/settings/connectors', label: 'Connectors' }
	];

	function isActive(href) {
		if (href === '/settings') return page.url.pathname === '/settings';
		return page.url.pathname.startsWith(href);
	}
</script>

<div class="flex min-h-screen flex-col bg-gray-50 font-body">
	<ModuleHeader title="Settings" />

	<div class="mx-auto flex w-full max-w-5xl flex-1 gap-0">
		<nav class="w-56 shrink-0 border-r border-brand-navy/8 bg-white py-4 pr-2 pl-4">
			<ul class="m-0 flex flex-col gap-0.5 p-0">
				{#each navItems as item (item.href)}
					<li>
						<a
							href={item.href}
							class="block rounded-lg px-3 py-2 font-body text-sm font-medium no-underline transition-colors {isActive(item.href)
								? 'bg-brand-sky/15 text-brand-navy'
								: 'text-brand-steel hover:bg-gray-50 hover:text-brand-navy'}"
						>
							{item.label}
						</a>
					</li>
				{/each}
			</ul>
		</nav>

		<main class="flex-1 overflow-auto p-6">
			{@render children?.()}
		</main>
	</div>
</div>
