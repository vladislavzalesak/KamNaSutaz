# KamNaSutaz

Statický prehľad nadchádzajúcich súťaží. Stránka načíta zverejnené CSV súbory
z `data/`, zoradí udalosti podľa dátumu a zobrazí odkaz na detail každej súťaže.

## Spustenie

GitHub Pages publikuje stránku aj aktuálne dáta z GitHub Actions. V nastaveniach
repozitára v časti **Settings → Pages → Build and deployment** nastavte zdroj
na **GitHub Actions**.

Na lokálne testovanie nainštalujte závislosti, spustite scrapery a následne
statický server:

```sh
python -m pip install --upgrade -r requirements.txt
python scripts/scrape_los_sk.py
python scripts/scrape_squad.py
python scripts/scrape_shootingarea.py
python scripts/scrape_sads.py
python -m http.server
```

## Automatická aktualizácia

Workflow `Scrape and deploy event calendar` denne spustí všetky štyri scrapery
a možno ho spustiť aj ručne. Dáta sa zahrnú do GitHub Pages artefaktu a
nasadia spolu so stránkou; scraper ich už necommitne do repozitára. Pred
scrape-om workflow načíta posledné zverejnené manifesty a CSV súbory, takže pri
zlyhaní zdroja zostanú jeho posledné úspešné dáta dostupné. Každý manifest
uchováva čas posledného úspešného behu aj stav posledného pokusu; stránka
načíta iba najnovší CSV pre každý zdroj. Staršie CSV snímky sa v nasadení
neuchovávajú.
Pre plánované spustenia musí byť workflow v predvolenej vetve repozitára;
scrape samotný používa vetvu `v1.0`.
Každý zdroj má vlastnú lokálnu SVG ikonu v `assets/icons/`; stránka nenačítava
favicony ani obrázky z externých serverov.

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
