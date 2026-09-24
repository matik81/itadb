import './evidence.css';
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
  type Observation,
  type TerritoryPage,
} from './api';
import { TerritorialHistory } from './TerritorialHistory';
import { TerritoryDetail } from './TerritoryDetail';
import { Icon, levelLabels } from './Icons';
import { SortHeader, type TableSort } from './SortHeader';

const number = new Intl.NumberFormat('it-IT', { maximumFractionDigits: 6 });
const dateTime = (value: string) => new Date(value).toLocaleString('it-IT');

export function EvidenceExplorer() {
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
  const [territory, setTerritory] = useState<Observation | null>(null);
  const [sort, setSort] = useState<TableSort>({ field: 'name', direction: 'asc' });
  const [searchDraft, setSearchDraft] = useState('');
  const [filters, setFilters] = useState({ search: '', parent: '', status: '' });
  const [parents, setParents] = useState<TerritoryPage['items']>([]);
  const [parentError, setParentError] = useState('');
  const [parentRetry, setParentRetry] = useState(0);
  const release = releases.find((item) => item.id === selected);
  const isM2 = release?.dataset_id === 'istat_m2';
  const chosen = coverage.find((item) => `${item.period}|${item.series_code}` === selection);
  const parentLevel = isM2
    ? level === 'municipality'
      ? 'province'
      : level === 'province'
        ? 'region'
        : null
    : null;
  function resetFilters() {
    setAfter(0);
    setFilters({ search: '', parent: '', status: '' });
    setSearchDraft('');
  }
  function changeSort(next: TableSort) {
    setSort(next);
    setAfter(0);
  }
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
    setParents([]);
    setParentError('');
    if (!release || !parentLevel || !chosen?.territory_snapshot) return;
    const controller = new AbortController();
    const query = new URLSearchParams({
      release_id: release.id,
      snapshot: chosen.territory_snapshot,
      level: parentLevel,
      limit: '500',
    });
    get<TerritoryPage>(`/v2/territories?${query}`, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        if (result.next_cursor !== null)
          throw new Error('Elenco dei territori incompleto. Riprova.');
        setParents(result.items.sort((a, b) => a.name.localeCompare(b.name, 'it')));
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setParentError(String(reason.message));
      });
    return () => controller.abort();
  }, [release, parentLevel, chosen?.territory_snapshot, parentRetry]);

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
      sort_by: sort.field,
      direction: sort.direction,
    });
    if (isM2) query.set('level', level);
    if (filters.search) query.set('search', filters.search);
    if (filters.parent) query.set('parent_code', filters.parent);
    if (filters.status) query.set('status', filters.status);
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
  }, [release, after, retry, chosen, isM2, level, sort, filters]);

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
              resetFilters();
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
                  resetFilters();
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
                  resetFilters();
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
                  resetFilters();
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
            <span> Il totale Italia serve al controllo: non va sommato alle regioni.</span>
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
            <form
              className="table-filters"
              aria-label="Filtri osservazioni"
              onSubmit={(event) => {
                event.preventDefault();
                setFilters({ ...filters, search: searchDraft.trim() });
                setAfter(0);
              }}
            >
              <label>
                Cerca territorio o codice
                <input
                  type="search"
                  value={searchDraft}
                  maxLength={100}
                  onChange={(event) => setSearchDraft(event.target.value)}
                  placeholder="Nome o codice ISTAT"
                />
              </label>
              {parentLevel && (
                <label>
                  {parentLevel === 'region' ? 'Regione' : 'Provincia'}
                  <select
                    value={filters.parent}
                    disabled={!parents.length}
                    onChange={(event) => {
                      setFilters({ ...filters, parent: event.target.value });
                      setAfter(0);
                    }}
                  >
                    <option value="">
                      {parentLevel === 'region' ? 'Tutte le regioni' : 'Tutte le province'}
                    </option>
                    {parents.map((parent) => (
                      <option key={parent.territory_id} value={parent.code}>
                        {parent.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <label>
                Stato del dato
                <select
                  value={filters.status}
                  onChange={(event) => {
                    setFilters({ ...filters, status: event.target.value });
                    setAfter(0);
                  }}
                >
                  <option value="">Tutti gli stati</option>
                  <option value="observed">Osservato</option>
                  <option value="estimated">Stimato</option>
                  <option value="unflagged_upstream">—</option>
                  <option value="missing">Mancante</option>
                  <option value="suppressed">Riservato</option>
                  <option value="demo">Dimostrativo</option>
                </select>
              </label>
              <button type="submit">Cerca</button>
              <button type="button" onClick={resetFilters}>
                Azzera filtri
              </button>
              {parentError && (
                <p role="alert">
                  {parentError}{' '}
                  <button type="button" onClick={() => setParentRetry((value) => value + 1)}>
                    Riprova filtri
                  </button>
                </p>
              )}
            </form>
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
                        <SortHeader
                          label="Territorio"
                          field="name"
                          sort={sort}
                          onSort={changeSort}
                        />
                        <SortHeader label="Codice" field="code" sort={sort} onSort={changeSort} />
                        <SortHeader
                          label="Valore"
                          field="value"
                          sort={sort}
                          onSort={changeSort}
                          numeric
                        />
                        <SortHeader label="Stato" field="status" sort={sort} onSort={changeSort} />
                      </tr>
                    </thead>
                    <tbody>
                      {page.items.map((item) => (
                        <tr key={item.territory_id}>
                          <td>
                            <span className="territory-name-cell">
                              <Icon kind={item.level} label={levelLabels[item.level]} />
                              {isM2 && item.level !== 'country' ? (
                                <button
                                  type="button"
                                  className="territory-link"
                                  aria-haspopup="dialog"
                                  onClick={() => setTerritory(item)}
                                >
                                  {item.territory_name}{' '}
                                  <span className="sr-only">· apri scheda e mappa</span>
                                </button>
                              ) : (
                                item.territory_name
                              )}
                            </span>
                          </td>
                          <td className="code">{item.territory_code}</td>
                          <td className="numeric">
                            {item.value === null
                              ? 'Non disponibile'
                              : number.format(Number(item.value))}
                          </td>
                          <td>
                            <span
                              className={item.status === 'unflagged_upstream' ? 'muted' : 'tag'}
                            >
                              {
                                {
                                  demo: 'Dimostrativo',
                                  observed: 'Osservato',
                                  estimated: 'Stimato',
                                  missing: 'Mancante',
                                  suppressed: 'Riservato',
                                  unflagged_upstream: '—',
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
                    {release.is_demo ? (
                      'Fixture dimostrativa inclusa nel progetto'
                    ) : (
                      <a href={release.upstream_url}>
                        {sources.find((item) => item.id === release.source_id)?.name ??
                          release.source_id}{' '}
                        ↗
                      </a>
                    )}
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
        {territory && release && chosen && (
          <TerritoryDetail
            key={`${release.id}-${territory.territory_id}-${chosen.period}-${chosen.series_code}`}
            observation={territory}
            coverage={chosen}
            release={release}
            sourceName={
              sources.find((item) => item.id === release.source_id)?.name ?? release.source_id
            }
            onClose={() => setTerritory(null)}
          />
        )}
        <footer>
          Itadb è un’infrastruttura aperta in costruzione. La popolazione sintetica 1:1 è una fase
          futura; gli agenti non rappresenteranno persone reali.
        </footer>
      </main>
    </>
  );
}
