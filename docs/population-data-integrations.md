# Popolazione virtuale — integrazioni di dati esterni

Aggiornato al 24 settembre 2026. Questo documento riepiloga le integrazioni
di dati esterni per la popolazione virtuale, con il loro stato effettivo.

**Quattro integrazioni completate: sesso ed età, geografia amministrativa,
famiglie e cittadinanza.**

| Passaggio | Dati esterni | Utilizzo nella sintesi | Stato |
|---|---|---|---|
| **1. Sesso ed età** | Conteggi ISTAT per comune, sesso e singola età al **1° gennaio 2025** | Determinano quanti individui virtuali generare in ciascuna cella comune–sesso–età | **Integrati** |
| **2. Geografia amministrativa** | Codici e gerarchia ISTAT al **1° gennaio 2025** | Assegnano comune, provincia/UTS e regione agli individui virtuali | **Integrata** |
| **3. Famiglie** | Conteggi censuari ISTAT per comune e numero di componenti al **31 dicembre 2024** | Determinano numero e dimensioni delle famiglie sintetiche | **Integrate** |
| **4. Cittadinanza** | Fonti ISTAT **STR** e **RCS** al **1° gennaio 2025** | Assegnano una categoria di cittadinanza a ogni individuo, conservando i margini STR/RCS e tutti gli attributi M4 | **Integrata** |

I primi tre passaggi sono operativi nel riferimento nazionale
[M4](synthesis-m4.md), dopo il [pilota M3](synthesis-m3.md) in Valle d'Aosta.
Fonti, riferimenti e checksum M4 sono fissati nel
[contratto degli input](../contracts/istat-m4-national-v1.json).

Per le famiglie, l'appartenenza dei componenti è sintetica e vincolata allo
stesso comune; la classe osservata 6+ è rappresentata con 6 componenti.
Non sono integrate relazioni di parentela osservate.

Per la cittadinanza sono state integrate due fonti complementari:

- [STR — Popolazione straniera residente](https://demo.istat.it/app/?i=STR&a=2025&l=it):
  stranieri complessivi per comune, sesso ed età.
- [RCS — Popolazione residente per cittadinanza o paese di nascita](https://demo.istat.it/app/?i=RCS&a=2025&l=it):
  conteggi per comune, sesso e singola cittadinanza.

I file riconciliano esattamente con M4. La [nuova versione arricchita](citizenship.md)
assegna `citizenship_code` a tutti i **58.943.464 individui**: 53.572.213 nella
categoria italiana e 5.371.251 nella popolazione straniera, inclusi 525 apolidi.
La base M4 originale è conservata immutabile.
L'associazione fra età e specifica cittadinanza è sintetica e documentata:
questo incrocio non è osservato nelle tavole disponibili.

La riconciliazione dei totali, gli audit e i test sono **verifiche trasversali**,
non ulteriori passaggi di integrazione. Infrastruttura e sviluppo software
supportano questi passaggi. L'anno di nascita sintetico è derivato dall'età
secondo la convenzione adottata, senza una fonte esterna aggiuntiva.

Le fonti forniscono evidenze aggregate: gli individui e le famiglie generati
restano sintetici e non sono associati a persone reali.
