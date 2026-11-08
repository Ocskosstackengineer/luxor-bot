# Luxor-bot – projektjegyzet Claude Code-nak

Heti Luxor-tipp (Szerencsejáték Zrt.; 75 szám, oszloponként 4 = 20 szám; sorsolás szombat este)
és Telegram-bot GitHub Actionsön. A Kenó-bot testvérprojektje, azonos felépítéssel.
A bot üzenetei, kommentjei, dokumentációja **magyarul**.

## A játék és az adat
- Oszlopok: L 1–15, U 16–30, X 31–45, O 46–60, R 61–75. Szelvény: 5x5, oszloponként 1 lóhere.
  Kép = középső 3x3: 6 szám (U, X, O oszlop 2-2) + 3 lóhere. Keret = 14 szám + 2 lóhere
  (az L és R oszlop teljes egészében keret).
- A sorsolás addig tart, amíg valakinek telitalálata nincs: 36–51 számot húznak (átlag ~44).
- `adat.csv` = a szerencsejatek.hu `luxor.csv` formátuma, de **időrendben** (legrégebbi elöl):
  `év;hét;dátum;határszám;első kép;első keret;kihúzott db;számok húzási sorrendben`.
  2001–2004 között a dátum és a számlálók üresek/0-k. Azonosító: (év, hét), nem a dátum.
- A felhasználó eredeti exportja és a szerencsejatek.hu: legfrissebb elöl. A `lp.load_rows`
  mindig (év, hét) szerint rendez, így a sorrend mindegy.

## Fájlok
- `luxor_predict.py` – módszerek (`score`, `pick` → oszloponként 4 + kép javaslat), `first36`,
  `hyper` (hipergeometrikus várható érték/szórás), CLI + backtest.
- `luxor_bot.py` – források, tipp, kiértékelés (találat, kép/keret/telitalálat húzásszáma),
  parancsok, ütemezés (`--once cron`). Token: `LUXOR_BOT_TOKEN` env/secret.
- `.github/workflows/luxor.yml` – `workflow_dispatch` (ezt hívja a cron-job.org) + tartalék
  `schedule`; futás után állapot-commit (mindig a friss `main`-ből).

## Ütemezés
- **Fő indító: cron-job.org**, a GitHub API-n (`POST .../actions/workflows/luxor.yml/dispatches`,
  törzs `{"ref":"main"}`, fine-grained token, jogosultság: Actions: write). Időpontok budapesti
  idő szerint: szombat **9:30** tipp (`tip_time: "09:30"`); szombat **19:00–23:40 20 percenként**
  eredmény (a bot `result_time` 19:30-tól keres); vasárnap **8:00 és 10:00** pótlás; naponta
  **13:00** parancsok (a Telegram a ki nem olvasott üzeneteket csak 24 óráig őrzi, ezért kell
  minden nap legalább egy futás).
- **Tartalék: a `luxor.yml` `schedule`-ja**, csak `50 7,8 * * 6` (szombat; télen 8:50/9:50,
  nyáron 9:50/10:50) és `12 9,10 * * 0` (vasárnap; télen 10:12/11:12, nyáron 11:12/12:12) –
  mindig a cron-job.org-os időpont UTÁN. Szombat esti tartalék nincs: a vasárnapi futás pótol.
- Kb. 30 futás/hét (tartalékkal), ~125 Actions-perc/hó.
- Kézi indítás: **Run workflow** (a „Re-run” a régi commitból indul, ne azt használd).

## Források (`source_url` lista)
1. `cmsfiles/luxor.csv` – teljes történet számlálókkal, késve frissülhet.
2. `jatekok/luxor/sorsolasok` – legutóbbi húzás: „46. hét - november 14. (szombat)” + számok.
   Évszám nincs: dátumból, évfordulón hét alapján korrigálva. Számlálók nélkül (0) kerül be;
   az `upgrade_counters` a következő eredménykeresésnél pótolja a CSV-ből.
`parse_source` kezeli a CSV-t, egy cmsfiles/luxor.html-szerű táblázatot és a sorsolási oldalt.
Élesben ellenőrizve (2026-11-08, a felhasználó gépéről): mindkét URL 200-at ad `User-Agent:
Mozilla/5.0`-val. A CSV 1311 sora pontosan egyezik az `adat.csv`-vel (a CSV legfrissebb elöl,
BOM-mal). A sorsolási oldalról a legutóbbi húzás (2026/45.) helyesen jön ki, a számsorrend
**azonos a CSV húzási sorrendjével**. Az oldalon a következő hét fejléce („46. hét”) számok
nélkül szerepel – ezt a parser helyesen kihagyja. Ha a bot nem talál eredményt, először a
`parse_source`-t kell ellenőrizni a valódi HTML-lel (az oldal szerkezete változhat).

## Logika / buktatók
- Az `adat.csv` hetei **ISO-hetek** (mind az 1149 dátumos sornál ellenőrizve), ezért a
  `tip_key(t)` = a `for_draw` dátum `isocalendar()` (év, hét) párja; a `/eredmeny` is így kulcsol.
- `make_tip`: a tipp a sorsolás dátumából vetett véletlenmaggal készül → ugyanarra a
  sorsolásra mindig ugyanaz. Ha a nyitott tipp egy múltbeli sorsolásé, és a sorsolás másnapja
  (pótlási nap) is elmúlt: `skipped`, és új tipp készül. A sorsolás másnapján a régi tippet
  küldi újra (még jöhet az eredmény). Régen a „nőtt-e az adatfájl” volt a feltétel – ez egy
  kimaradt eredmény után a múlt heti tippet küldte újra az új helyett (javítva 2026-11-08).
- `check_result` csak a tipp SAJÁT hetével (`key(row) == tip_key(t)`) értékel, a helyi adatban
  is keres (ha egy korábbi futás elmentette, de nem értékelte). Egy késve érkező régebbi húzás
  csak az adatba kerül; ha a forrásban már későbbi hét van, de a tippé nincs: `skipped`.
- `evaluate`: a várható érték hetente a kihúzott számok darabszámától függ (`hyper(k)`), a z
  ezek összegéből számol.

## Elemzési eredmények (1311 hét, 2001–2026)
- Véletlenségi tesztek mind rendben: gyakoriság az első 36 húzásban (p=0,50), szám–pozíció
  függetlenség (p=0,48), egymást követő hetek átfedése, késleltetések, párok, időbeli sodródás.
- A sorsolás vége (37+. szám, leállító golyó) sem mutat szelvényhatást (p=0,97 / 0,46).
- Walk-forward backtest (1011 hét, 19 stratégia): semmi nem tér el a véletlentől. A legjobb
  és a legrosszabb |z| (2,2 / 2,8) ugyanilyen szimulált véletlen adaton az esetek 7,5–12,5%-ában
  kijön. A `kerules` egy másik véletlen döntetlen-feloldással z=+0,77 – zaj.
- A bot ezért minden tipp mellé véletlen kontrollt is sorsol, és a `/stat` z-értéket ad.
