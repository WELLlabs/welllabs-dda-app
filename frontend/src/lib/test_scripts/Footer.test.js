import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import Footer from '../shared/components/landing/Footer.svelte';

describe('Footer', () => {
	it('renders product label and version', () => {
		render(Footer);

		expect(screen.getByText(/dda\s+diagnose, design & assess/i)).toBeInTheDocument();
		expect(screen.getByText(/system status: nominal/i)).toBeInTheDocument();
		expect(screen.getByText('v2.4.1')).toBeInTheDocument();
	});
});
