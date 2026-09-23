# M1 — onboarding della popolazione residente ISTAT

## Risultato e ambito

Primo incremento: selezionare un dataflow reale, acquisire un campione minimo,
conservare DSD/codelist e provenienza e rendere ripetibile la verifica offline.
Perimetro: popolazione al 1° gennaio 2024, totale sesso/età/stato civile,
20 regioni amministrative e Italia come controllo. Nessun microdato.

Questo primo incremento produce evidenze locali e non assegna lo stato `published`.
La pubblicazione in DB/API/web resta nel passaggio successivo.

## Decisioni

- Dataflow `IT1,22_289_DF_DCIS_POPRES1_1,1.0`, DSD `IT1,DCIS_POPRES1,1.0`.
- Domini espliciti derivati dalle codelist, senza dedurre i codici dalla lunghezza.
  Trentino-Alto Adige è `ITDA`; non sommare anche Trento e Bolzano.
- Periodo della richiesta `2024-01-01` per entrambi gli estremi. Nella prova live
  gli estremi `2024` hanno incluso anche il 2025: il gate rifiuta periodi aggiuntivi.
- Conservare flag e note; il primo contratto accetta solo osservazioni senza flag.
  Non convertire valori mancanti/soppressi in zero o stime in osservazioni.
- Usare lo stack esistente, senza dipendenze aggiuntive o cambiamenti al DB/API.

## Fasi e verifica

1. Verifica base locale e acquisizioni selettive: completate il 23 settembre 2026.
2. Contratto, acquisizione metadati riutilizzabile e validazione offline: completati.
3. Test senza rete di schema, domini, periodo, duplicati, flag, copertura e totali;
   ripetizione sul campione archiviato e documentazione delle evidenze: completati.
4. Incremento successivo: nuove migrazioni per revisioni e territori; adapter Parquet
   e pubblicazione atomica; test PostgreSQL di integrità, idempotenza e rollback;
   esposizione API/UI della provenienza e verifica manuale dell'interfaccia.

## Rischi e limiti

`LAST_UPDATE` del dataflow non dimostra la data di pubblicazione del singolo dato.
La versione nominale di una DSD può restare invariata: registrare anche SHA-256.
Il campione non prova validità storica di tutti i territori o prestazioni nazionali.
Nell'onboarding iniziale Docker/PostgreSQL non erano disponibili localmente e i
test di integrazione non erano stati eseguiti.
