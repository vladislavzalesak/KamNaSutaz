# KamNaSutaz

Statický prehľad nadchádzajúcich súťaží. Stránka načíta CSV súbory v `data/`,
zoradí udalosti podľa dátumu a zobrazí odkaz na detail každej súťaže.

## Spustenie

Otvorte `index.html` cez statický webový server alebo publikujte koreň
repozitára cez GitHub Pages. Na lokálne testovanie môžete použiť napríklad
`python -m http.server`.

## Automatická aktualizácia

Workflow `.github/workflows/scrape-los-sk.yml` načíta LOS-SK súťaže denne o
04:17 UTC a možno ho spustiť aj ručne z karty Actions. CSV v `data/los-sk.csv`
sa zapisuje ako commit pri každom úspešnom spustení. Stránka číta zoznam CSV
súborov v `app.js`; pri pridaní ďalšieho zdroja doplňte jeho cestu do
`csvFiles`.

LOS-SK zobrazuje dátumy ako `DD.MM.YYYY`; scraper ich normalizuje na `YYYY-MM-DD`
v CSV. Scraper používa iba Python štandardnú knižnicu a pri zmene očakávanej
štruktúry zdrojovej stránky skončí chybou namiesto prepísania údajov neúplným
výsledkom.
