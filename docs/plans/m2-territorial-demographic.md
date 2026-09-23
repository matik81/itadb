# M2 — copertura territoriale e demografica

## Risultato richiesto

Estendere le evidenze aggregate a territori versionati, variazioni e crosswalk,
confini verificati, popolazione per sesso/età, famiglie e abitazioni. Rendere
consultabili provenienza e copertura senza sommare totali e dettagli sovrapposti.
Non generare individui sintetici (M3/M4).

## Fasi e criteri di uscita

1. Verificare fonti ufficiali, licenze e selezioni limitate; fissare nel contratto
   periodi, dimensioni, gerarchie e vintage. Archiviare originali e metadati.
2. Nuova migrazione, mai riscrittura di revisioni applicate: copertura multisérie,
   storia territoriale, eventi e crosswalk, geometrie e protezione delle evidenze.
3. Pipeline riproducibile con gate di copertura, additività e riconciliazione;
   pubblicazione atomica e idempotente, quarantena degli errori.
4. API con filtri obbligatori e pagine limitate; web con scelta di periodo/serie,
   provenienza e limiti espliciti. Rigenerazione OpenAPI/tipi.
5. Test offline, integrazione PostgreSQL/PostGIS e upgrade con dati preesistenti;
   benchmark su volume aggregato rappresentativo, piani di query e risorse misurate.
6. Documentazione delle verifiche realmente eseguite, commit su branch dedicato,
   rebase su origin/main, PR e verifica CI.

## Decisioni e rischi da risolvere

- Nessuna interpolazione tra confini o periodi implicita; un crosswalk strutturale
  non autorizza una ripartizione della popolazione senza pesi documentati.
- Le diverse definizioni di famiglia/abitazione devono rimanere distinguibili.
- I test usano fixture dichiarate inventate; le prove live hanno evidenze locali
  escluse da Git. La copertura ufficiale effettiva sarà dichiarata nel rapporto.
- Operazioni lunghe: terminale di avanzamento e log persistente in `.tools/`.

## Stato

Fasi 1–6 completate sul branch `feat/m2-territorial-demographic-coverage`:
[PR #13](https://github.com/matik81/itadb/pull/13).
Fonti, perimetro e derivazioni sono in `docs/sources/istat-m2.md`; esiti dei test,
backup/restore, pubblicazione Windows/Linux e HTTP in `docs/validation.md`;
benchmark del milione di aggregati in `docs/benchmarks/m2.md`.

La verifica visiva interattiva è stata completata tramite Playwright e Chrome,
su dati ufficiali nello stack locale, anche a viewport di 320/390/768 px.
Corretti richieste duplicate dei metadati e troncamento della categoria su mobile;
verificati filtri, paginazione, collegamenti, tastiera e recupero dagli errori.
Esiti ed evidenze sono descritti in `docs/validation.md`; l'esito remoto è tracciato
nei check della PR. La direttiva sulle operazioni lunghe è stata salvata anche nelle
istruzioni generali locali, oltre ad AGENTS.md.
