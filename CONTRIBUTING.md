# Contribuire

Partire da README.md, AGENTS.md e dalla roadmap. Aprire una issue per nuove fonti o
decisioni che cambiano il modello; proporre una PR circoscritta con problema, risultato,
verifiche eseguite e limiti. Non sono richiesti servizi cloud per contribuire.

Usare Python 3.13/uv e Node 24/npm. Conservare uv.lock e package-lock.json. Eseguire i
controlli del README; le modifiche a schema/pipeline devono passare anche la CI PostGIS.
Non modificare a mano i tipi generati. Non importare dati reali nel repository.

Le fixture devono essere piccole, inventate oppure redistribuibili con licenza e fonte.
Ogni PR relativa ai dati indica DSD/contratto, unità, tempo, territorio, controlli e limiti.
I contributi di codice sono offerti con Apache-2.0. Rispettare il CODE_OF_CONDUCT.md.
