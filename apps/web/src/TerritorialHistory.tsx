import { useEffect, useState } from 'react';
import { API_BASE, get, type CrosswalkPage } from './api';

export function TerritorialHistory({ releaseId }: { releaseId: string }) {
  const [page, setPage] = useState<CrosswalkPage | null>(null);
  const [after, setAfter] = useState(0);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setPage(null);
    setError('');
    get<CrosswalkPage>(
      `/v2/crosswalks?release_id=${releaseId}&after=${after}&limit=50`,
      controller.signal,
    )
      .then((result) => {
        if (!controller.signal.aborted) setPage(result);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(String(reason.message));
      });
    return () => controller.abort();
  }, [releaseId, after, retry]);
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
                  <th>Decorrenza</th>
                  <th>Variazione</th>
                  <th>Codici</th>
                  <th>Utilizzo</th>
                </tr>
              </thead>
              <tbody>
                {page.items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.effective_date}</td>
                    <td>
                      <a href={item.source_url}>{item.description} ↗</a>
                    </td>
                    <td className="code">
                      {item.from_code} → {item.to_code}
                    </td>
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
