import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import ModuleHeader from '../shared/components/ModuleHeader.svelte';

describe('ModuleHeader', () => {
	it('renders brand home links', () => {
		render(ModuleHeader, { props: { title: 'Diagnose' } });

		expect(screen.getByRole('link', { name: /home/i })).toHaveAttribute('href', '/home');
		expect(screen.getByRole('link', { name: /water security tool/i })).toHaveAttribute('href', '/home');
		expect(screen.getByText('Diagnose')).toBeInTheDocument();
	});

	it('uses custom homeHref', () => {
		render(ModuleHeader, { props: { homeHref: '/dashboard', title: 'Assess' } });

		expect(screen.getByRole('link', { name: /home/i })).toHaveAttribute('href', '/dashboard');
		expect(screen.getByRole('link', { name: /water security tool/i })).toHaveAttribute(
			'href',
			'/dashboard'
		);
	});

	it('links the module title when titleHref is set', () => {
		render(ModuleHeader, {
			props: { title: 'Diagnose', titleHref: '/diagnose', project: 'North Basin' }
		});

		expect(screen.getByRole('link', { name: 'Diagnose' })).toHaveAttribute('href', '/diagnose');
		expect(screen.getByText('North Basin')).toBeInTheDocument();
	});

	it('renders module title as plain text when titleHref is absent', () => {
		render(ModuleHeader, { props: { title: 'Design' } });

		expect(screen.queryByRole('link', { name: 'Design' })).not.toBeInTheDocument();
		expect(screen.getByText('Design')).toBeInTheDocument();
	});
});
