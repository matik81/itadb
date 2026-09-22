import { render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from './App';

afterEach(() => vi.unstubAllGlobals());
it('shows a genuine empty catalog without invented statistics', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [] }));
  render(<App />);
  expect(await screen.findByText('Nessuna versione pubblicata')).toBeInTheDocument();
  expect(screen.queryByText('1.200')).not.toBeInTheDocument();
});
it('shows an actionable error when the API is unavailable', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }));
  render(<App />);
  expect(await screen.findByRole('alert')).toHaveTextContent('503');
  expect(screen.getByRole('button', { name: 'Riprova' })).toBeInTheDocument();
});
it('labels demo evidence and renders missing values without turning them into zero', async () => {
  const release = { id: 'demo-id', title: 'Fixture', reference_period: '2025-01-01', is_demo: true,
    source_id: 'demo', upstream_url: 'https://example.org', license_url: 'https://example.org/license',
    retrieved_at: '2025-01-02T00:00:00Z', published_at: '2025-01-02T00:00:00Z',
    raw_sha256: 'a'.repeat(64), limitations: 'Valori inventati.' };
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => {
    if (url.includes('/observations')) return { items: [{territory_id: 1, territory_name: 'Alfa',
      territory_code: 'DEMO001', value: null, status: 'missing'}], next_cursor: null };
    if (url.endsWith('/v1/releases')) return [release];
    return [];
  }})));
  render(<App />);
  expect(await screen.findByText('Non disponibile')).toBeInTheDocument();
  expect(screen.getByText('Dimostrazione con dati inventati')).toBeInTheDocument();
});
