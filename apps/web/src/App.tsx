import { useEffect, useState } from 'react';
import {
  API_BASE,
  get,
  type Artifact,
  type Page,
  type Quality,
  type Release,
  type Source,
  type Coverage,
} from './api';
import { TerritorialHistory } from './TerritorialHistory';

const number = new Intl.NumberFormat('it-IT', { maximumFractionDigits: 6 });
const dateTime = (value: string) => new Date(value).toLocaleString('it-IT');

export function App() {
  const [releases, setReleases] = useState<Release[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [selected, setSelected] = useState('');
  const [page, setPage] = useState<Page | null>(null);
  const [quality, setQuality] = useState<Quality[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [after, setAfter] = useState(0);
  const [error, setError] = useState('');
  const [evidenceError, setEvidenceError] = useState('');
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const [coverage, setCoverage] = useState<Coverage[]>([]);
  const [selection, setSelection] = useState('');
  const [level, setLevel] = useState('region');
  const release = releases.find((item) => item.id === selected);
  const isM2 = release?.dataset_id === 'istat_m2';
  const chosen = coverage.find((item) => `${item.period}|${item.series_code}` === selection);
  const unit =
    { persons: 'persone', households: 'famiglie', dwellings: 'abitazioni' }[
      chosen?.unit ?? 'persons'
    ] ?? chosen?.unit;

  useEffect(() => {
    setCoverage([]);
    setSelection('');
    setQuality([]);
    setArtifacts([]);
    setEvidenceError('');
    if (!release) return;
    const controller = new AbortController();
    Promise.all([
      isM2
        ? get<Coverage[]>(`/v2/releases/${release.id}/coverage`, controller.signal)
        : Promise.resolve([]),
      get<Quality[]>(`/v2/releases/${release.id}/quality`, controller.signal),
      get<Artifact[]>(`/v2/releases/${release.id}/artifacts`, controller.signal),
    ])
      .then(([items, checks, evidenceFiles]) => {
        if (controller.signal.aborted) return;
        setCoverage(items);
        setQuality(checks);
        setArtifacts(evidenceFiles);
        const initial =
          items.find(
            (item) =>
              item.series_code === release.series_code && item.period === release.reference_period,
          ) ?? items[0];
        setSelection(initial ? `${initial.period}|${initial.series_code}` : '');
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setEvidenceError(String(reason.message));
      });
    return () => controller.abort();
  }, [release, isM2, retry]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    Promise.all([
      get<Release[]>('/v2/releases', controller.signal),
      get<Source[]>('/v2/sources', controller.signal),
    ])
      .then(([items, registered]) => {
        setReleases(items);
        setSources(registered);
        setSelected(items[0]?.id ?? '');
        setAfter(0);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(String(reason.message));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [retry]);

  useEffect(() => {
    if (!release || (isM2 && !chosen)) return;
    const controller = new AbortController();
    setPage(null);
    setLoading(true);
    setError('');
    const query = new URLSearchParams({
      release_id: release.id,
      period: chosen?.period ?? release.reference_period,
      series: chosen?.series_code ?? release.series_code,
      after: String(after),
      limit: '100',
    });
    if (isM2) query.set('level', level);
    get<Page>(`/v2/observations?${query}`, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        setPage(result);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(String(reason.message));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [release, after, retry, chosen, isM2, level]);

  return (
    <>
      <a className="skip" href="#content">
        Vai ai dati
      </a>
      <header className="topbar">
        <a className="brand" href="/">
          ita<span>db</span>
          <small>DATI · TERRITORI · SOCIETÀ</small>
        </a>
        <nav aria-label="Navigazione principale">
          <a className="active" href="#content">
            Esplora
          </a>
          <a href={`${API_BASE}/docs`}>API</a>
          <a href="https://github.com/matik81/itadb">GitHub ↗</a>
        </nav>
      </header>
      <main id="content">
        <div className="heading">
          <div>
            <p className="eyebrow">OSSERVATORIO TERRITORIALE / V0.1</p>
            <h1>Ogni dato, la sua fonte.</h1>
            <p className="intro">Consulta le evidenze pubblicate e verifica da dove provengono.</p>
          </div>
          <span className="phase">
            01 <span>Dati aggregati</span>
          </span>
        </div>
        {(error || evidenceError) && (
          <div role="alert" className="notice error">
            <strong>Dati non disponibili</strong>
            <p>{error || evidenceError}</p>
            <button onClick={() => setRetry((value) => value + 1)}>Riprova</button>
          </div>
        )}
        <section className="controls" aria-label="Selezione dati">
          <label htmlFor="release">Versione pubblicata</label>
          <select
            id="release"
            value={selected}
            disabled={!releases.length}
            onChange={(event) => {
              setSelected(event.target.value);
              setAfter(0);
              setCoverage([]);
              setSelection('');
              setPage(null);
              setLevel('region');
            }}
          >
            <option value="" disabled>
              Seleziona una versione
            </option>
            {releases.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title} · {dateTime(item.published_at)} · {item.id.slice(0, 8)}
              </option>
            ))}
          </select>
          {release && (
            <span className="period">
              Riferimento <strong>{chosen?.period ?? release.reference_period}</strong>
            </span>
          )}
        </section>
        {isM2 && (
          <section className="controls m2-controls" aria-label="Copertura demografica">
            <div>
              <label htmlFor="period">Periodo</label>
              <select
                id="period"
                value={chosen?.period ?? ''}
                onChange={(event) => {
                  const next = coverage.find((item) => item.period === event.target.value);
                  setSelection(next ? `${next.period}|${next.series_code}` : '');
                  setAfter(0);
                }}
              >
                {[...new Set(coverage.map((item) => item.period))].sort().map((period) => (
                  <option key={period}>{period}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="series">Indicatore e categoria</label>
              <select
                id="series"
                aria-describedby="selection-description"
                value={selection}
                onChange={(event) => {
                  setSelection(event.target.value);
                  setAfter(0);
                }}
              >
                {coverage
                  .filter((item) => item.period === chosen?.period)
                  .sort((left, right) =>
                    left.title.localeCompare(right.title, 'it', { numeric: true }),
                  )
                  .map((item) => (
                    <option key={item.series_code} value={`${item.period}|${item.series_code}`}>
                      {item.title}
                    </option>
                  ))}
              </select>
            </div>
            <div>
              <label htmlFor="level">Livello territoriale</label>
              <select
                id="level"
                value={level}
                onChange={(event) => {
                  setLevel(event.target.value);
                  setAfter(0);
                }}
              >
                <option value="country">Italia · totale di controllo</option>
                <option value="region">Regioni</option>
                <option value="province">Province</option>
                <option value="municipality">Comuni</option>
              </select>
            </div>
            <p className="muted" id="selection-description">
              <strong className="selection-title">{chosen?.title}</strong>
              {chosen?.row_count} osservazioni su tutti i livelli coperti · Confini del{' '}
              {chosen?.territory_snapshot}. Ogni selezione mostra una sola categoria e un solo
              livello; non sommare totali e dettagli. Età e abitazioni sono disponibili per regione,
              famiglie anche per comune nel 2021.
            </p>
          </section>
        )}
        {release?.is_demo && (
          <div className="notice demo">
            <strong>Dimostrazione con dati inventati</strong>
            <span>
              {' '}
              Questi territori e valori servono a verificare il sistema. Non descrivono la
              popolazione italiana.
            </span>
          </div>
        )}
        {!loading && !error && !releases.length && (
          <div className="empty">
            <h2>Nessuna versione pubblicata</h2>
            <p>
              Le osservazioni saranno disponibili dopo l’importazione e il superamento dei controlli
              di qualità.
            </p>
          </div>
        )}
        {release?.dataset_id === 'istat_population_regions' && (
          <div className="notice official">
            <strong>Dati ISTAT · 20 regioni e totale Italia</strong>
            <span>
              {' '}
              Il totale Italia serve al controllo: non va sommato alle regioni. “Senza flag ISTAT”
              descrive lo stato fornito dalla fonte, senza attribuire un metodo di rilevazione.
            </span>
          </div>
        )}
        <div className="workspace">
          <section
            className="panel observations"
            aria-labelledby="observations-title"
            aria-busy={loading}
          >
            <div className="panel-heading">
              <h2 id="observations-title">
                {isM2 ? 'Evidenze per territorio' : 'Popolazione per territorio'}
              </h2>
              <span className="muted">Unità: {unit}</span>
            </div>
            {loading && (
              <p role="status" className="empty">
                Caricamento delle evidenze…
              </p>
            )}
            {!loading && page && (
              <>
                <div className="table-scroll">
                  <table>
                    <caption className="sr-only">Osservazioni della versione selezionata</caption>
                    <thead>
                      <tr>
                        <th>Territorio</th>
                        <th>Codice</th>
                        <th>Livello</th>
                        <th className="numeric">Valore</th>
                        <th>Stato</th>
                      </tr>
                    </thead>
                    <tbody>
                      {page.items.map((item) => (
                        <tr key={item.territory_id}>
                          <td>
                            {isM2 && item.level !== 'country' ? (
                              <a
                                href={`${API_BASE}/v2/releases/${release.id}/territories/${item.territory_id}/boundary`}
                              >
                                {item.territory_name}{' '}
                                <span className="sr-only">· confine GeoJSON</span>
                              </a>
                            ) : (
                              item.territory_name
                            )}
                          </td>
                          <td className="code">{item.territory_code}</td>
                          <td>
                            {
                              {
                                country: 'Italia · totale',
                                region: 'Regione',
                                province: 'Provincia',
                                municipality: 'Comune',
                              }[item.level]
                            }
                          </td>
                          <td className="numeric">
                            {item.value === null
                              ? 'Non disponibile'
                              : number.format(Number(item.value))}
                          </td>
                          <td>
                            <span className="tag">
                              {
                                {
                                  demo: 'Dimostrativo',
                                  observed: 'Osservato',
                                  estimated: 'Stimato',
                                  missing: 'Mancante',
                                  suppressed: 'Riservato',
                                  unflagged_upstream: 'Senza flag ISTAT',
                                }[item.status]
                              }
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!page.items.length && (
                  <p className="empty">Nessuna osservazione per questa selezione.</p>
                )}
                <div className="pagination">
                  <span>{page.items.length} osservazioni in questa pagina</span>
                  <div>
                    {after > 0 && <button onClick={() => setAfter(0)}>Prima pagina</button>}
                    {page.next_cursor !== null && (
                      <button onClick={() => setAfter(page.next_cursor!)}>Successive →</button>
                    )}
                  </div>
                </div>
              </>
            )}
          </section>
          <aside className="panel evidence" aria-labelledby="evidence-title">
            <h2 id="evidence-title">Traccia dell’evidenza</h2>
            {release ? (
              <>
                <dl>
                  <dt>Fonte</dt>
                  <dd>
                    <a href={release.upstream_url}>
                      {sources.find((item) => item.id === release.source_id)?.name ??
                        release.source_id}{' '}
                      ↗
                    </a>
                  </dd>
                  <dt>Acquisita</dt>
                  <dd>{dateTime(release.retrieved_at)}</dd>
                  <dt>Pubblicata in Itadb</dt>
                  <dd>{dateTime(release.published_at)}</dd>
                  {!release.is_demo && (
                    <>
                      <dt>Aggiornamento del dataflow ISTAT</dt>
                      <dd>
                        {release.upstream_last_update
                          ? dateTime(release.upstream_last_update)
                          : 'Non disponibile'}
                      </dd>
                      <dt>Pubblicazione alla fonte</dt>
                      <dd>
                        {release.upstream_published_at
                          ? dateTime(release.upstream_published_at)
                          : 'Non accertata'}
                      </dd>
                      <dt>Snapshot territoriale</dt>
                      <dd>{chosen?.territory_snapshot ?? release.territory_snapshot}</dd>
                    </>
                  )}
                  <dt>Licenza di questa versione</dt>
                  <dd>
                    <a href={release.license_url}>Consulta la licenza ↗</a>
                  </dd>
                  <dt>Verifiche</dt>
                  <dd>
                    {quality.length
                      ? `${quality.filter((check) => check.passed).length} / ${quality.length} superate`
                      : 'Verifiche non disponibili'}
                  </dd>
                </dl>
                {release.supersedes_release_id && (
                  <div className="revision">
                    <h3>Revisione della versione precedente</h3>
                    <p>{release.revision_reason}</p>
                    <a href={`${API_BASE}/v2/releases/${release.supersedes_release_id}`}>
                      Consulta la provenienza precedente ↗
                    </a>
                  </div>
                )}
                {release.attribution && <p className="muted">{release.attribution}</p>}
                <details>
                  <summary>Identificativi e checksum</summary>
                  <p>Versione</p>
                  <code>{release.id}</code>
                  <p>SHA-256 originale</p>
                  <code>{release.raw_sha256}</code>
                  <p>SHA-256 contratto</p>
                  <code>{release.contract_sha256}</code>
                  {artifacts.length > 0 && (
                    <>
                      <p>{artifacts.length} artefatti tracciati</p>
                      <a href={`${API_BASE}/v2/releases/${release.id}/artifacts`}>
                        Consulta manifest e checksum via API ↗
                      </a>
                    </>
                  )}
                </details>
                <div className="limitations">
                  <h3>Limiti di utilizzo</h3>
                  <p>{release.limitations}</p>
                </div>
              </>
            ) : (
              <p className="muted">Seleziona una versione per consultarne la provenienza.</p>
            )}
          </aside>
        </div>
        {isM2 && release && <TerritorialHistory key={release.id} releaseId={release.id} />}
        <footer>
          Itadb è un’infrastruttura aperta in costruzione. La popolazione sintetica 1:1 è una fase
          futura; gli agenti non rappresenteranno persone reali.
        </footer>
      </main>
    </>
  );
}
