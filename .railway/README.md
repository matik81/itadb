# Configurazione Railway

Il partial `itadb` in `railway.ts` gestisce API e volume persistente.
Le dipendenze degli strumenti sono isolate in questa directory.

```sh
npm --prefix .railway ci --ignore-scripts
export ITADB_GITHUB_REPOSITORY=GITHUB_OWNER/GITHUB_REPOSITORY
railway config plan
railway config apply --yes
railway config plan --detailed-exit-code
```

Sostituire il segnaposto localmente. Prima di `apply`, verificare progetto,
ambiente e piano: nessuna cancellazione, cambio regione o perdita del
collegamento GitHub. Non usare `--confirm-destructive`.
CORS e dominio generato vengono conservati sul provider. Non aggiungere
identità, credenziali o piani generati ai file versionati.

Un push aggiorna il codice applicativo tramite il collegamento GitHub.
Le modifiche a questo file richiedono un `plan` e un `apply` separati.
Vedi [deployment](../docs/deployment.md) e [decisione tecnica](../docs/adr-railway-iac.md).
