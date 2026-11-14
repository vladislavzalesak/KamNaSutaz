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
Workflow `Scrape all event sources` umožňuje ručne spustiť všetky štyri
scrapery naraz; denné aktualizácie zostávajú samostatné pre každý zdroj.

Stavové boxy sú zelené pri úspechu v poslednom týždni, žlté pri staršom
úspešnom behu bez novšieho zlyhania a červené, ak posledný pokus zlyhal.
Zobrazený čas je vždy čas posledného úspešného behu (nie zmena obsahu CSV);
pri chybe sa navyše zobrazí čas neúspešného pokusu.

Podporované zdroje sú LOS-SK, SQUAD, Shooting Area a SADS. CSV obsahuje dátum,
názov preteku (ak ho zdroj poskytuje), miesto a odkaz. LOS-SK dátumy číta vo
formáte `D.M.YYYY` (ak sú hodnoty dvojciferné, aj `DD.MM.YYYY`) a zapisuje ich
ako `YYYY-MM-DD` do CSV. Rovnaký dátum a miesto sa pri zobrazení považujú za
možnú duplicitu a zobrazia sa iba raz. Scrapery používajú Python štandardnú
knižnicu, `certifi` na doplnenie CA certifikátov pri overovaní HTTPS a `tzdata`
pre systémy bez systémovej databázy časových pásiem. SQUAD momentálne
neposiela celý TLS certifikačný reťazec; `scripts/certs/squad-ca-chain.pem`
dopĺňa reťazec publikovaný Let’s Encrypt a TLS overovanie zostáva zapnuté. Ak
SQUAD zmení certifikačnú autoritu, tento doplnkový reťazec bude treba obnoviť.
Závislosti sa inštalujú príkazom
`python -m pip install --upgrade -r requirements.txt`. Pri zmene očakávanej
štruktúry zdrojovej stránky scrapery skončia chybou namiesto prepísania údajov
neúplným výsledkom.
