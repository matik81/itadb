# M2 — scheda territoriale con mappa

## Risultato

Il nome del territorio apre una scheda leggibile nella web app: mappa del
confine ISTAT, osservazione selezionata, periodo, snapshot, fonte e licenza.
Il download GeoJSON è un'azione distinta. Chiudere la scheda conserva filtri,
paginazione e focus. La stessa interazione vale per regioni, province e comuni M2.

## Implementazione e verifica

- Dialog nativo accessibile e responsivo; mappa SVG dei poligoni pubblicati,
  proiezione Mercatore, zoom e spostamento. Nessuna nuova dipendenza o sorgente
  cartografica esterna; contratto API e dati pubblicati invariati.
- Caricamento, errore, geometria non disponibile e retry espliciti. Verifica
  dell'identità release/territorio; poligoni multipli e anelli interni conservati.
- Test di proiezione e componenti, typecheck, formattazione, build; Playwright
  con regioni continentali e insulari, mobile, tastiera, download e errori.
- Documentare le prove effettive, commit sul branch M2, rebase e aggiornamento PR.

Stato: implementazione e verifiche locali completate. Sedici test web passati;
Playwright ha aperto tutte le 20 regioni ufficiali, una provincia e un comune
dalla seconda pagina, verificando zoom, mouse, tastiera, touch emulato,
download, errori/retry e viewport 1440/768/390/320 px. Evidenze nel registro
`docs/validation.md`; consegna sul branch M2 e nella PR #13.

La mappa serve a consultare il confine semplificato; non è uno strumento per
misure catastali o navigazione stradale. Non sono stati usati dispositivi fisici
o motori browser diversi da Chrome.
