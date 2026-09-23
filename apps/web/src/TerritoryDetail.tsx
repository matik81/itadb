import { useEffect, useRef, useState } from 'react';
import { get, type Boundary, type Coverage, type Observation, type Release } from './api';
import { TerritoryMap } from './TerritoryMap';
import { projectBoundary } from './territory-map';
import { Icon } from './Icons';

type Props = {
  observation: Observation;
  coverage: Coverage;
  release: Release;
  sourceName: string;
  onClose: () => void;
};
const number = new Intl.NumberFormat('it-IT', { maximumFractionDigits: 6 });
const levels = {
  country: 'Italia',
  region: 'Regione',
  province: 'Provincia',
  municipality: 'Comune',
};
const statuses = {
  demo: 'Dimostrativo',
  observed: 'Osservato',
  estimated: 'Stimato',
  missing: 'Mancante',
  suppressed: 'Riservato',
  unflagged_upstream: '—',
};

export function TerritoryDetail({ observation, coverage, release, sourceName, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [map, setMap] = useState<{ paths: string[]; download: string } | null>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const unit =
    { persons: 'persone', households: 'famiglie', dwellings: 'abitazioni' }[coverage.unit] ??
    coverage.unit;
  useEffect(() => {
    const element = dialog.current!;
    const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    element.showModal();
    document.body.style.overflow = 'hidden';
    return () => {
      element.close();
      document.body.style.overflow = previousOverflow;
      trigger?.focus({ preventScroll: true });
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    let download: string | undefined;
    setMap(null);
    setError('');
    get<Boundary>(
      `/v2/releases/${release.id}/territories/${observation.territory_id}/boundary`,
      controller.signal,
    )
      .then((boundary) => {
        if (controller.signal.aborted) return;
        if (
          boundary.release_id !== release.id ||
          boundary.territory_id !== observation.territory_id
        )
          throw new Error('Il confine ricevuto non corrisponde al territorio selezionato.');
        const paths = projectBoundary(boundary.geometry);
        const feature = {
          type: 'Feature',
          geometry: boundary.geometry,
          properties: {
            name: observation.territory_name,
            code: observation.territory_code,
            territory_id: observation.territory_id,
            release_id: release.id,
            snapshot: coverage.territory_snapshot,
            source: sourceName,
            license_url: release.license_url,
            attribution: release.attribution,
            simplification_degrees: boundary.simplification_degrees,
          },
        };
        download = URL.createObjectURL(
          new Blob([JSON.stringify(feature)], { type: 'application/geo+json' }),
        );
        setMap({ paths, download });
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(String(reason.message));
      });
    return () => {
      controller.abort();
      if (download) URL.revokeObjectURL(download);
    };
  }, [release, observation, coverage, sourceName, retry]);
  return (
    <dialog
      ref={dialog}
      className="territory-detail"
      aria-labelledby="territory-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className="territory-heading">
        <div>
          <p className="eyebrow">SCHEDA TERRITORIALE · {levels[observation.level]}</p>
          <h2 id="territory-title">{observation.territory_name}</h2>
          <p className="muted">
            Codice ISTAT {observation.territory_code} · Confini del {coverage.territory_snapshot}
          </p>
        </div>
        <button type="button" onClick={onClose} autoFocus>
          Chiudi scheda
        </button>
      </div>
      {release.is_demo && <p className="notice demo">Dimostrazione con dati inventati</p>}
      <div className="territory-content">
        <section
          className="boundary-panel"
          aria-label="Confine territoriale"
          aria-busy={!map && !error}
        >
          {!map && !error && (
            <p role="status" className="map-placeholder">
              Caricamento della mappa…
            </p>
          )}
          {error && (
            <div role="alert" className="notice error">
              <strong>Mappa non disponibile</strong>
              <p>{error}</p>
              <button type="button" onClick={() => setRetry((value) => value + 1)}>
                Riprova mappa
              </button>
            </div>
          )}
          {map && <TerritoryMap paths={map.paths} name={observation.territory_name} />}
          <p className="muted">
            Confine ISTAT semplificato per la consultazione. Province e regioni derivano dall’unione
            dei confini comunali.
          </p>
          {map && (
            <a
              className="boundary-download"
              href={map.download}
              download={`itadb-${observation.territory_code}-${coverage.territory_snapshot}.geojson`}
            >
              Scarica il confine in GeoJSON
            </a>
          )}
        </section>
        <section className="territory-statistic" aria-label="Dato selezionato">
          <p className="eyebrow">DATO SELEZIONATO</p>
          <h3>{coverage.title}</h3>
          <div className="territory-value-with-icon">
            <Icon kind={coverage.unit} className="metric-icon" />
            <p className="territory-value">
              {observation.value === null
                ? 'Non disponibile'
                : number.format(Number(observation.value))}
              <span>{unit}</span>
            </p>
          </div>
          <dl>
            <dt>Periodo del dato</dt>
            <dd>{coverage.period}</dd>
            <dt>Stato della fonte</dt>
            <dd>{statuses[observation.status]}</dd>
            <dt>Fonte</dt>
            <dd>
              <a href={release.upstream_url} target="_blank" rel="noreferrer">
                {sourceName} ↗
              </a>
            </dd>
            <dt>Licenza</dt>
            <dd>
              <a href={release.license_url} target="_blank" rel="noreferrer">
                Consulta la licenza ↗
              </a>
            </dd>
          </dl>
          <p className="muted">{release.attribution}</p>
        </section>
      </div>
      <div className="territory-limitations">
        <h3>Limiti di utilizzo</h3>
        <p>{release.limitations}</p>
        <p className="muted">
          Versione pubblicata: <code>{release.id}</code>
        </p>
      </div>
    </dialog>
  );
}
