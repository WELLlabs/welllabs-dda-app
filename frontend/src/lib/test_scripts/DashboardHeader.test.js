import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import DashboardHeader from '../shared/components/landing/DashboardHeader.svelte';

describe('DashboardHeader', () => {
	it('renders the app brand link', () => {
		render(DashboardHeader);

		expect(screen.getByRole('link', { name: /water security tool/i })).toBeInTheDocument();
	});

	it('links the brand to /home', () => {
		render(DashboardHeader);

		expect(screen.getByRole('link', { name: /water security tool/i })).toHaveAttribute(
			'href',
			'/home'
		);
	});

	it('accepts an optional name prop without crashing', () => {
		render(DashboardHeader, { props: { name: 'Ada Lovelace' } });

		expect(screen.getByRole('link', { name: /water security tool/i })).toBeInTheDocument();
	});
});
