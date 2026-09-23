# ADR 0006 — release ISTAT, snapshot territoriali e API v2

Stato: adottata per M1. Data: 23 settembre 2026.

## Contesto

Il campione regionale ha 21 righe, un solo istante e valori senza flag ISTAT.
La v1 ammette cinque stati chiusi: aggiungerne uno senza versione può rompere
client esaustivi. Il catalogo non distingueva revisioni né aggiornamento upstream;
la sola chiave territoriale non impediva intervalli sovrapposti.

## Decisione

API v2 per release arricchite e stato `unflagged_upstream`; v1 continua a esporre
solo release compatibili. Il frontend usa v2 anche per la demo.
Metadati di release aggiuntivi: impronta dei metadati, date upstream nullable,
serie, snapshot, predecessore e motivazione. Una revisione non modifica la precedente.
Lock per dataset/periodo e predecessore atteso impediscono rami concorrenti.

L'identità include dati, contratto di onboarding, contratto di pubblicazione,
trasformazione e metadati XML canonici senza Header SDMX (timestamp di risposta).
Gli originali completi, inclusi gli Header, restano archiviati. Timestamp di
acquisizione diversi da soli non creano nuove release. La prima acquisizione
pubblicata resta la provenienza della release; ogni tentativo ha un run separato.

I territori sono snapshot della selezione revisionata, con validità di un giorno,
gerarchia Italia/regioni e namespace derivato dal contenuto della definizione.
Una definizione modificata richiede un nuovo namespace; non si estende una
validità temporale per supposizione e non si inventano crosswalk.

Abilitare `btree_gist`, modulo distribuito con PostgreSQL, per un vincolo di
esclusione su schema/codice/intervallo. La necessità è verificabile con due
inserimenti concorrenti sovrapposti: uno deve fallire anche fuori dalla pipeline.
[Documentazione PostgreSQL 17](https://www.postgresql.org/docs/17/btree-gist.html),
[vincoli su intervalli](https://www.postgresql.org/docs/17/rangetypes.html#RANGETYPES-CONSTRAINT).

## Alternative e conseguenze

Un controllo solo Python non protegge altre scritture o gare concorrenti.
Classificare l'assenza di flag come osservazione diretta altererebbe il significato.
Estendere retroattivamente v1 cambierebbe il suo enum; mantenerla evita tale rottura.
La validità di un giorno limita deliberatamente il riuso: M2 dovrà introdurre
evidenze territoriali storiche e mapping fusioni/scissioni prima di altre date.
L'estensione e gli indici vengono verificati su PostgreSQL/PostGIS reale;
nessuna affermazione di capacità nazionale deriva da questa decisione.
