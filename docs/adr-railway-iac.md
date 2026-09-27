# ADR: configurazione Railway versionata

Stato: accettata, 26 settembre 2026.

## Contesto

Le impostazioni applicate via CLI devono essere revisionabili e ripetibili.
Railway ha deprecato `railway.json`; la sua CLI richiede il pacchetto `railway/iac`
per valutare la configurazione TypeScript.

## Decisione

Usare `.railway/railway.ts` con SDK `railway` 3.11.0, dipendenza di sviluppo
isolata in `.railway/package.json` e bloccata dal relativo lockfile.
Non entra nelle immagini, nel backend o nel bundle frontend. L'installazione
usa `npm --prefix .railway ci --ignore-scripts`.

Il partial `itadb` gestisce API e volume esistenti. Regione, risorse, comando,
healthcheck e limiti DuckDB sono espliciti. L'origine CORS viene preservata;
il repository GitHub arriva da `ITADB_GITHUB_REPOSITORY`, senza identità in Git.
I domini generati restano gestiti dal provider. I piani non devono cancellare
risorse, variabili o volumi. Le modifiche infrastrutturali richiedono un piano
revisionato prima di `apply`; il codice applicativo continua a essere distribuito
dal collegamento GitHub dopo la CI.

## Conseguenze

Una dipendenza di soli strumenti sostituisce impostazioni manuali non tracciate.
Non servono nuovi servizi né dipendenze runtime. I piani e gli identificativi
cloud restano locali in `.tools/`. La sola modifica del file IaC non applica
automaticamente un nuovo piano: eseguire la procedura di [deployment](deployment.md).
La popolazione viene recuperata dalla copia locale o rigenerata; nessun backup
cloud è previsto.

[Documentazione Railway IaC](https://docs.railway.com/infrastructure-as-code).
