import { useState } from 'react';
import {
  number,
  query,
  repositoryUrl,
  useResource,
  type Evidence,
  type Validation,
  type Comparison,
  type Municipality,
} from './population-api';
import { SortHeader, type TableSort } from './SortHeader';

const kinds: Record<string, string> = {
  sex_age: 'Sesso ed età',
  foreign_age: 'Stranieri per sesso ed età',
  citizenship: 'Singole cittadinanze',
  household_size: 'Dimensioni familiari',
};
const stages = [
  {
    step: '01',
    title: 'Sesso ed età',
    source: 'ISTAT · POSAS',
    body: 'I conteggi per comune, sesso e singola età determinano gli individui. La coorte di nascita rimane stabile; 100+ conserva una classe aperta.',
    assumption: 'Il modello non inventa date di compleanno né età esatte nella classe 100+.',
  },
  {
    step: '02',
    title: 'Geografia',
    source: 'ISTAT · Confini amministrativi',
    body: 'Ogni individuo appartiene a un comune, una provincia o UTS e una regione dello stesso riferimento temporale.',
    assumption:
      'È assegnato il comune di residenza. Le coordinate individuali saranno un’integrazione successiva.',
  },
  {
    step: '03',
    title: 'Cittadinanza',
    source: 'ISTAT · STR e RCS',
    body: 'STR vincola gli stranieri per sesso ed età; RCS vincola le singole cittadinanze per comune e sesso. Entrambi i conteggi sono conservati.',
    assumption:
      'L’incrocio tra età e singola cittadinanza è sintetico: il modello usa una permutazione entro comune e sesso.',
  },
  {
    step: '04',
    title: 'Famiglie',
    source: 'ISTAT · Censimento delle famiglie',
    body: 'Gli individui già definiti vengono raggruppati nello stesso comune, rispettando numero e dimensioni delle famiglie, presenza di un adulto e assegnazione dei minori.',
    assumption:
      'Composizione casuale rispetto a età e cittadinanza; classe 6+ rappresentata con 6 componenti. Gli adulti eccedenti restano non assegnati.',
  },
];
const sourceNames: Record<string, string> = {
  population_zip: 'Popolazione per comune, sesso ed età — POSAS',
  province_zip: 'Popolazione provinciale — riconciliazione',
  geography: 'Confini e gerarchie amministrative',
  households: 'Famiglie per comune e numero di componenti',
  population_parents: 'Popolazione regionale e nazionale',
  str: 'Popolazione straniera per sesso ed età — STR',
  str_regions: 'Popolazione straniera regionale',
  rcs: 'Popolazione per singola cittadinanza — RCS',
};
export function PopulationMethod({
  evidence,
  municipality,
}: {
  evidence: Evidence;
  municipality: Municipality | null;
}) {
  const [kind, setKind] = useState('sex_age');
  const [sort, setSort] = useState<TableSort>({ field: 'category', direction: 'asc' });
  const validation = useResource<Validation[]>(
    `/v3/populations/${evidence.id}/validation?${query({ municipality_code: municipality?.code })}`,
  );
  const comparison = useResource<Comparison[]>(
    municipality
      ? `/v3/populations/${evidence.id}/comparison?${query({ municipality_code: municipality.code, kind })}`
      : null,
  );
  const sources = (evidence.provenance.sources ?? []) as {
    group: string;
    name: string;
    url: string;
    sha256: string;
  }[];
  const rows = [...(comparison.data ?? [])].sort((a, b) => {
    const field = sort.field as keyof Comparison;
    const x = a[field],
      y = b[field];
    return (
      (typeof x === 'number' && typeof y === 'number'
        ? x - y
        : String(x).localeCompare(String(y))) * (sort.direction === 'asc' ? 1 : -1)
    );
  });
  return (
    <article className="method-page">
      <div className="method-intro">
        <span className="eyebrow">DALLE EVIDENZE ALLA POPOLAZIONE</span>
        <h1>
          Come è costruita
          <br />
          questa popolazione.
        </h1>
        <p>
          Ogni individuo appartiene a una versione riproducibile del modello. Qui trovi gli input,
          l’ordine delle integrazioni e i confronti tra i conteggi di origine e i record che stai
          esplorando.
        </p>
        <div className="method-meta">
          <span>
            Popolazione al {new Date(evidence.reference_date).toLocaleDateString('it-IT')}
          </span>
          <span>
            Famiglie al {new Date(evidence.household_reference).toLocaleDateString('it-IT')}
          </span>
          <span>
            Seed {String((evidence.provenance.model as Record<string, unknown>)?.seed ?? '—')}
          </span>
        </div>
      </div>
      <div className="method-stages">
        {stages.map((s) => (
          <section key={s.step}>
            <span className="stage-number">{s.step}</span>
            <div>
              <span className="eyebrow">{s.source}</span>
              <h2>{s.title}</h2>
              <p>{s.body}</p>
              <p className="assumption">
                <span>ASSUNZIONE / PERIMETRO</span>
                {s.assumption}
              </p>
            </div>
          </section>
        ))}
      </div>
      <section className="method-validation">
        <div className="section-heading">
          <div>
            <span className="eyebrow">VERIFICA SUI RECORD DEL DATABASE</span>
            <h2>I conteggi tornano?</h2>
          </div>
          <span className="scope-chip">{municipality?.name ?? 'Italia'}</span>
        </div>
        <p>
          Confronto tra i vincoli ammessi dalle fonti e le distribuzioni calcolate dopo il
          caricamento degli individui e delle famiglie nell’archivio di preparazione. L’uguaglianza
          verifica la calibrazione; la composizione familiare resta un’assunzione del modello.
        </p>
        {validation.loading && <p role="status">Calcolo dei confronti…</p>}
        {validation.error && (
          <p role="alert">
            {validation.error} <button onClick={validation.retry}>Riprova</button>
          </p>
        )}
        <div className="validation-cards">
          {validation.data?.map((v) => (
            <div key={v.kind}>
              <span className={`check-mark ${v.mismatched_cells ? 'failed' : ''}`}>
                {v.mismatched_cells ? '!' : '✓'}
              </span>
              <h3>{kinds[v.kind]}</h3>
              <strong>{number.format(v.cells)}</strong>
              <span>celle confrontate</span>
              <dl>
                <dt>Conteggio fonte</dt>
                <dd>{number.format(v.expected)}</dd>
                <dt>Conteggio sintetico</dt>
                <dd>{number.format(v.actual)}</dd>
                <dt>Scostamento massimo</dt>
                <dd>{number.format(v.max_absolute_error)}</dd>
              </dl>
            </div>
          ))}
        </div>
        {municipality ? (
          <div className="comparison">
            <label>
              Esamina i conteggi di {municipality.name}
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                {Object.entries(kinds).map(([k, title]) => (
                  <option key={k} value={k}>
                    {title}
                  </option>
                ))}
              </select>
            </label>
            {comparison.loading && <p role="status">Caricamento dei conteggi…</p>}
            {comparison.error && (
              <p role="alert">
                {comparison.error} <button onClick={comparison.retry}>Riprova</button>
              </p>
            )}
            <div className="comparison-scroll">
              <table>
                <thead>
                  <tr>
                    {[
                      ['category', 'Categoria'],
                      ['sex', 'Sesso'],
                      ['expected', 'Fonte'],
                      ['actual', 'Popolazione'],
                    ].map(([field, label]) => (
                      <SortHeader
                        key={field}
                        field={field}
                        label={label}
                        sort={sort}
                        onSort={setSort}
                      />
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={`${r.sex}-${r.category}`}>
                      <td>
                        {kind === 'citizenship'
                          ? String(
                              (evidence.provenance.country_labels as Record<string, string>)?.[
                                String(r.category).padStart(3, '0')
                              ] ?? r.category,
                            )
                          : r.category}
                        {(kind.endsWith('age') && r.category === 100) ||
                        (kind === 'household_size' && r.category === 6)
                          ? '+'
                          : ''}
                      </td>
                      <td>{r.sex === '*' ? 'Totale' : r.sex}</td>
                      <td>{number.format(r.expected)}</td>
                      <td>{number.format(r.actual)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <p className="method-hint">
            Seleziona un comune in «Esplora» per confrontare anche le singole celle.
          </p>
        )}
      </section>
      <section className="method-sources">
        <span className="eyebrow">PROVENIENZA DELLO SNAPSHOT</span>
        <h2>Le fonti utilizzate</h2>
        <p>
          Gli originali e i contratti sono identificati tramite checksum. I collegamenti portano
          alle risorse della fonte utilizzate dalla pipeline.
        </p>
        <div className="source-grid">
          {sources
            .filter((s) => sourceNames[s.name])
            .map((s) => (
              <a
                key={`${s.group}-${s.name}`}
                href={s.url.startsWith('https://') ? s.url : undefined}
                target="_blank"
                rel="noreferrer"
              >
                <span>ISTAT ↗</span>
                <strong>{sourceNames[s.name]}</strong>
                <small className="mono">SHA-256 {s.sha256.slice(0, 16)}…</small>
              </a>
            ))}
        </div>
        <details>
          <summary>Tutti gli originali e metadati ({sources.length})</summary>
          <ul>
            {sources.map((s) => (
              <li key={`${s.group}-${s.name}`}>
                <a
                  href={s.url.startsWith('https://') ? s.url : undefined}
                  target="_blank"
                  rel="noreferrer"
                >
                  {s.group} / {s.name} ↗
                </a>
                <code>{s.sha256}</code>
              </li>
            ))}
          </ul>
        </details>
      </section>
      <section className="method-repro">
        <div>
          <span className="eyebrow">RIPRODUCIBILITÀ</span>
          <h2>Un risultato, una storia verificabile.</h2>
          <p>
            Il workflow completo di generazione è disponibile su GitHub: acquisizione, contratti
            degli input, modello, checkpoint e verificatore indipendente.
          </p>
          <a
            className="primary-link"
            href={`${repositoryUrl}/blob/main/docs/population.md`}
            target="_blank"
            rel="noreferrer"
          >
            Apri workflow e documentazione ↗
          </a>
        </div>
        <dl>
          <dt>Snapshot della generazione</dt>
          <dd className="mono">{evidence.run_id}</dd>
          <dt>Manifest SHA-256</dt>
          <dd className="mono">{evidence.manifest_sha256}</dd>
          <dt>Algoritmo</dt>
          <dd>{String(evidence.provenance.algorithm ?? '—')}</dd>
          <dt>Adulti senza assegnazione familiare</dt>
          <dd>
            {typeof evidence.report.unassigned_adults === 'number'
              ? number.format(evidence.report.unassigned_adults)
              : 'Non disponibile'}
          </dd>
        </dl>
      </section>
      <footer className="method-footer">
        Fonti ISTAT,{' '}
        <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">
          CC BY 4.0
        </a>{' '}
        · Codice Apache-2.0
      </footer>
    </article>
  );
}
