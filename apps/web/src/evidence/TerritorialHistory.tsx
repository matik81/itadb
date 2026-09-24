import { useEffect, useState } from 'react';
import { API_BASE, get, type CrosswalkPage } from '../api';
import { SortHeader, type TableSort } from '../SortHeader';

const kindLabels = {
  merger: 'Fusione',
  split: 'Scissione',
  recode: 'Ricodifica',
  transfer: 'Trasferimento',
};

export function TerritorialHistory({ releaseId }: { releaseId: string }) {
  const [page, setPage] = useState<CrosswalkPage | null>(null);
  const [after, setAfter] = useState(0);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [sort, setSort] = useState<TableSort>({ field: 'date', direction: 'asc' });
  const [kind, setKind] = useState('');
  const [usage, setUsage] = useState('');
  function changeSort(next: TableSort) {
    setSort(next);
    setAfter(0);
  }
  useEffect(() => {
    const controller = new AbortController();
    setPage(null);
    setError('');
    const query = new URLSearchParams({
      release_id: releaseId,
      after: String(after),
      limit: '50',
      sort_by: sort.field,
      direction: sort.direction,
    });
    if (kind) query.set('kind', kind);
    if (usage) query.set('weight_basis', usage);
    get<CrosswalkPage>(`/v2/crosswalks?${query}`, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setPage(result);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(String(reason.message));
      });
    return () => controller.abort();
  }, [releaseId, after, retry, sort, kind, usage]);
  return (
    <section className="panel history" aria-labelledby="history-title">
      <h2 id="history-title">Storia territoriale e corrispondenze</h2>
      <p>
        Snapshot 2020, 2021 e 2024. Le fusioni complete permettono somme esatte; scissioni e
        trasferimenti descrivono collegamenti senza ripartire la popolazione.
      </p>
      <p className="muted">
        Confini comunali ISTAT con correzioni topologiche documentate. Province e regioni derivano
        dall’unione dei comuni. I GeoJSON sono semplificati per la consultazione.
      </p>
      <div className="snapshot-links">
        {['2020-01-01', '2021-12-31', '2024-01-01'].map((snapshot) => (
          <a
            key={snapshot}
            href={`${API_BASE}/v2/territories?release_id=${releaseId}&snapshot=${snapshot}&level=municipality&limit=100`}
          >
            Catalogo comuni {snapshot} ↗
          </a>
        ))}
      </div>
      <div className="table-filters" role="group" aria-label="Filtri storia territoriale">
        <label>
          Tipo di variazione
          <select
            value={kind}
            onChange={(event) => {
              setKind(event.target.value);
              setAfter(0);
            }}
          >
            <option value="">Tutte le variazioni</option>
            {Object.entries(kindLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Utilizzo delle corrispondenze
          <select
            value={usage}
            onChange={(event) => {
              setUsage(event.target.value);
              setAfter(0);
            }}
          >
            <option value="">Tutti gli utilizzi</option>
            <option value="exact">Aggregazione esatta</option>
            <option value="structural">Collegamento strutturale</option>
          </select>
        </label>
        <button
          type="button"
          onClick={() => {
            setKind('');
            setUsage('');
            setAfter(0);
          }}
        >
          Azzera filtri storia
        </button>
      </div>
      {error && (
        <div role="alert">
          <p>{error}</p>
          <button onClick={() => setRetry(retry + 1)}>Riprova storia territoriale</button>
        </div>
      )}
      {!page && !error && <p role="status">Caricamento delle corrispondenze…</p>}
      {page && (
        <>
          <div className="table-scroll">
            <table>
              <caption className="sr-only">Collegamenti tra codici territoriali storici</caption>
              <thead>
                <tr>
                  <SortHeader label="Decorrenza" field="date" sort={sort} onSort={changeSort} />
                  <SortHeader
                    label="Variazione"
                    field="description"
                    sort={sort}
                    onSort={changeSort}
                  />
                  <SortHeader
                    label="Codice origine"
                    field="from_code"
                    sort={sort}
                    onSort={changeSort}
                  />
                  <SortHeader
                    label="Codice destinazione"
                    field="to_code"
                    sort={sort}
                    onSort={changeSort}
                  />
                  <SortHeader label="Utilizzo" field="usage" sort={sort} onSort={changeSort} />
                </tr>
              </thead>
              <tbody>
                {page.items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.effective_date}</td>
                    <td>
                      <a href={item.source_url}>{item.description} ↗</a>
                      <span className="history-kind">{kindLabels[item.kind]}</span>
                    </td>
                    <td className="code">{item.from_code}</td>
                    <td className="code">{item.to_code}</td>
                    <td>
                      {item.weight_basis === 'exact'
                        ? 'Aggregazione esatta · peso 1'
                        : 'Strutturale · nessun peso demografico'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!page.items.length && <p>Nessuna corrispondenza pubblicata.</p>}
          <div className="pagination">
            <span>{page.items.length} collegamenti in questa pagina</span>
            <div>
              {after > 0 && <button onClick={() => setAfter(0)}>Prime corrispondenze</button>}
              {page.next_cursor !== null && (
                <button onClick={() => setAfter(page.next_cursor!)}>Altre corrispondenze →</button>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
