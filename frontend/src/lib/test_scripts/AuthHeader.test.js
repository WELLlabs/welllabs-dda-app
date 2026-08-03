import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import AuthHeader from '../shared/components/auth/AuthHeader.svelte';

describe('AuthHeader', () => {
	it('renders brand link to home for login variant', () => {
		render(AuthHeader, { props: { variant: 'login' } });

		expect(screen.getByRole('link', { name: /water security tool/i })).toHaveAttribute('href', '/');
		expect(screen.getByRole('link', { name: /create account/i })).toHaveAttribute('href', '/register');
		expect(screen.queryByRole('link', { name: /sign in/i })).not.toBeInTheDocument();
	});

	it('shows sign-in link for register variant', () => {
		render(AuthHeader, { props: { variant: 'register' } });

		expect(screen.getByRole('link', { name: /sign in/i })).toHaveAttribute('href', '/login');
		expect(screen.queryByRole('link', { name: /create account/i })).not.toBeInTheDocument();
	});

	it('defaults to login variant', () => {
		render(AuthHeader);

		expect(screen.getByRole('link', { name: /create account/i })).toBeInTheDocument();
	});
});
