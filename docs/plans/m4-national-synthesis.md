# M4 — piano e registro di completamento

Stato: **implementazione e verifiche locali completate; consegna tramite PR**.
La richiesta dell'utente autorizza sviluppo, branch dedicato, commit e PR
riallineata a main. Nessun agente parallelo è stato avviato.

## Risultato conseguito

Riferimento unico `m4-reference/1`, popolazione 01/01/2025 e famiglie
31/12/2024: 58.943.464 persone virtuali, 26.670.169 famiglie e residuo
esplicito di 560.159 adulti. 7.896 comuni, 107 province/UTS, 20 regioni.
Seed 1701, classe 6+ = 6; priorità M3 conservate. Coorti stabili, 100+ aperto.

[Metodo e riproduzione](../synthesis-m4.md),
[decisione architetturale](../adr/0012-national-territorial-snapshots.md),
[valutazione statistica/disclosure](../reviews/m4-disclosure.md),
[misure](../benchmarks/m4-national-2026-09-24.json).

## Passi verificati

1. Inventario selettivo: famiglie disponibili fino al 2024; POSAS 2025 e
   geografia 2025. Confronto di 612 celle POSAS/SDMX esatto prima del download
   nazionale. Le richieste SDMX troppo lunghe/non rispondenti sono abbandonate
   a favore dell'archivio ufficiale POSAS da 8,5 MB, senza rilassare i controlli.
2. Contratto immutabile di 15 originali. Ammesse tutte le celle comunali,
   riconciliate con congiunte provinciali, regionali/nazionali e classi
   familiari di tutti i livelli. Nessun uso implicito di stime o soppressioni.
3. Generatore vettoriale e audit SQL indipendente: 107 batch, 214 Parquet,
   1.594.992 celle demografiche comunali esatte. Famiglie nello stesso comune,
   minori assegnati, residuo incluso nei totali geografici.
4. Riproducibilità al cambio dell'ordine dei batch; checkpoint, recupero dopo
   interruzione a 10M, retry nazionale identico, file corrotti rifiutati,
   fallimenti senza snapshot completo. Originali e tentativi conservati.
5. Prove effettive 1M, 10M e nazionale entro budget preventivi: 8 GiB RSS,
   40 GiB disco per prova, due ore. Nazionale: 177,61 s nel runner monitorato,
   picco RSS 1,09 GiB; audit successivo 28,65 s. Nessuna estrapolazione.
6. Valutazione statistica e disclosure tecnica, formato Parquet locale e JSON
   aggregato implementati. 400 celle regionali condivisibili come formato
   proposto, minimo 483; tutti gli artefatti restano `public_release=false`.
7. 219 test Python, 38 integrazioni PostgreSQL, 17 test web, Ruff/mypy,
   typecheck/build/format frontend; OpenAPI e tipi rigenerati senza differenze.

## Visibilità e provenienza

Terminale aperto su `.tools/m4-progress.log`; wrapper con heartbeat, fasi,
conteggi ed esiti. Log, report di ammissione, checkpoint e misure sono conservati
localmente e non inclusi in Git. Ryzen 9 9900X, 24 processori logici, circa
61 GiB RAM; ambiente e hash dei sorgenti effettivi nel manifest. Sorgenti
archiviati prima del commit, working tree dirty dichiarato.

## Confini e chiusura della revisione

La PR sottopone alla revisione di progetto il formato e l'ambito di
condivisione; nessun dataset viene pubblicato automaticamente. La revisione
scientifica esterna e l'autorizzazione alla distribuzione pubblica dei
microdati non sono state svolte e restano distinte dal completamento tecnico.
La composizione familiare casuale non è validata su relazioni osservate;
questi limiti non vengono trasformati in risultati positivi della milestone.

Consegna: revisione del diff, commit sul branch `feat/m4-national-synthesis`,
rebase su `origin/main`, push e PR; controllo della CI della PR.
