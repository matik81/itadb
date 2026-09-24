import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { mapFixture } from './test-fixtures/population';
import type { MapTerritory } from './population-map';

vi.mock('./PopulationMap', () => ({
  PopulationMap: ({
    level,
    territories,
    selected,
  }: {
    level: string;
    territories: MapTerritory[];
    selected: string;
  }) => (
    <div
      aria-label="Mappa territoriale"
      data-testid="map"
      data-level={level}
      data-selected={selected}
      data-codes={territories.map((t) => t.code).join(',')}
    />
  ),
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
let expandedMap = false;
let failDistribution = false;
beforeEach(() => {
  window.location.hash = '';
  requests = [];
  failPersons = false;
  expandedMap = false;
  failDistribution = false;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string) => {
      const url = new URL(input);
      requests.push(url.pathname + url.search);
      let data: unknown;
      if (url.pathname === '/v3/populations') data = [snapshot];
      else if (url.pathname.endsWith('/map'))
        data = expandedMap
          ? mapFixture
          : {
              regions: [
                {
                  code: '90',
                  name: 'Regione inventata',
                  geometry: null,
                  persons: 15,
                  households: 5,
                },
              ],
              municipalities: [municipality],
              provinces: [],
              municipality_boundaries: [],
              representation: 'municipality_aggregates',
              individual_coordinates_available: false,
            };
      else if (url.pathname.endsWith('/distributions')) {
        if (failDistribution) return { ok: false, status: 503 };
        data = [
          { age: 40, sex: 'M', persons: 8 },
          { age: 40, sex: 'F', persons: 7 },
        ];
      } else if (url.pathname.endsWith('/validation'))
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

describe('Modalità territoriali di Esplora', () => {
  beforeEach(() => {
    expandedMap = true;
  });
  const distributionPanel = () =>
    screen.getByRole('complementary', { name: 'Distribuzione della popolazione' });
  const latestDistribution = () =>
    new URL(requests.filter((r) => r.includes('/distributions?')).at(-1)!, 'http://localhost')
      .searchParams;

  it('aggrega province e regioni, conserva i filtri individuali e rimuove i filtri figli', async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: /Comune 900001/ }));
    const mapElement = screen.getByTestId('map');
    fireEvent.change(screen.getByLabelText('Sesso'), { target: { value: 'F' } });
    fireEvent.click(screen.getByRole('radio', { name: 'Province' }));
    expect(screen.getByTestId('map')).toBe(mapElement);
    const selection = screen.getByRole('region', { name: 'Territorio selezionato' });
    expect(within(selection).getByRole('heading', { name: 'Provincia 900' })).toBeInTheDocument();
    expect(within(selection).getByText('300')).toBeInTheDocument();
    expect(within(selection).getByText('30')).toBeInTheDocument();
    expect(screen.getByLabelText('Cerca una provincia')).toHaveValue('');
    expect(screen.queryByLabelText('Provincia', { selector: 'select' })).not.toBeInTheDocument();
    expect(screen.getByTestId('map')).toHaveAttribute('data-codes', '900,901');
    await waitFor(() => expect(latestDistribution().get('province_code')).toBe('900'));
    expect(latestDistribution().has('municipality_code')).toBe(false);
    expect(latestDistribution().get('sex')).toBe('F');
    fireEvent.click(screen.getByRole('radio', { name: 'Regioni' }));
    expect(screen.getByTestId('map')).toBe(mapElement);
    expect(within(selection).getByRole('heading', { name: 'Regione 90' })).toBeInTheDocument();
    expect(within(selection).getByText('600')).toBeInTheDocument();
    expect(screen.queryByLabelText('Regione', { selector: 'select' })).not.toBeInTheDocument();
    expect(screen.getByTestId('map')).toHaveAttribute('data-codes', '90,91');
    await waitFor(() => expect(latestDistribution().has('province_code')).toBe(false));
    expect(latestDistribution().get('region_code')).toBe('90');
    expect(latestDistribution().get('sex')).toBe('F');
    expect(
      within(distributionPanel()).getByRole('heading', { name: /Regione 90/ }),
    ).toBeInTheDocument();
  });

  it('percorre regione, provincia e comune e restringe ricerca e mappa ai figli', async () => {
    render(<App />);
    await screen.findByRole('button', { name: /Comune 900001/ });
    fireEvent.click(screen.getByRole('radio', { name: 'Regioni' }));
    fireEvent.change(screen.getByLabelText('Cerca una regione'), { target: { value: ' 90 ' } });
    fireEvent.click(screen.getByRole('button', { name: /Regione 90/ }));
    fireEvent.click(screen.getByRole('button', { name: /Esplora le province/ }));
    expect(screen.getByRole('radio', { name: 'Province' })).toBeChecked();
    expect(screen.getByLabelText('Regione', { selector: 'select' })).toHaveValue('90');
    expect(screen.queryByRole('button', { name: /Provincia 910/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Provincia 900/ }));
    fireEvent.click(screen.getByRole('button', { name: /Esplora i comuni/ }));
    expect(screen.getByLabelText('Provincia', { selector: 'select' })).toHaveValue('900');
    expect(screen.getByTestId('map')).toHaveAttribute('data-codes', '900001,900002');
    expect(screen.queryByRole('button', { name: /Comune 901001/ })).not.toBeInTheDocument();
    // A municipality without coordinates remains searchable and selectable.
    fireEvent.click(screen.getByRole('button', { name: /Comune 900002/ }));
    expect(screen.getByTestId('map')).toHaveAttribute('data-selected', '900002');
    fireEvent.change(screen.getByLabelText('Regione', { selector: 'select' }), {
      target: { value: '91' },
    });
    expect(screen.getByLabelText('Provincia', { selector: 'select' })).toHaveValue('');
    expect(screen.getByTestId('map')).toHaveAttribute('data-selected', '');
    expect(screen.getByTestId('map')).toHaveAttribute('data-codes', '910001');
    fireEvent.click(screen.getByRole('button', { name: /Tutta Italia/ }));
    expect(screen.getByTestId('map')).toHaveAttribute('data-codes', '900001,900002,901001,910001');
    expect(
      within(distributionPanel()).getByRole('heading', { name: /Italia/ }),
    ).toBeInTheDocument();
  });

  it('gestisce ricerca vuota, errore e riprova anche nella selezione provinciale', async () => {
    render(<App />);
    await screen.findByRole('button', { name: /Comune 900001/ });
    fireEvent.click(screen.getByRole('radio', { name: 'Province' }));
    fireEvent.change(screen.getByLabelText('Cerca una provincia'), {
      target: { value: 'inesistente' },
    });
    expect(screen.getByText('Nessuna provincia trovata.')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Cerca una provincia'), { target: { value: '910' } });
    failDistribution = true;
    fireEvent.click(screen.getByRole('button', { name: /Provincia 910/ }));
    expect(await within(distributionPanel()).findByRole('alert')).toHaveTextContent('503');
    expect(
      within(distributionPanel()).queryByRole('img', { name: /Distribuzione per età/ }),
    ).not.toBeInTheDocument();
    failDistribution = false;
    fireEvent.click(within(distributionPanel()).getByRole('button', { name: 'Riprova' }));
    expect(
      await within(distributionPanel()).findByRole('img', {
        name: /Distribuzione per età di Provincia 910/,
      }),
    ).toBeInTheDocument();
    expect(latestDistribution().get('province_code')).toBe('910');
  });

  it('chiude i record passando a un aggregato e non ripristina selezioni comunali nascoste', async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: /Comune 900001/ }));
    fireEvent.click(screen.getByRole('button', { name: /Esplora i record/ }));
    expect(
      await screen.findByRole('region', { name: 'Record di Comune 900001' }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: 'Regioni' }));
    expect(
      screen.queryByRole('region', { name: 'Record di Comune 900001' }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: 'Comuni' }));
    expect(
      screen.queryByRole('region', { name: 'Territorio selezionato' }),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText('Provincia', { selector: 'select' })).toHaveValue('');
    expect(screen.getByTestId('map')).toHaveAttribute('data-codes', '900001,900002,901001');
  });
});
