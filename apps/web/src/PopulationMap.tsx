import { useEffect, useMemo, useRef, useState } from 'react';
import { mercator, geometryPath } from './population-map';
import { number, type PopulationMapData, type Municipality } from './population-api';

type View = { x: number; y: number; scale: number };
const center = mercator(12.5, 42);
export function PopulationMap({
  data,
  selected,
  onSelect,
}: {
  data: PopulationMapData | null;
  selected: string;
  onSelect: (code: string) => void;
}) {
  const wrapper = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState({ width: 1200, height: 800 });
  const [view, setView] = useState<View>({ x: 0, y: 0, scale: 1 });
  const [hover, setHover] = useState<{ item: Municipality; x: number; y: number } | null>(null);
  const drag = useRef<{ x: number; y: number; origin: View; moved: boolean } | null>(null);
  const base = Math.min(size.width / 0.35, size.height / 0.32) * 0.87;
  const scale = base * view.scale;
  const ox = size.width / 2 + view.x - center[0] * scale;
  const oy = size.height / 2 + view.y - center[1] * scale;
  const points = useMemo(
    () =>
      (data?.municipalities ?? [])
        .filter((m) => m.latitude !== null && m.longitude !== null)
        .map((item) => ({ item, point: mercator(item.longitude!, item.latitude!) })),
    [data],
  );
  const regions = useMemo(
    () =>
      (data?.regions ?? []).map((region) => ({ ...region, path: geometryPath(region.geometry) })),
    [data],
  );
  useEffect(() => {
    if (!wrapper.current || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(([entry]) =>
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height }),
    );
    observer.observe(wrapper.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const item = points.find((p) => p.item.code === selected);
    if (!item) return;
    const nextScale = 4;
    setView({
      scale: nextScale,
      x: (center[0] - item.point[0]) * base * nextScale,
      y: (center[1] - item.point[1]) * base * nextScale,
    });
  }, [selected, points, base]);
  useEffect(() => {
    const element = canvas.current;
    if (!element) return;
    const ctx = element.getContext('2d');
    if (!ctx) return;
    const ratio = window.devicePixelRatio || 1;
    element.width = size.width * ratio;
    element.height = size.height * ratio;
    ctx.scale(ratio, ratio);
    ctx.clearRect(0, 0, size.width, size.height);
    for (const { item, point } of points) {
      const x = ox + point[0] * scale,
        y = oy + point[1] * scale;
      if (x < -20 || x > size.width + 20 || y < -20 || y > size.height + 20) continue;
      const active = item.code === selected;
      const radius = active
        ? 6
        : Math.min(4.5, 0.7 + Math.log10(Math.max(1, item.persons)) * 0.42) *
          Math.min(1.6, Math.sqrt(view.scale));
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fillStyle = active ? '#ffcf78' : 'rgba(88,225,194,0.6)';
      ctx.fill();
      if (active) {
        ctx.beginPath();
        ctx.arc(x, y, 13, 0, Math.PI * 2);
        ctx.strokeStyle = '#ffcf78';
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    }
  }, [points, selected, ox, oy, scale, size, view.scale]);
  function nearest(x: number, y: number) {
    let found: Municipality | null = null,
      distance = 12;
    for (const { item, point } of points) {
      const d = Math.hypot(ox + point[0] * scale - x, oy + point[1] * scale - y);
      if (d < distance) {
        found = item;
        distance = d;
      }
    }
    return found;
  }
  function zoom(factor: number, x = size.width / 2, y = size.height / 2) {
    setView((v) => {
      const next = Math.min(45, Math.max(0.7, v.scale * factor));
      const f = next / v.scale;
      return {
        scale: next,
        x: (v.x - x + size.width / 2) * f + x - size.width / 2,
        y: (v.y - y + size.height / 2) * f + y - size.height / 2,
      };
    });
  }
  return (
    <div className="population-map" ref={wrapper}>
      <svg className="map-geography" width="100%" height="100%" aria-hidden="true">
        <defs>
          <pattern id="radar-grid" width="56" height="56" patternUnits="userSpaceOnUse">
            <path d="M56 0H0V56" fill="none" stroke="#183332" strokeWidth=".5" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#radar-grid)" />
        <g transform={`translate(${ox},${oy}) scale(${scale})`}>
          {regions.map((r) => (
            <path
              key={r.code}
              d={r.path}
              fill="#102321"
              fillRule="evenodd"
              stroke="#427169"
              strokeWidth={0.7 / scale}
            />
          ))}
        </g>
      </svg>
      <canvas
        ref={canvas}
        className="map-points"
        style={{ width: size.width, height: size.height }}
        tabIndex={0}
        role="img"
        aria-label="Mappa della popolazione per comune. I punti rappresentano comuni, non residenze individuali. Usa frecce per spostarti, più e meno per lo zoom. I comuni sono selezionabili anche dalla ricerca."
        onKeyDown={(e) => {
          if (e.key === '+' || e.key === '=') zoom(1.3);
          else if (e.key === '-') zoom(1 / 1.3);
          else if (e.key === 'Home') setView({ x: 0, y: 0, scale: 1 });
          else if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) {
            e.preventDefault();
            setView((v) => ({
              ...v,
              x: v.x + (e.key === 'ArrowLeft' ? 40 : e.key === 'ArrowRight' ? -40 : 0),
              y: v.y + (e.key === 'ArrowUp' ? 40 : e.key === 'ArrowDown' ? -40 : 0),
            }));
          }
        }}
        onWheel={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          zoom(e.deltaY < 0 ? 1.13 : 1 / 1.13, e.clientX - r.left, e.clientY - r.top);
        }}
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId);
          drag.current = { x: e.clientX, y: e.clientY, origin: view, moved: false };
          setHover(null);
        }}
        onPointerMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          if (drag.current) {
            const dx = e.clientX - drag.current.x,
              dy = e.clientY - drag.current.y;
            if (Math.hypot(dx, dy) > 4) drag.current.moved = true;
            setView({
              ...drag.current.origin,
              x: drag.current.origin.x + dx,
              y: drag.current.origin.y + dy,
            });
          } else {
            const item = nearest(e.clientX - r.left, e.clientY - r.top);
            setHover(item ? { item, x: e.clientX - r.left, y: e.clientY - r.top } : null);
          }
        }}
        onPointerUp={(e) => {
          const current = drag.current;
          drag.current = null;
          if (current && !current.moved) {
            const r = e.currentTarget.getBoundingClientRect();
            const item = nearest(e.clientX - r.left, e.clientY - r.top);
            if (item) onSelect(item.code);
          }
        }}
        onPointerCancel={() => {
          drag.current = null;
        }}
        onPointerLeave={() => setHover(null)}
      />
      {hover && (
        <div
          className="map-tooltip"
          style={{ left: Math.min(hover.x + 14, size.width - 210), top: hover.y + 14 }}
        >
          <strong>{hover.item.name}</strong>
          <span>{number.format(hover.item.persons)} individui virtuali</span>
        </div>
      )}
      <div className="map-controls" aria-label="Controlli della mappa">
        <span className="north-mark">
          N<br />↑
        </span>
        <button aria-label="Aumenta zoom" onClick={() => zoom(1.5)}>
          +
        </button>
        <button aria-label="Riduci zoom" onClick={() => zoom(1 / 1.5)}>
          −
        </button>
        <button aria-label="Mostra tutta Italia" onClick={() => setView({ x: 0, y: 0, scale: 1 })}>
          ⌖
        </button>
      </div>
      <div className="map-legend">
        <span className="signal-dot" /> Distribuzione per comune{' '}
        <span className="legend-separator">/</span> Coordinate individuali: non ancora integrate
      </div>
    </div>
  );
}
