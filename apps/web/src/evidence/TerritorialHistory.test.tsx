import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { TerritorialHistory } from './TerritorialHistory';

afterEach(() => vi.unstubAllGlobals());
it('sorts and selects history filters on the full API result, resetting pagination', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      items: [
        {
          id: 9,
          effective_date: '2021-01-01',
          kind: 'merger',
          description: 'Fusione inventata',
          from_code: 'A',
          to_code: 'B',
          weight_basis: 'exact',
        },
      ],
      next_cursor: 9,
    }),
  });
  vi.stubGlobal('fetch', fetchMock);
  render(<TerritorialHistory releaseId="fixture" />);
  expect(await screen.findByText('Fusione inventata ↗')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Altre corrispondenze →' }));
  await waitFor(() => expect(fetchMock.mock.calls.at(-1)?.[0]).toContain('after=9'));
  fireEvent.click(screen.getByRole('button', { name: 'Ordina decorrenza in ordine decrescente' }));
  await waitFor(() => {
    expect(fetchMock.mock.calls.at(-1)?.[0]).toContain('direction=desc');
    expect(fetchMock.mock.calls.at(-1)?.[0]).toContain('after=0');
  });
  fireEvent.change(screen.getByLabelText('Tipo di variazione'), { target: { value: 'split' } });
  fireEvent.change(screen.getByLabelText('Utilizzo delle corrispondenze'), {
    target: { value: 'structural' },
  });
  await waitFor(() => {
    expect(fetchMock.mock.calls.at(-1)?.[0]).toContain('kind=split');
    expect(fetchMock.mock.calls.at(-1)?.[0]).toContain('weight_basis=structural');
  });
  fireEvent.click(screen.getByRole('button', { name: 'Azzera filtri storia' }));
  await waitFor(() => expect(fetchMock.mock.calls.at(-1)?.[0]).not.toContain('kind='));
});
