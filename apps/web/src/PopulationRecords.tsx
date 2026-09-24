import { useState } from 'react';
import {
  number,
  query,
  useResource,
  type PersonPage,
  type HouseholdPage,
  type Household,
} from './population-api';
import { SortHeader, type TableSort } from './SortHeader';
import { Icon } from './Icons';

export type PersonFilters = { sex: string; citizenship: string; ageMin: number; ageMax: number };
export function PopulationRecords({
  snapshot,
  municipality,
  name,
  filters,
  labels,
  onClose,
}: {
  snapshot: number;
  municipality: string;
  name: string;
  filters: PersonFilters;
  labels: Record<string, string>;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<'persons' | 'households'>('persons');
  const [sort, setSort] = useState<TableSort>({ field: 'person_id', direction: 'asc' });
  const [after, setAfter] = useState(0);
  const [history, setHistory] = useState<number[]>([]);
  const [family, setFamily] = useState<number | null>(null);
  const [size, setSize] = useState('');
  const params = query({
    municipality_code: municipality,
    sort_by: sort.field,
    direction: sort.direction,
    after,
    limit: 40,
    ...(tab === 'persons'
      ? {
          sex: filters.sex,
          citizenship_code: filters.citizenship,
          age_min: filters.ageMin,
          age_max: filters.ageMax,
        }
      : { size }),
  });
  const data = useResource<PersonPage | HouseholdPage>(
    `/v3/populations/${snapshot}/${tab}?${params}`,
  );
  const detail = useResource<Household>(
    family ? `/v3/populations/${snapshot}/households/${family}` : null,
  );
  function changeSort(next: TableSort) {
    setSort(next);
    setAfter(0);
    setHistory([]);
  }
  function changeTab(next: 'persons' | 'households') {
    setTab(next);
    setSort({ field: next === 'persons' ? 'person_id' : 'household_id', direction: 'asc' });
    setAfter(0);
    setHistory([]);
    setFamily(null);
  }
  const persons = (data.data as PersonPage | null)?.items;
  return (
    <section className="records-panel panel" aria-label={`Record di ${name}`}>
      <div className="panel-heading">
        <div>
          <span className="eyebrow">INDIVIDUI E FAMIGLIE</span>
          <h2>{name}</h2>
        </div>
        <button className="icon-button" aria-label="Chiudi elenco" onClick={onClose}>
          ×
        </button>
      </div>
      <div className="records-tabs">
        <button
          className={tab === 'persons' ? 'selected' : ''}
          onClick={() => changeTab('persons')}
        >
          <Icon kind="persons" />
          Individui
        </button>
        <button
          className={tab === 'households' ? 'selected' : ''}
          onClick={() => changeTab('households')}
        >
          <Icon kind="households" />
          Famiglie
        </button>
        <span>Snapshot {snapshot}</span>
      </div>
      {tab === 'households' && (
        <label className="inline-control">
          Componenti
          <select
            value={size}
            onChange={(e) => {
              setSize(e.target.value);
              setAfter(0);
              setHistory([]);
            }}
          >
            <option value="">Tutte le dimensioni</option>
            {[1, 2, 3, 4, 5, 6].map((n) => (
              <option key={n} value={n}>
                {n === 6 ? '6 (classe 6+)' : n}
              </option>
            ))}
          </select>
        </label>
      )}
      {data.loading && <p role="status">Caricamento dei record…</p>}
      {data.error && (
        <div role="alert">
          {data.error} <button onClick={data.retry}>Riprova</button>
        </div>
      )}
      {data.data && (
        <>
          <div className="records-scroll">
            <table>
              <thead>
                <tr>
                  <SortHeader
                    label="ID"
                    field={tab === 'persons' ? 'person_id' : 'household_id'}
                    sort={sort}
                    onSort={changeSort}
                  />
                  {tab === 'persons' ? (
                    <>
                      <SortHeader label="Età" field="age" sort={sort} onSort={changeSort} />
                      <SortHeader label="Sesso" field="sex" sort={sort} onSort={changeSort} />
                      <SortHeader
                        label="Cittadinanza"
                        field="citizenship_code"
                        sort={sort}
                        onSort={changeSort}
                      />
                      <SortHeader
                        label="Famiglia"
                        field="household_id"
                        sort={sort}
                        onSort={changeSort}
                      />
                    </>
                  ) : (
                    <>
                      <SortHeader label="Componenti" field="size" sort={sort} onSort={changeSort} />
                      <th scope="col">Esplora</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {tab === 'persons'
                  ? persons?.map((p) => (
                      <tr key={p.person_id}>
                        <td className="mono">
                          <Icon kind="persons" />
                          {p.person_id}
                        </td>
                        <td>
                          {p.age}
                          {p.age_is_lower_bound ? '+' : ''}
                        </td>
                        <td>{p.sex}</td>
                        <td>{labels[p.citizenship_code] ?? p.citizenship_code}</td>
                        <td>
                          {p.household_id ? (
                            <button
                              className="text-button"
                              onClick={() => setFamily(p.household_id)}
                            >
                              {p.household_id} ↗
                            </button>
                          ) : (
                            <span className="muted">Non assegnata</span>
                          )}
                        </td>
                      </tr>
                    ))
                  : (data.data as HouseholdPage).items.map((h) => (
                      <tr key={h.household_id}>
                        <td className="mono">
                          <Icon kind="households" />
                          {h.household_id}
                        </td>
                        <td>{h.size}</td>
                        <td>
                          <button className="text-button" onClick={() => setFamily(h.household_id)}>
                            Apri famiglia ↗
                          </button>
                        </td>
                      </tr>
                    ))}
              </tbody>
            </table>
          </div>
          {data.data.items.length === 0 && (
            <p className="empty-state">Nessun record corrisponde ai filtri.</p>
          )}
          <div className="pagination">
            <span>
              {number.format(data.data.items.length)} record nella pagina · ordinamento sull’intera
              selezione
            </span>
            <button
              disabled={!history.length}
              onClick={() => {
                setAfter(history[history.length - 1]);
                setHistory((h) => h.slice(0, -1));
              }}
            >
              ← Precedenti
            </button>
            <button
              disabled={data.data.next_cursor === null}
              onClick={() => {
                setHistory((h) => [...h, after]);
                setAfter(data.data!.next_cursor!);
              }}
            >
              Successivi →
            </button>
          </div>
        </>
      )}
      {family && (
        <aside className="family-detail" aria-label={`Famiglia ${family}`}>
          <div className="panel-heading">
            <h3>
              <Icon kind="households" />
              Famiglia {family}
            </h3>
            <button aria-label="Chiudi famiglia" onClick={() => setFamily(null)}>
              ×
            </button>
          </div>
          {detail.loading && <p role="status">Caricamento famiglia…</p>}
          {detail.error && (
            <p role="alert">
              {detail.error} <button onClick={detail.retry}>Riprova</button>
            </p>
          )}
          {detail.data && (
            <>
              <p>{detail.data.size} componenti nello stesso comune</p>
              <ul className="family-members">
                {detail.data.members.map((p) => (
                  <li key={p.person_id}>
                    <Icon kind="persons" />
                    <strong>#{p.person_id}</strong>
                    <span>
                      {p.age}
                      {p.age_is_lower_bound ? '+' : ''} anni · {p.sex}
                    </span>
                    <span>{labels[p.citizenship_code] ?? p.citizenship_code}</span>
                    {p.reference_adult && <small>Adulto di riferimento</small>}
                  </li>
                ))}
              </ul>
              <p className="muted">
                La composizione è casuale entro i vincoli del modello. Non sono assegnate relazioni
                di parentela.
              </p>
            </>
          )}
        </aside>
      )}
    </section>
  );
}
