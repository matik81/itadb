import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from './App';

afterEach(() => vi.unstubAllGlobals());
it('selects one M2 category, period and level and resets pagination', async () => {
  const coverage = [
    {
      period: '2024-01-01',
      series_code: 'pop',
      title: 'Popolazione totale',
      unit: 'persons',
      row_count: 21,
      territory_snapshot: '2024-01-01',
    },
    {
      period: '2021-12-31',
      series_code: 'hh',
      title: 'Famiglie totali',
      unit: 'households',
      row_count: 8032,
      territory_snapshot: '2021-12-31',
    },
  ];
  const fetchMock = vi.fn(async (url: string) => ({
    ok: true,
    json: async () => {
      if (url.endsWith('/v2/releases'))
        return [
          {
            id: 'm2',
            dataset_id: 'istat_m2',
            title: 'M2',
            series_code: 'pop',
            reference_period: '2024-01-01',
            published_at: '2026-09-23T00:00:00Z',
            retrieved_at: '2026-09-23T00:00:00Z',
            raw_sha256: 'a'.repeat(64),
            is_demo: false,
          },
        ];
      if (url.endsWith('/coverage')) return coverage;
      if (url.includes('/crosswalks')) return { items: [], next_cursor: null };
      if (url.includes('/observations'))
        return {
          items: [
            {
              territory_id: 8,
              territory_name: 'Regione di test',
              territory_code: '01',
              level: 'region',
              value: '1200',
              status: 'unflagged_upstream',
            },
          ],
          next_cursor: 8,
        };
      return [];
    },
  }));
  vi.stubGlobal('fetch', fetchMock);
  render(<App />);
  expect(await screen.findByText('Regione di test')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Successive →' }));
  await waitFor(() =>
    expect(fetchMock.mock.calls.some(([url]) => url.includes('after=8'))).toBe(true),
  );
  fireEvent.change(screen.getByLabelText('Periodo'), { target: { value: '2021-12-31' } });
  expect(await screen.findByText('Unità: famiglie')).toBeInTheDocument();
  await waitFor(() =>
    expect(
      fetchMock.mock.calls.some(
        ([url]) =>
          url.includes('series=hh') && url.includes('period=2021-12-31') && url.includes('after=0'),
      ),
    ).toBe(true),
  );
  fireEvent.change(screen.getByLabelText('Livello territoriale'), {
    target: { value: 'municipality' },
  });
  await waitFor(() =>
    expect(fetchMock.mock.calls.some(([url]) => url.includes('level=municipality'))).toBe(true),
  );
  expect(screen.getByText(/non sommare totali e dettagli/)).toBeInTheDocument();
});
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
  const release = {
    id: 'demo-id',
    title: 'Fixture',
    reference_period: '2025-01-01',
    is_demo: true,
    source_id: 'demo',
    series_code: 'population_total',
    upstream_url: 'https://example.org',
    license_url: 'https://example.org/license',
    retrieved_at: '2025-01-02T00:00:00Z',
    published_at: '2025-01-02T00:00:00Z',
    raw_sha256: 'a'.repeat(64),
    limitations: 'Valori inventati.',
  };
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => ({
      ok: true,
      json: async () => {
        if (url.includes('/observations'))
          return {
            items: [
              {
                territory_id: 1,
                territory_name: 'Alfa',
                territory_code: 'DEMO001',
                level: 'municipality',
                value: null,
                status: 'missing',
              },
            ],
            next_cursor: null,
          };
        if (url.endsWith('/v2/releases')) return [release];
        return [];
      },
    })),
  );
  render(<App />);
  expect(await screen.findByText('Non disponibile')).toBeInTheDocument();
  expect(screen.getByText('Dimostrazione con dati inventati')).toBeInTheDocument();
});

it('uses the release series and distinguishes national controls, upstream state and revisions', async () => {
  const fetchMock = vi.fn(async (url: string) => ({
    ok: true,
    json: async () => {
      if (url.endsWith('/v2/releases'))
        return [
          {
            id: 'revision-id',
            title: 'Popolazione residente',
            dataset_id: 'istat_population_regions',
            reference_period: '2024-01-01',
            territory_snapshot: '2024-01-01',
            is_demo: false,
            series_code: 'resident_population_jan1',
            source_id: 'istat',
            upstream_url: 'https://example.org/data',
            license_url: 'https://example.org/license',
            retrieved_at: '2026-09-23T00:00:00Z',
            published_at: '2026-09-23T01:00:00Z',
            upstream_last_update: '2026-03-31T08:03:43Z',
            upstream_published_at: null,
            supersedes_release_id: 'previous-id',
            revision_reason: 'Correzione del campione di test.',
            attribution: 'Fonte: ISTAT. Conteggi inventati per questo test.',
            raw_sha256: 'a'.repeat(64),
            contract_sha256: 'b'.repeat(64),
            limitations: 'Fixture di test.',
          },
        ];
      if (url.includes('/observations'))
        return {
          items: [
            {
              territory_id: 1,
              territory_name: 'Italia',
              territory_code: 'IT',
              level: 'country',
              value: '1000.000000',
              status: 'unflagged_upstream',
            },
          ],
          next_cursor: null,
        };
      if (url.endsWith('/artifacts'))
        return [{ kind: 'raw', sha256: 'a'.repeat(64), byte_size: 100 }];
      return [];
    },
  }));
  vi.stubGlobal('fetch', fetchMock);
  render(<App />);
  expect(await screen.findByText('Senza flag ISTAT')).toBeInTheDocument();
  expect(screen.getByText('Italia · totale')).toBeInTheDocument();
  expect(screen.getByText('Non accertata')).toBeInTheDocument();
  expect(screen.getByText('Correzione del campione di test.')).toBeInTheDocument();
  expect(screen.queryByText('Osservato')).not.toBeInTheDocument();
  expect(screen.queryByText('Dimostrazione con dati inventati')).not.toBeInTheDocument();
  expect(
    fetchMock.mock.calls.some(([url]) => url.includes('series=resident_population_jan1')),
  ).toBe(true);
  expect(screen.getByRole('link', { name: /provenienza precedente/ })).toHaveAttribute(
    'href',
    expect.stringContaining('/v2/releases/previous-id'),
  );
});
