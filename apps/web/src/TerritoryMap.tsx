import { useRef, useState } from 'react';

export function TerritoryMap({ paths, name }: { paths: string[]; name: string }) {
  const [view, setView] = useState({ zoom: 1, x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number } | null>(null);
  function move(dx: number, dy: number) {
    setView((current) => ({
      ...current,
      x: Math.max(-320 * (current.zoom - 1), Math.min(320 * (current.zoom - 1), current.x + dx)),
      y: Math.max(-220 * (current.zoom - 1), Math.min(220 * (current.zoom - 1), current.y + dy)),
    }));
  }
  function zoom(factor: number) {
    setView((current) => {
      const next = Math.max(1, Math.min(8, current.zoom * factor));
      return {
        zoom: next,
        x: (current.x * (next - 1)) / (current.zoom - 1 || 1),
        y: (current.y * (next - 1)) / (current.zoom - 1 || 1),
      };
    });
  }
  const reset = () => setView({ zoom: 1, x: 0, y: 0 });
  return (
    <div className="territory-map">
      <div className="map-toolbar" role="group" aria-label="Controlli della mappa">
        <button type="button" onClick={() => zoom(2)} disabled={view.zoom === 8}>
          Ingrandisci +
        </button>
        <button type="button" onClick={() => zoom(0.5)} disabled={view.zoom === 1}>
          Riduci −
        </button>
        <button type="button" onClick={reset}>
          Vista completa
        </button>
        <span className="muted" aria-live="polite">
          Zoom {view.zoom}×
        </span>
      </div>
      <div
        className="map-canvas"
        role="group"
        aria-label={`Mappa di ${name}`}
        aria-describedby="map-instructions"
        tabIndex={0}
        onKeyDown={(event) => {
          const arrows: Record<string, [number, number]> = {
            ArrowLeft: [40, 0],
            ArrowRight: [-40, 0],
            ArrowUp: [0, 40],
            ArrowDown: [0, -40],
          };
          if (arrows[event.key]) {
            event.preventDefault();
            move(...arrows[event.key]);
          }
          if (['+', '=', '-', '0'].includes(event.key)) {
            event.preventDefault();
            if (event.key === '0') reset();
            else zoom(event.key === '-' ? 0.5 : 2);
          }
        }}
      >
        <svg
          viewBox="0 0 640 440"
          role="img"
          aria-label={`Confine di ${name}, nord in alto`}
          className={view.zoom > 1 ? 'map-zoomed' : undefined}
          onPointerDown={(event) => {
            if (view.zoom === 1 || !event.isPrimary || event.button !== 0) return;
            drag.current = { x: event.clientX, y: event.clientY };
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={(event) => {
            if (!drag.current) return;
            const width = event.currentTarget.getBoundingClientRect().width;
            move(
              ((event.clientX - drag.current.x) * 640) / width,
              ((event.clientY - drag.current.y) * 640) / width,
            );
            drag.current = { x: event.clientX, y: event.clientY };
          }}
          onPointerUp={() => {
            drag.current = null;
          }}
          onPointerCancel={() => {
            drag.current = null;
          }}
          onLostPointerCapture={() => {
            drag.current = null;
          }}
        >
          <g
            transform={`translate(${view.x} ${view.y}) translate(320 220) scale(${view.zoom}) translate(-320 -220)`}
          >
            {paths.map((path, index) => (
              <path key={index} d={path} fillRule="evenodd" vectorEffect="non-scaling-stroke" />
            ))}
          </g>
          <g className="map-north" aria-hidden="true">
            <text x="610" y="26" textAnchor="middle">
              N
            </text>
            <path d="M610 36 L604 49 L610 46 L616 49 Z" />
          </g>
        </svg>
      </div>
      <p id="map-instructions" className="muted">
        Nord in alto. Ingrandisci e trascina per esplorare; da tastiera usa +, − e le frecce. Premi
        0 per la vista completa.
      </p>
    </div>
  );
}
