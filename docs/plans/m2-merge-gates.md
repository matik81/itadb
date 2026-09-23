# M2 — chiusura dei rilievi prima del merge

La PR #13 è bloccata da tre conversazioni: readiness incompleta, contesto dei
crosswalk non ricontrollato e gerarchia geometrica non ricontrollata alla pubblicazione.

1. Verificare tutte le viste v2 con il ruolo reader, senza scandire le evidenze.
2. Aggiungere la revisione 0005, lasciando immutate 0001–0004: ricontrollare date,
   livelli, pesi e cardinalità degli eventi; ripetere il contenimento geometrico
   con la stessa politica della pipeline (esatto per unioni, tolleranza 2% per fonti).
   Salvare la politica nel dettaglio del gate, senza cambiare evidenze già pubblicate.
3. Test PostgreSQL di regressione, upgrade ripetuto e conservazione delle release;
   backup/restore e misure del controllo sui dati M2 ufficiali locali.
4. Aggiornare la PR, risolvere i tre rilievi corretti, attendere la CI ed eseguire
   il merge con rebase in main, mantenendo le protezioni GitHub.

Stato: correzioni e verifiche locali completate (104 test offline, 38 di integrazione,
backup/restore e tre piani SQL sul perimetro ufficiale). Nessuna nuova acquisizione
o dipendenza. La chiusura della PR segue i controlli CI obbligatori su GitHub.
