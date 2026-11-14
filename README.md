# KamNaSutaz

Statický prehľad nadchádzajúcich súťaží. Stránka načíta CSV súbory v `data/`,
zoradí udalosti podľa dátumu a zobrazí odkaz na detail každej súťaže.

## Spustenie

Otvorte `index.html` cez statický webový server alebo publikujte koreň
repozitára cez GitHub Pages. Na lokálne testovanie môžete použiť napríklad
`python -m http.server`.

## Automatická aktualizácia

Každý zdroj má samostatný scraper a GitHub Actions workflow, ktorý beží denne
a možno ho spustiť aj ručne. Každé úspešné spustenie uloží samostatný CSV súbor
v `data/`, ktorého názov obsahuje identifikátor zdroja a UTC čas scrape-u
(napríklad `los-sk_20261114T041700000000Z.csv`). Stabilný JSON súbor pre každý
zdroj ukazuje na najnovší CSV a uchováva čas posledného úspešného behu aj stav
posledného pokusu; stránka načíta iba najnovšie CSV.
Každý zdroj má vlastnú lokálnu SVG ikonu v `assets/icons/`; stránka nenačítava
favicony ani obrázky z externých serverov.

Stavové boxy sú zelené pri úspechu v poslednom týždni, žlté pri staršom
úspešnom behu bez novšieho zlyhania a červené, ak posledný pokus zlyhal.
Zobrazený čas je vždy čas posledného úspešného behu (nie zmena obsahu CSV);
pri chybe sa navyše zobrazí čas neúspešného pokusu.

Podporované zdroje sú LOS-SK, SQUAD, Shooting Area a SADS. LOS-SK dátumy číta
vo formáte `D.M.YYYY` (ak sú hodnoty dvojciferné, aj `DD.MM.YYYY`) a zapisuje
ich ako `YYYY-MM-DD` do CSV. Rovnaký dátum a miesto sa pri zobrazení považujú
za možnú duplicitu a zobrazia sa iba raz. Scrapers používajú iba Python
štandardnú knižnicu a pri zmene očakávanej štruktúry zdrojovej stránky skončia
chybou namiesto prepísania údajov neúplným výsledkom.
