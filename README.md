# Luxor Telegram-bot (GitHub Actions)

Heti Luxor-tipp és kiértékelés. A GitHub szerverein fut, a gépednek nem kell bekapcsolva lennie.

- **Szombat ~9:10:** tipp – oszloponként 4 szám (L U X O R), plusz hogy melyik 6 kerüljön a
  középső 3x3-as „képbe” (az U, X, O oszlop 2-2 száma), és egy véletlen kontroll-tipp.
- **Szombat 19:30-tól 20 percenként:** a szerencsejatek.hu sorsolási oldaláról és a
  `luxor.csv`-ből keresi az eredményt. Ha megvan: találatok oszloponként, hányadik húzásnál
  lett volna meg a kép / keret / telitalálat (a sorsolás első kép- és keret-nyertesével
  összevetve, ha ismert), és futó összesítés a véletlen kontrollal és az elmélettel.
- **Vasárnap délig:** pótolja a késve megjelenő eredményt; ha addig sincs, a következő
  szombati tipp előtt.
- Az új húzásokat és az állapotot (`adat.csv`, `bot_state.json`) visszamenti a repóba.

## Beüzemelés

1. **Új bot** a @BotFather-nél (`/newbot`), és írj neki egy `/start`-ot. Külön bot kell, mint a
   Kenóhoz: két program nem olvashatja ugyanannak a botnak a parancsait.
2. Privát repó (pl. `Ocskosstackengineer/luxor-bot`), a mappa feltöltése a `.github`-bal együtt.
3. Settings → Secrets and variables → Actions → New repository secret:
   `LUXOR_BOT_TOKEN` = az új bot tokenje.
4. Actions → luxor-bot → Run workflow. Szombat 9:00 után azonnal jön a tipp; más napokon a
   `/tipp` paranccsal kérhető (a következő parancsfeldolgozáskor – naponta kétszer, télen
   7:42 és 19:42, nyáron 8:42 és 20:42 körül –, vagy egy újabb Run workflow-val).

## Helyi próba (Windows, PowerShell)

    pip install -r requirements.txt
    python luxor_bot.py --dry-run --once tipp
    python -c "import luxor_bot as b; c=b.load_config('config.json'); r=b.fetch_remote(c); print(len(r), r[-1]['date'], r[-1]['nums'][:10])"

Az utolsó parancsnak a legfrissebb szombati húzást kell kiírnia mindkét forrásból
(a naplóban forrásonként egy `forrás: ... -> N húzás` sor).

## Parancsok

- `/tipp` – a következő sorsolásra szóló tipp
- `/eredmeny 53 72 50 4 ...` – kézi eredménymegadás, az összes kihúzott szám húzási sorrendben
- `/stat` – összesítés
- `/help`

## Tudnivalók

- A GitHub ütemezett futásai 5-30 percet késhetnek.
- Kb. 38 futás hetente, havonta ~165 Actions-perc (a GitHub Free privát repókra havi 2000-et ad,
  a szervezet összes privát repójára közösen – a Kenó-bot ~700-at használ).
- A kép/keret kiértékelés a bot javasolt elrendezésére vonatkozik (a kép = a javasolt 6 szám).
  Ha a szelvényen máshová kerülnek a számok, a kép/keret eredmény eltérhet; a 20 számos
  találat és a telitalálat ettől független.
- A Telegram a ki nem olvasott üzeneteket 24 óráig őrzi; a bot naponta kétszer olvassa a
  parancsokat, így egy parancs sem vész el, de a válasz akár 12 órát is késhet.
- Ha egy sorsolás eredménye vasárnap délig sem jön meg, a tipp kiértékelés nélkül lezárul,
  és a következő szombaton új tipp készül (a késve érkező régi húzás csak az adatba kerül).
