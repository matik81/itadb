# Web app

- Leggi i tipi src/generated/api.ts, generati da OpenAPI; non editarli a mano.
- Mai mostrare dati mock come fallback di una richiesta fallita.
- Mostra fonte, periodo, licenza, limiti e marcatura demo in prossimità dei dati.
- Conserva stati loading, vuoto ed errore, navigazione da tastiera e layout responsivo.
- Non introdurre analytics, autenticazione o storage di dati personali senza requisito.
- Esegui npm run typecheck, npm test e npm run build nella cartella apps/web.
- Ogni tabella deve offrire ordinamento crescente/decrescente sulle colonne utili
  e filtri per selezione sui campi rilevanti. Ordinamento e filtri riguardano
  l'intero risultato, anche quando è paginato; i cambi azzerano il cursore.
- Identifica persone, famiglie e abitazioni con un'icona accanto ai valori nelle
  schede. Usa icone accessibili per il tipo di territorio accanto al nome,
  evitando colonne «Livello» che ripetono lo stesso valore su tutte le righe.
