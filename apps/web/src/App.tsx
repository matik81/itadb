import { useEffect, useMemo, useState } from 'react';
import { Icon } from './Icons';
import { PopulationMap } from './PopulationMap';
import { PopulationMethod } from './PopulationMethod';
import { PopulationRecords, type PersonFilters } from './PopulationRecords';
import {
  number,
  query,
  repositoryUrl,
  useResource,
  type Snapshot,
  type Evidence,
  type PopulationMapData,
  type Distribution,
} from './population-api';

const initialFilters: PersonFilters = { sex: '', citizenship: '', ageMin: 0, ageMax: 100 };
export function App() {
  const [mode, setMode] = useState(window.location.hash === '#metodo' ? 'method' : 'explore');
  const [snapshotId, setSnapshotId] = useState(0);
  const [municipalityCode, setMunicipalityCode] = useState('');
  const [region, setRegion] = useState('');
  const [search, setSearch] = useState('');
  const [filters, setFilters] = useState<PersonFilters>(initialFilters);
  const [records, setRecords] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(window.innerWidth > 700);
  const [statisticsOpen, setStatisticsOpen] = useState(window.innerWidth > 700);
  const snapshots = useResource<Snapshot[]>('/v3/populations');
  const evidence = useResource<Evidence>(snapshotId ? `/v3/populations/${snapshotId}` : null);
  const map = useResource<PopulationMapData>(
    snapshotId ? `/v3/populations/${snapshotId}/map` : null,
  );
  const municipalities = map.data?.municipalities ?? [];
  const municipality = municipalities.find((m) => m.code === municipalityCode) ?? null;
  const labels = (evidence.data?.provenance.country_labels ?? {}) as Record<string, string>;
  const distributionQuery = query({
    municipality_code: municipalityCode,
    region_code: region,
    sex: filters.sex,
    citizenship_code: filters.citizenship,
    age_min: filters.ageMin,
    age_max: filters.ageMax,
  });
  const distribution = useResource<Distribution[]>(
    snapshotId ? `/v3/populations/${snapshotId}/distributions?${distributionQuery}` : null,
  );
  useEffect(() => {
    if (snapshots.data?.length && !snapshotId)
      setSnapshotId((snapshots.data.find((s) => !s.is_fixture) ?? snapshots.data[0]).id);
  }, [snapshots.data, snapshotId]);
  useEffect(() => {
    const handle = () => setMode(window.location.hash === '#metodo' ? 'method' : 'explore');
    window.addEventListener('hashchange', handle);
    return () => window.removeEventListener('hashchange', handle);
  }, []);
  const filteredMunicipalities = useMemo(
    () =>
      municipalities
        .filter(
          (m) =>
            (!region || m.region_code === region) &&
            (!search ||
              `${m.name} ${m.code}`
                .toLocaleLowerCase('it')
                .includes(search.toLocaleLowerCase('it'))),
        )
        .sort((a, b) => a.name.localeCompare(b.name, 'it')),
    [municipalities, region, search],
  );
  const histogram = useMemo(
    () =>
      Array.from({ length: 11 }, (_, i) => ({
        label: i === 10 ? '100+' : `${i * 10}–${i * 10 + 9}`,
        male: 0,
        female: 0,
      })),
    [],
  );
  const bins = histogram.map((b) => ({ ...b }));
  let males = 0,
    females = 0;
  for (const row of distribution.data ?? []) {
    const bin = bins[Math.min(10, Math.floor(row.age / 10))];
    if (row.sex === 'M') {
      bin.male += row.persons;
      males += row.persons;
    } else {
      bin.female += row.persons;
      females += row.persons;
    }
  }
  const maxBin = Math.max(1, ...bins.map((b) => b.male + b.female));
  function selectMunicipality(code: string) {
    setMunicipalityCode(code);
    setRecords(false);
    setSearch('');
    const m = municipalities.find((item) => item.code === code);
    if (m) setRegion(m.region_code);
  }
  function selectSnapshot(id: number) {
    setSnapshotId(id);
    setMunicipalityCode('');
    setRegion('');
    setSearch('');
    setFilters(initialFilters);
    setRecords(false);
  }
  const activeSnapshot = snapshots.data?.find((s) => s.id === snapshotId);
  const activeRegion = map.data?.regions.find((r) => r.code === region);
  const scope = municipality?.name ?? activeRegion?.name ?? 'Italia';
  const anyError = snapshots.error || evidence.error || map.error;
  return (
    <div className={`population-app ${mode === 'method' ? 'method-mode' : ''}`}>
      <a className="skip-link" href="#population-content">
        Vai al contenuto
      </a>
      <header className="app-header">
        <a className="brand" href="#esplora" aria-label="Itadb — esplora">
          <span className="brand-glyph">◉</span>ita<span>db</span>
          <small>POPOLAZIONE VIRTUALE</small>
        </a>
        <nav aria-label="Navigazione principale">
          <a
            href="#esplora"
            className={mode === 'explore' ? 'active' : ''}
            aria-current={mode === 'explore' ? 'page' : undefined}
          >
            Esplora
          </a>
          <a
            href="#metodo"
            className={mode === 'method' ? 'active' : ''}
            aria-current={mode === 'method' ? 'page' : undefined}
          >
            Metodo e verifiche
          </a>
        </nav>
        <a className="repository-link" href={repositoryUrl} target="_blank" rel="noreferrer">
          GitHub ↗
        </a>
      </header>
      <main id="population-content" className={mode === 'method' ? 'method-main' : 'explore-main'}>
        {mode === 'explore' && (
          <PopulationMap
            data={map.data}
            selected={municipalityCode}
            onSelect={selectMunicipality}
          />
        )}
        {(snapshots.loading || (!!snapshotId && !evidence.data && evidence.loading)) && (
          <div className="central-state panel" role="status">
            <span className="loading-signal" />
            <h1>Caricamento della popolazione</h1>
            <p>Connessione allo snapshot verificato…</p>
          </div>
        )}
        {anyError && (
          <div className="central-state panel" role="alert">
            <h1>La popolazione non è disponibile</h1>
            <p>{anyError}</p>
            <button
              onClick={() => {
                snapshots.retry();
                evidence.retry();
                map.retry();
              }}
            >
              Riprova
            </button>
          </div>
        )}
        {snapshots.data?.length === 0 && (
          <div className="central-state panel">
            <h1>Nessuna popolazione disponibile</h1>
            <p>
              Qui potrai esplorare gli individui e le famiglie di uno snapshot verificato, appena
              disponibile nel database.
            </p>
            <a href={`${repositoryUrl}/blob/main/docs/population.md`}>Consulta il progetto ↗</a>
          </div>
        )}
        {evidence.data && mode === 'method' && (
          <PopulationMethod evidence={evidence.data} municipality={municipality} />
        )}
        {evidence.data && mode === 'explore' && (
          <>
            <div className="map-caption">
              <span className="eyebrow">ITALIA / {evidence.data.reference_date.slice(0, 4)}</span>
              <h1>
                L’Italia virtuale,
                <br />
                individuo per individuo.
              </h1>
              <p>
                Esplora individui e famiglie virtuali,
                <br />a partire dal territorio.
              </p>
            </div>
            <button
              className="mobile-panel-toggle"
              onClick={() => setFiltersOpen(!filtersOpen)}
              aria-expanded={filtersOpen}
            >
              {filtersOpen ? 'Nascondi strumenti' : 'Mostra strumenti'}
            </button>
            <aside
              className={`explore-sidebar panel ${filtersOpen ? '' : 'mobile-hidden'}`}
              aria-label="Filtri di esplorazione"
            >
              <div className="panel-heading">
                <span className="eyebrow">ESPLORA IL MODELLO</span>
                <span className="status-label">
                  <i />
                  VERIFICATO
                </span>
              </div>
              <label>
                Versione della popolazione
                <select value={snapshotId} onChange={(e) => selectSnapshot(Number(e.target.value))}>
                  {snapshots.data?.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.reference_date} · {s.run_id.slice(0, 8)}
                      {s.is_fixture ? ' · fixture inventata' : ''}
                    </option>
                  ))}
                </select>
              </label>
              {activeSnapshot?.is_fixture && (
                <p className="fixture-label">
                  Fixture inventata: dati esclusivamente dimostrativi.
                </p>
              )}
              <div className="territory-heading">
                <span className="eyebrow">TERRITORIO</span>
                {(region || municipalityCode) && (
                  <button
                    className="text-button"
                    onClick={() => {
                      setRegion('');
                      setMunicipalityCode('');
                      setSearch('');
                      setRecords(false);
                    }}
                  >
                    Tutta Italia ↗
                  </button>
                )}
              </div>
              <label>
                Regione
                <select
                  value={region}
                  onChange={(e) => {
                    setRegion(e.target.value);
                    setMunicipalityCode('');
                    setRecords(false);
                  }}
                >
                  <option value="">Tutte le regioni</option>
                  {map.data?.regions.map((r) => (
                    <option key={r.code} value={r.code}>
                      {r.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Cerca un comune
                <input
                  type="search"
                  value={search}
                  placeholder="Nome o codice ISTAT"
                  onChange={(e) => setSearch(e.target.value)}
                />
              </label>
              {map.loading && <p role="status">Caricamento dei territori…</p>}
              {(search || !municipalityCode) && (
                <div className="municipality-results" aria-label="Comuni disponibili">
                  {filteredMunicipalities.slice(0, 6).map((m) => (
                    <button key={m.code} onClick={() => selectMunicipality(m.code)}>
                      <Icon kind="municipality" />
                      <span>
                        {m.name}
                        <small>{m.province_name}</small>
                      </span>
                      <span>↗</span>
                    </button>
                  ))}
                  {map.data && !filteredMunicipalities.length && <p>Nessun comune trovato.</p>}
                  {filteredMunicipalities.length > 6 && (
                    <small>
                      Affina la ricerca tra {number.format(filteredMunicipalities.length)} comuni.
                    </small>
                  )}
                </div>
              )}
              {municipality && (
                <div className="selected-territory">
                  <div>
                    <Icon kind="municipality" />
                    <h2>{municipality.name}</h2>
                  </div>
                  <p>
                    {municipality.province_name} · {municipality.code}
                  </p>
                  <div className="territory-counts">
                    <span>
                      <Icon kind="persons" />
                      <strong>{number.format(municipality.persons)}</strong>individui
                    </span>
                    <span>
                      <Icon kind="households" />
                      <strong>{number.format(municipality.households)}</strong>famiglie
                    </span>
                  </div>
                  <button className="primary-button" onClick={() => setRecords(true)}>
                    Esplora i record <span>↗</span>
                  </button>
                </div>
              )}
              <details className="individual-filters" open>
                <summary>
                  Filtri individui <small>Istogramma ed elenco</small>
                </summary>
                <div className="filter-grid">
                  <label>
                    Sesso
                    <select
                      value={filters.sex}
                      onChange={(e) => setFilters({ ...filters, sex: e.target.value })}
                    >
                      <option value="">Tutti</option>
                      <option value="M">Maschile</option>
                      <option value="F">Femminile</option>
                    </select>
                  </label>
                  <label>
                    Cittadinanza
                    <select
                      value={filters.citizenship}
                      onChange={(e) => setFilters({ ...filters, citizenship: e.target.value })}
                    >
                      <option value="">Tutte</option>
                      {Object.entries(labels)
                        .sort((a, b) => a[1].localeCompare(b[1], 'it'))
                        .map(([code, label]) => (
                          <option value={code} key={code}>
                            {label}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    Età minima
                    <input
                      type="number"
                      min={0}
                      max={filters.ageMax}
                      value={filters.ageMin}
                      onChange={(e) =>
                        setFilters({
                          ...filters,
                          ageMin: Math.min(filters.ageMax, Math.max(0, Number(e.target.value))),
                        })
                      }
                    />
                  </label>
                  <label>
                    Età massima
                    <input
                      type="number"
                      min={filters.ageMin}
                      max={100}
                      value={filters.ageMax}
                      onChange={(e) =>
                        setFilters({
                          ...filters,
                          ageMax: Math.max(filters.ageMin, Math.min(100, Number(e.target.value))),
                        })
                      }
                    />
                  </label>
                </div>
                <small>100 include la classe aperta 100+.</small>
                <button className="text-button" onClick={() => setFilters(initialFilters)}>
                  Reimposta filtri
                </button>
              </details>
            </aside>
            <aside
              className={`distribution-panel panel ${statisticsOpen ? '' : 'stats-collapsed'}`}
              aria-label="Distribuzione della popolazione"
            >
              <div className="panel-heading">
                <span className="eyebrow">NELLA SELEZIONE</span>
                <Icon kind="persons" />
              </div>
              <h2>{scope}</h2>
              {distribution.loading ? (
                <p role="status">Aggiornamento distribuzione…</p>
              ) : distribution.error ? (
                <p role="alert">
                  {distribution.error} <button onClick={distribution.retry}>Riprova</button>
                </p>
              ) : (
                <>
                  <strong className="population-total">{number.format(males + females)}</strong>
                  <span className="muted">individui virtuali</span>
                  <div className="sex-totals">
                    <span>
                      <i className="male-key" />M <strong>{number.format(males)}</strong>
                    </span>
                    <span>
                      <i className="female-key" />F <strong>{number.format(females)}</strong>
                    </span>
                  </div>
                  <div className="chart-heading">
                    <span>Distribuzione per età</span>
                    <small>anni</small>
                  </div>
                  <div
                    className="age-histogram"
                    role="img"
                    aria-label={`Distribuzione per età di ${scope}: ${number.format(males + females)} individui`}
                  >
                    {bins.map((b) => (
                      <div
                        className="histogram-row"
                        key={b.label}
                        title={`${b.label}: ${number.format(b.male)} M, ${number.format(b.female)} F`}
                      >
                        <span>{b.label}</span>
                        <div className="histogram-track">
                          <i
                            className="male-bar"
                            style={{ width: `${(b.male / maxBin) * 100}%` }}
                          />
                          <i
                            className="female-bar"
                            style={{ width: `${(b.female / maxBin) * 100}%` }}
                          />
                        </div>
                        <small>{number.format(b.male + b.female)}</small>
                      </div>
                    ))}
                  </div>
                  {males + females === 0 && <p>Nessun individuo corrisponde ai filtri.</p>}
                </>
              )}
              <button
                className="stats-toggle"
                aria-expanded={statisticsOpen}
                onClick={() => setStatisticsOpen(!statisticsOpen)}
              >
                {statisticsOpen ? 'Nascondi istogramma' : 'Mostra istogramma'}
              </button>
              <a href="#metodo" className="verification-link">
                Come verifichiamo questi dati <span>↗</span>
              </a>
            </aside>
            <div className="snapshot-strip">
              <span>
                <i />
                POPOLAZIONE SINTETICA
              </span>
              <span>Riferimento {evidence.data.reference_date}</span>
              <span>Fonti ISTAT · CC BY 4.0</span>
              <span className="mono">{evidence.data.run_id.slice(0, 12)}</span>
            </div>
            {records && municipality && (
              <PopulationRecords
                key={`${snapshotId}-${municipalityCode}-${JSON.stringify(filters)}`}
                snapshot={snapshotId}
                municipality={municipality.code}
                name={municipality.name}
                filters={filters}
                labels={labels}
                onClose={() => setRecords(false)}
              />
            )}
          </>
        )}
      </main>
    </div>
  );
}
