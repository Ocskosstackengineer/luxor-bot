# Luxor Telegram-bot (GitHub Actions)

Heti Luxor-tipp és kiértékelés. A GitHub szerverein fut, a gépednek nem kell bekapcsolva lennie.
A futásokat a **cron-job.org** indítja (budapesti idő szerint); a GitHub saját ütemezése csak
tartalék.

- **Szombat 9:30:** tipp – oszloponként 4 szám (L U X O R), plusz hogy melyik 6 kerüljön a
  középső 3x3-as „képbe” (az U, X, O oszlop 2-2 száma), és egy véletlen kontroll-tipp.
- **Szombat 19:00–23:40 között 20 percenként** (a bot 19:30-tól keres): a szerencsejatek.hu
  sorsolási oldaláról és a `luxor.csv`-ből keresi az eredményt. Ha megvan: találatok oszloponként, hányadik húzásnál
  lett volna meg a kép / keret / telitalálat (a sorsolás első kép- és keret-nyertesével
  összevetve, ha ismert), és futó összesítés a véletlen kontrollal és az elmélettel.
- **Vasárnap 8:00 és 10:00:** pótolja a késve megjelenő eredményt; ha addig sincs, a
  következő szombati tipp előtt.
- **Naponta 13:00:** Telegram-parancsok feldolgozása.
- Az új húzásokat és az állapotot (`adat.csv`, `bot_state.json`) visszamenti a repóba.

## Beüzemelés

1. **Új bot** a @BotFather-nél (`/newbot`), és írj neki egy `/start`-ot. Külön bot kell, mint a
   Kenóhoz: két program nem olvashatja ugyanannak a botnak a parancsait.
2. Privát repó (pl. `Ocskosstackengineer/luxor-bot`), a mappa feltöltése a `.github`-bal együtt.
3. Settings → Secrets and variables → Actions → New repository secret:
   `LUXOR_BOT_TOKEN` = az új bot tokenje.
4. Actions → luxor-bot → Run workflow. Szombat 9:30 után azonnal jön a tipp; más napokon a
   `/tipp` paranccsal kérhető (a következő parancsfeldolgozáskor – naponta 13:00-kor –,
   vagy egy újabb Run workflow-val).
5. **Ütemezés a cron-job.org-on.** GitHubon: Settings → Developer settings → Personal access
   tokens → **Fine-grained token**, csak ehhez a repóhoz, jogosultság: **Actions: Read and
   write**. A cron-job.org-on (időzóna: Europe/Budapest) a jobok:
   - URL: `https://api.github.com/repos/Ocskosstackengineer/luxor-bot/actions/workflows/luxor.yml/dispatches`
   - metódus `POST`, törzs: `{"ref":"main"}`
   - fejlécek: `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`
   - időpontok: szombat **9:30**; szombat **19:00–23:40 között 20 percenként**;
     vasárnap **8:00** és **10:00**; naponta **13:00**.

   Sikeres indításnál a GitHub `204`-et ad vissza.

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

- A cron-job.org percre pontosan indít; a GitHub saját ütemezése 5-30 percet késhet, és ki is
  maradhat. A `luxor.yml` `schedule`-ja ezért csak tartalék, mindig a cron-job.org-os időpont
  után: szombat 7:50 és 8:50 UTC (télen 8:50 és 9:50, nyáron 9:50 és 10:50 budapesti idő –
  a tipp 9:30 utáni futás számít), vasárnap 9:12 és 10:12 UTC (télen 10:12 és 11:12, nyáron
  11:12 és 12:12). Szombat esti tartalék nincs: a kimaradt eredményt a vasárnapi futás hozza be.
- **Kézi futtatás:** Actions → luxor-bot → **Run workflow**. A „Re-run jobs” ne – az a régi
  commitból indul.
- Kb. 30 futás hetente (a tartalékkal együtt), havonta ~125 Actions-perc (a GitHub Free privát
  repókra havi 2000-et ad, a szervezet összes privát repójára közösen – a Kenó-bot ~450-et
  használ).
- A kép/keret kiértékelés a bot javasolt elrendezésére vonatkozik (a kép = a javasolt 6 szám).
  Ha a szelvényen máshová kerülnek a számok, a kép/keret eredmény eltérhet; a 20 számos
  találat és a telitalálat ettől független.
- A Telegram a ki nem olvasott üzeneteket 24 óráig őrzi; a bot naponta legalább egyszer
  (13:00-kor) olvassa a parancsokat, így egy parancs sem vész el, de a válasz akár egy napot
  is késhet.
- Ha egy sorsolás eredménye vasárnap délig sem jön meg, a tipp kiértékelés nélkül lezárul,
  és a következő szombaton új tipp készül (a késve érkező régi húzás csak az adatba kerül).
