import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import Nav from '../shared/components/landing/Nav.svelte';

describe('Nav', () => {
	it('renders brand and auth CTAs', () => {
		render(Nav);

		expect(screen.getByText(/water security tool/i)).toBeInTheDocument();
		expect(screen.getByRole('link', { name: /get started/i })).toHaveAttribute('href', '/register');
		expect(screen.getByRole('link', { name: /sign in/i })).toHaveAttribute('href', '/login');
	});
});
