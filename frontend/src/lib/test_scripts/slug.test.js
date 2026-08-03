import { describe, expect, it } from 'vitest';
import { findBySlug, itemPath, slugify } from '../shared/slug.js';

describe('slugify', () => {
	it('lowercases and hyphenates spaces', () => {
		expect(slugify('My Project Name')).toBe('my-project-name');
	});

	it('trims and collapses repeated separators', () => {
		expect(slugify('  Foo   Bar--Baz  ')).toBe('foo-bar-baz');
	});

	it('strips diacritics and non-alphanumeric characters', () => {
		expect(slugify('Café — Watershed #1!')).toBe('cafe-watershed-1');
	});

	it('strips underscores (non-alphanumeric before hyphen collapse)', () => {
		expect(slugify('field_note_area')).toBe('fieldnotearea');
		expect(slugify('field note_area')).toBe('field-notearea');
	});

	it('returns fallback slug for empty input', () => {
		expect(slugify('')).toBe('item');
		expect(slugify('!!!')).toBe('item');
	});
});

describe('itemPath', () => {
	it('builds a path from base and slugified name', () => {
		const item = { id: 'abc12345-xxxx', name: 'North Basin' };
		expect(itemPath('/diagnose', item)).toBe('/diagnose/north-basin');
	});

	it('appends short id when multiple items share a slug', () => {
		const items = [
			{ id: 'aaaaaaaa-1111', name: 'North Basin' },
			{ id: 'bbbbbbbb-2222', name: 'North Basin' }
		];
		expect(itemPath('/diagnose', items[0], items)).toBe('/diagnose/north-basin-aaaaaaaa');
		expect(itemPath('/diagnose', items[1], items)).toBe('/diagnose/north-basin-bbbbbbbb');
	});

	it('does not disambiguate when slug is unique among items', () => {
		const items = [
			{ id: 'aaaaaaaa-1111', name: 'North Basin' },
			{ id: 'bbbbbbbb-2222', name: 'South Basin' }
		];
		expect(itemPath('/diagnose', items[0], items)).toBe('/diagnose/north-basin');
	});
});

describe('findBySlug', () => {
	const items = [
		{ id: 'aaaaaaaa-1111', name: 'North Basin', updated_at: '2024-01-01T00:00:00Z' },
		{ id: 'bbbbbbbb-2222', name: 'North Basin', updated_at: '2024-06-01T00:00:00Z' },
		{ id: 'cccccccc-3333', name: 'South Basin', updated_at: '2024-03-01T00:00:00Z' }
	];

	it('returns null for empty slug', () => {
		expect(findBySlug(items, '')).toBeNull();
		expect(findBySlug(items, null)).toBeNull();
	});

	it('resolves a unique slug match', () => {
		expect(findBySlug(items, 'south-basin')).toEqual(items[2]);
	});

	it('resolves a disambiguated slug with id prefix', () => {
		expect(findBySlug(items, 'north-basin-aaaaaaaa')).toEqual(items[0]);
		expect(findBySlug(items, 'north-basin-bbbbbbbb')).toEqual(items[1]);
	});

	it('picks most recently updated when bare slug collides', () => {
		expect(findBySlug(items, 'north-basin')).toEqual(items[1]);
	});

	it('returns null when no match exists', () => {
		expect(findBySlug(items, 'missing-project')).toBeNull();
	});
});
