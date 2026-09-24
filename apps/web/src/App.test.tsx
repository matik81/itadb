import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';

vi.mock('./PopulationMap', () => ({
  PopulationMap: () => <div aria-label="Mappa territoriale" />,
}));
const snapshot = {
  id: 1,
  run_id: 'a'.repeat(64),
  manifest_sha256: 'b'.repeat(64),
  reference_date: '2025-01-01',
  household_reference: '2024-12-31',
  persons: 15,
  households: 5,
  municipalities: 1,
  located_persons: 0,
  is_fixture: true,
  data_kind: 'synthetic',
  published_at: '2026-01-01T12:00:00Z',
};
const evidence = {
  ...snapshot,
  report: { unassigned_adults: 1 },
  publication_checks: { database_constraints: true },
  provenance: {
    model: { seed: 1701 },
    country_labels: { '100': 'Italia', '201': 'Albania' },
    algorithm: 'ordered-population/1.0.0',
    sources: [
      {
        group: 'national',
        name: 'population_zip',
        url: 'https://example.org/posas.zip',
        sha256: 'c'.repeat(64),
      },
    ],
  },
};
const municipality = {
  code: '900001',
  name: 'Comune inventato',
  province_code: '900',
  province_name: 'Provincia inventata',
  region_code: '90',
  region_name: 'Regione inventata',
  persons: 15,
  households: 5,
  latitude: null,
  longitude: null,
  location_kind: 'municipality_representative_point',
};
const person = {
  person_id: 1,
  household_id: 1,
  municipality_code: '900001',
  sex: 'M',
  birth_year: 1984,
  birth_year_upper_bound: null,
  age: 40,
  age_is_lower_bound: false,
  citizenship_code: '100',
  reference_adult: true,
  data_kind: 'synthetic',
};
let requests: string[];
let failPersons = false;
beforeEach(() => {
  window.location.hash = '';
  requests = [];
  failPersons = false;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string) => {
      const url = new URL(input);
      requests.push(url.pathname + url.search);
      let data: unknown;
      if (url.pathname === '/v3/populations') data = [snapshot];
      else if (url.pathname.endsWith('/map'))
        data = {
          regions: [
            { code: '90', name: 'Regione inventata', geometry: null, persons: 15, households: 5 },
          ],
          municipalities: [municipality],
          provinces: [],
          municipality_boundaries: [],
          representation: 'municipality_aggregates',
          individual_coordinates_available: false,
        };
      else if (url.pathname.endsWith('/distributions'))
        data = [
          { age: 40, sex: 'M', persons: 8 },
          { age: 40, sex: 'F', persons: 7 },
        ];
      else if (url.pathname.endsWith('/validation'))
        data = [
          {
            kind: 'sex_age',
            cells: 202,
            expected: 15,
            actual: 15,
            mismatched_cells: 0,
            max_absolute_error: 0,
          },
        ];
      else if (url.pathname.endsWith('/comparison'))
        data = [{ kind: 'sex_age', sex: 'M', category: 40, expected: 8, actual: 8 }];
      else if (url.pathname.endsWith('/persons')) {
        if (failPersons) return { ok: false, status: 503 };
        data = { items: [person], next_cursor: url.searchParams.get('after') === '0' ? 1 : null };
      } else if (url.pathname.endsWith('/households/1'))
        data = {
          household_id: 1,
          municipality_code: '900001',
          size: 1,
          data_kind: 'synthetic',
          members: [person],
        };
      else if (url.pathname.endsWith('/households'))
        data = {
          items: [
            { household_id: 1, municipality_code: '900001', size: 1, data_kind: 'synthetic' },
          ],
          next_cursor: null,
        };
      else data = evidence;
      return { ok: true, json: async () => data };
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

async function selectTown() {
  await screen.findByRole('button', { name: /Comune inventato/ });
  fireEvent.click(screen.getByRole('button', { name: /Comune inventato/ }));
  fireEvent.click(screen.getByRole('button', { name: /Esplora i record/ }));
  await screen.findByRole('button', { name: 'Successivi →' });
}

describe('Prodotto popolazione', () => {
  it('usa le API della popolazione e distingue esplicitamente la fixture', async () => {
    render(<App />);
    expect(await screen.findByText(/Fixture inventata: dati esclusivamente/)).toBeInTheDocument();
    expect(requests.every((path) => path.startsWith('/v3/populations'))).toBe(true);
    expect(screen.getByRole('link', { name: 'Metodo e verifiche' })).toBeInTheDocument();
  });
  it('naviga individui e famiglia, applica filtri e azzera la paginazione', async () => {
    render(<App />);
    await selectTown();
    const panel = screen.getByRole('region', { name: 'Record di Comune inventato' });
    fireEvent.click(within(panel).getByRole('button', { name: '1 ↗' }));
    expect(await screen.findByRole('complementary', { name: 'Famiglia 1' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Successivi →' }));
    await waitFor(() =>
      expect(requests.some((p) => p.includes('/persons?') && p.includes('after=1'))).toBe(true),
    );
    fireEvent.change(screen.getByLabelText('Cittadinanza'), { target: { value: '201' } });
    await waitFor(() =>
      expect(
        requests.some(
          (p) =>
            p.includes('/persons?') && p.includes('citizenship_code=201') && p.includes('after=0'),
        ),
      ).toBe(true),
    );
  });
  it('ordina attraverso il backend, non soltanto la pagina corrente', async () => {
    render(<App />);
    await selectTown();
    fireEvent.click(screen.getByRole('button', { name: 'Ordina età in ordine crescente' }));
    await waitFor(() =>
      expect(
        requests.some(
          (p) => p.includes('/persons?') && p.includes('sort_by=age') && p.includes('after=0'),
        ),
      ).toBe(true),
    );
  });
  it('mostra fonti, ipotesi e conteggi di verifica per lo snapshot selezionato', async () => {
    render(<App />);
    await selectTown();
    window.location.hash = '#metodo';
    fireEvent(window, new HashChangeEvent('hashchange'));
    expect(await screen.findByRole('heading', { name: 'I conteggi tornano?' })).toBeInTheDocument();
    expect(await screen.findByText('202')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /Popolazione per comune, sesso ed età/ }),
    ).toHaveAttribute('href', 'https://example.org/posas.zip');
    expect(
      screen.getByText(/Composizione casuale rispetto a età e cittadinanza/),
    ).toBeInTheDocument();
  });
  it('mostra errori e riprova senza sostituire record con dati inventati', async () => {
    failPersons = true;
    render(<App />);
    await screen.findByRole('button', { name: /Comune inventato/ });
    fireEvent.click(screen.getByRole('button', { name: /Comune inventato/ }));
    fireEvent.click(screen.getByRole('button', { name: /Esplora i record/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('503');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    failPersons = false;
    fireEvent.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Riprova' }));
    expect(await screen.findByRole('table')).toBeInTheDocument();
  });
  it('gestisce un catalogo vuoto senza mostrare una popolazione di esempio', async () => {
    vi.mocked(fetch).mockResolvedValue({ ok: true, json: async () => [] } as Response);
    render(<App />);
    expect(
      await screen.findByRole('heading', { name: 'Nessuna popolazione disponibile' }),
    ).toBeInTheDocument();
    expect(screen.queryByText('VERIFICATO')).not.toBeInTheDocument();
  });
});
