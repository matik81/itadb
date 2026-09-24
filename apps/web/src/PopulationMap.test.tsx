import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PopulationMap } from './PopulationMap';
import { aggregateTerritories, type TerritoryLevel } from './population-map';
import { mapFixture } from './test-fixtures/population';

const context = {
  scale: vi.fn(),
  clearRect: vi.fn(),
  beginPath: vi.fn(),
  arc: vi.fn(),
  fill: vi.fn(),
  stroke: vi.fn(),
  save: vi.fn(),
  restore: vi.fn(),
  resetTransform: vi.fn(),
  isPointInPath: vi.fn().mockReturnValue(false),
};
beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
    context as unknown as CanvasRenderingContext2D,
  );
  vi.stubGlobal('PointerEvent', MouseEvent);
  vi.stubGlobal(
    'Path2D',
    class {
      constructor(public path: string) {}
    },
  );
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('Livelli della mappa', () => {
  it.each([
    ['region', 2, false, false],
    ['province', 3, true, false],
    ['municipality', 3, true, true],
  ] as const)(
    'mostra confini e cerchi coerenti in modalità %s',
    (level, circles, provinces, municipalities) => {
      const { container } = render(
        <PopulationMap
          data={mapFixture}
          level={level}
          territories={aggregateTerritories(mapFixture, level)}
          selected=""
          onSelect={vi.fn()}
        />,
      );
      expect(container.querySelector('.region-borders')).toBeInTheDocument();
      expect(!!container.querySelector('.province-borders')).toBe(provinces);
      expect(!!container.querySelector('.municipality-borders')).toBe(municipalities);
      expect(context.arc).toHaveBeenCalledTimes(circles);
    },
  );
  it.each(['region', 'province', 'municipality'] as TerritoryLevel[])(
    'seleziona il codice del livello %s dal cerchio',
    (level) => {
      const onSelect = vi.fn();
      const territories = aggregateTerritories(mapFixture, level).slice(0, 1);
      render(
        <PopulationMap
          data={mapFixture}
          level={level}
          territories={territories}
          selected=""
          onSelect={onSelect}
        />,
      );
      const canvas = screen.getByRole('img', { name: /Mappa della popolazione/ });
      Object.assign(canvas, { setPointerCapture: vi.fn() });
      fireEvent.pointerMove(canvas, { clientX: 600, clientY: 400 });
      expect(screen.getByText(territories[0].name)).toBeInTheDocument();
      expect(screen.getByText(`${territories[0].persons} individui`)).toBeInTheDocument();
      fireEvent.pointerDown(canvas, { clientX: 600, clientY: 400 });
      fireEvent.pointerUp(canvas, { clientX: 600, clientY: 400 });
      expect(onSelect).toHaveBeenCalledWith(territories[0].code);
    },
  );
  it('evidenzia il confine selezionato e mantiene zoom e navigazione da tastiera', () => {
    const { container } = render(
      <PopulationMap
        data={mapFixture}
        level="province"
        territories={aggregateTerritories(mapFixture, 'province')}
        selected="900"
        onSelect={vi.fn()}
      />,
    );
    expect(container.querySelector('.selected-boundary')).toHaveAttribute('d');
    const geography = container.querySelector('.map-geography g')!;
    const initial = geography.getAttribute('transform');
    const canvas = screen.getByRole('img', { name: /Mappa della popolazione/ });
    fireEvent.keyDown(canvas, { key: '+' });
    expect(geography.getAttribute('transform')).not.toBe(initial);
    const zoomed = geography.getAttribute('transform');
    fireEvent.keyDown(canvas, { key: 'ArrowRight' });
    expect(geography.getAttribute('transform')).not.toBe(zoomed);
  });
  it.each([false, true])(
    'conserva zoom e posizione cambiando livello, con selezione: %s',
    (hasSelection) => {
      const map = (level: TerritoryLevel, selected: string) => (
        <PopulationMap
          data={mapFixture}
          level={level}
          territories={aggregateTerritories(mapFixture, level)}
          selected={selected}
          onSelect={vi.fn()}
        />
      );
      const { container, rerender } = render(map('municipality', hasSelection ? '900001' : ''));
      const canvas = screen.getByRole('img', { name: /Mappa della popolazione/ });
      fireEvent.keyDown(canvas, { key: '+' });
      fireEvent.keyDown(canvas, { key: 'ArrowRight' });
      fireEvent.keyDown(canvas, { key: 'ArrowDown' });
      const transform = container.querySelector('.map-geography g')!.getAttribute('transform');
      for (const [level, code] of [
        ['province', '900'],
        ['region', '90'],
        ['municipality', ''],
        ['province', ''],
      ] as const) {
        rerender(map(level, hasSelection ? code : ''));
        expect(screen.getByRole('img', { name: /Mappa della popolazione/ })).toBe(canvas);
        expect(container.querySelector('.map-geography g')).toHaveAttribute('transform', transform);
      }
      // An explicit selection within the current mode still centers the territory.
      rerender(map('province', '910'));
      expect(container.querySelector('.map-geography g')!.getAttribute('transform')).not.toBe(
        transform,
      );
    },
  );
  it('seleziona anche il confine e non seleziona al termine di un trascinamento', () => {
    const onSelect = vi.fn();
    context.isPointInPath.mockReturnValueOnce(true);
    render(
      <PopulationMap
        data={mapFixture}
        level="region"
        territories={aggregateTerritories(mapFixture, 'region').slice(0, 1)}
        selected=""
        onSelect={onSelect}
      />,
    );
    const canvas = screen.getByRole('img', { name: /Mappa della popolazione/ });
    Object.assign(canvas, { setPointerCapture: vi.fn() });
    fireEvent.pointerDown(canvas, { clientX: 100, clientY: 100 });
    fireEvent.pointerUp(canvas, { clientX: 100, clientY: 100 });
    expect(onSelect).toHaveBeenCalledWith('90');
    expect(context.isPointInPath).toHaveBeenCalledWith(
      expect.anything(),
      expect.any(Number),
      expect.any(Number),
      'evenodd',
    );
    onSelect.mockClear();
    fireEvent.pointerDown(canvas, { clientX: 600, clientY: 400 });
    fireEvent.pointerMove(canvas, { clientX: 630, clientY: 430 });
    fireEvent.pointerUp(canvas, { clientX: 630, clientY: 430 });
    expect(onSelect).not.toHaveBeenCalled();
  });
});
