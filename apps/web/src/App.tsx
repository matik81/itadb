import { useEffect, useState } from 'react';
import { API_BASE, get, type Page, type Quality, type Release, type Source } from './api';

const number = new Intl.NumberFormat('it-IT', { maximumFractionDigits: 6 });
const dateTime = (value: string) => new Date(value).toLocaleString('it-IT');

export function App() {
  const [releases, setReleases] = useState<Release[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [selected, setSelected] = useState('');
  const [page, setPage] = useState<Page | null>(null);
  const [quality, setQuality] = useState<Quality[]>([]);
  const [after, setAfter] = useState(0);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const release = releases.find((item) => item.id === selected);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    Promise.all([
      get<Release[]>('/v1/releases', controller.signal),
      get<Source[]>('/v1/sources', controller.signal),
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
    if (!release) return;
    const controller = new AbortController();
    setPage(null);
    setQuality([]);
    setLoading(true);
    setError('');
    const query = new URLSearchParams({
      release_id: release.id,
      period: release.reference_period,
      series: 'population_total',
      after: String(after),
      limit: '100',
    });
    Promise.all([
      get<Page>(`/v1/observations?${query}`, controller.signal),
      get<Quality[]>(`/v1/releases/${release.id}/quality`, controller.signal),
    ])
      .then(([result, checks]) => {
        setPage(result);
        setQuality(checks);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(String(reason.message));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [release, after, retry]);

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
        {error && (
          <div role="alert" className="notice error">
            <strong>Dati non disponibili</strong>
            <p>{error}</p>
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
            }}
          >
            <option value="" disabled>
              Seleziona una versione
            </option>
            {releases.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title} · {item.reference_period}
              </option>
            ))}
          </select>
          {release && (
            <span className="period">
              Riferimento <strong>{release.reference_period}</strong>
            </span>
          )}
        </section>
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
        <div className="workspace">
          <section
            className="panel observations"
            aria-labelledby="observations-title"
            aria-busy={loading}
          >
            <div className="panel-heading">
              <h2 id="observations-title">Popolazione per territorio</h2>
              <span className="muted">Unità: persone</span>
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
                        <th className="numeric">Valore</th>
                        <th>Stato</th>
                      </tr>
                    </thead>
                    <tbody>
                      {page.items.map((item) => (
                        <tr key={item.territory_id}>
                          <td>{item.territory_name}</td>
                          <td className="code">{item.territory_code}</td>
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
                  <dt>Pubblicata</dt>
                  <dd>{dateTime(release.published_at)}</dd>
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
                <details>
                  <summary>Identificativi e checksum</summary>
                  <p>Versione</p>
                  <code>{release.id}</code>
                  <p>SHA-256 originale</p>
                  <code>{release.raw_sha256}</code>
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
        <footer>
          Itadb è un’infrastruttura aperta in costruzione. La popolazione sintetica 1:1 è una fase
          futura; gli agenti non rappresenteranno persone reali.
        </footer>
      </main>
    </>
  );
}
