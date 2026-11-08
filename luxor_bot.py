"""
luxor_bot.py - heti Luxor-tipp + eredmény-kiértékelés Telegramon

Futtatás:   python luxor_bot.py --once cron            (egy ütemezett lépés: GitHub Actions)
            python luxor_bot.py                        (folyamatosan fut, helyi gépen / VPS-en)
Teszt:      python luxor_bot.py --dry-run --once tipp      (üzenet csak a konzolra)
            python luxor_bot.py --dry-run --once eredmeny

Kell hozzá: Python 3.9+, numpy, és a luxor_predict.py ugyanabban a mappában.
Token: LUXOR_BOT_TOKEN környezeti változó (GitHub secret), vagy config.json (nem ajánlott).

Telegram parancsok (csak a beállított chat ID-ról):
    /tipp                       a következő sorsolásra szóló tipp (újra)küldése
    /eredmeny 53 72 50 4 ...    a kihúzott számok kézi megadása HÚZÁSI SORRENDBEN
    /stat                       összesítés: algoritmus vs véletlen kontroll vs elmélet
    /help
"""
import argparse
import datetime as dt
import html
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request

try:  # Windows: a rendszer tanúsítványtárát használja (helyi futtatásnál hasznos)
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import numpy as np

import luxor_predict as lp

HERE = os.path.dirname(os.path.abspath(__file__))
COLS = lp.COLS
MONTHS = {"január": 1, "február": 2, "március": 3, "április": 4, "május": 5, "június": 6,
          "július": 7, "augusztus": 8, "szeptember": 9, "október": 10, "november": 11,
          "december": 12}
WEEKDAYS = ["hétfő", "kedd", "szerda", "csütörtök", "péntek", "szombat", "vasárnap"]


# ---------------------------------------------------------------- konfiguráció
def load_config(path):
    cfg = {
        "telegram_token": "",
        "chat_id": "",
        "method": "kerules",
        "draw_weekday": 5,            # 0 = hétfő ... 5 = szombat
        "tip_time": "09:00",          # tipp a sorsolás napján
        "result_time": "19:30",       # ettől keresi az eredményt a sorsolás napján
        "result_until": "12:00",      # másnap eddig keres még (utána a következő tippnél pótol)
        "result_retry_minutes": 15,
        "source_url": [
            "https://bet.szerencsejatek.hu/cmsfiles/luxor.csv",
            "https://bet.szerencsejatek.hu/jatekok/luxor/sorsolasok",
        ],
        "data_file": "adat.csv",
        "state_file": "bot_state.json",
    }
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg.update(json.load(f))
    cfg["telegram_token"] = os.environ.get("LUXOR_BOT_TOKEN") or cfg["telegram_token"]
    cfg["chat_id"] = str(os.environ.get("LUXOR_CHAT_ID") or cfg["chat_id"])
    for key in ("data_file", "state_file"):
        if not os.path.isabs(cfg[key]):
            cfg[key] = os.path.join(HERE, cfg[key])
    return cfg


def log(msg):
    print(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


# ---------------------------------------------------------------- adatok
def key(r):
    return (r["year"], r["week"])


def read_history(cfg):
    return lp.load_rows(cfg["data_file"])


def write_history(cfg, rows):
    rows = sorted(rows, key=key)
    with open(cfg["data_file"], "w", encoding="utf-8") as f:
        for r in rows:
            f.write(f"{r['year']};{r['week']};{r['date']};" + ";".join(map(str, r["counters"]))
                    + ";" + ";".join(map(str, r["nums"])) + "\n")


ROW_HEAD = re.compile(r"(?<!\d)(\d{4})\s+(\d{1,2})\s+(\d{4}\.\d{2}\.\d{2}\.?)")
LATEST_HEAD = re.compile(r"(\d{1,2})\.\s*hét\s*[-–—]\s*(" + "|".join(MONTHS) + r")\s+(\d{1,2})\.",
                         re.IGNORECASE)
NUM = r"(?<![\d.])\d{1,2}(?![\d.])"
RUN = re.compile(r"(?:" + NUM + r"[\s,;]*){30,75}")


def _valid(nums):
    return len(nums) >= lp.K36 and len(set(nums)) == len(nums) and all(1 <= n <= 75 for n in nums)


def _split_counters(ints):
    """[c1..c4, számok...] vagy csak [számok...]; a 4. számláló = a kihúzott számok darabszáma."""
    if len(ints) > 4 and ints[3] == len(ints) - 4 and _valid(ints[4:]):
        return ints[:4], ints[4:]
    if _valid(ints):
        return [0, 0, 0, 0], ints
    return None


def parse_source(text, today=None):
    """Kezeli: luxor.csv (';'), a cmsfiles/luxor.html táblázatot és a sorsolási oldal legutóbbi húzását."""
    today = today or dt.date.today()
    text = text.lstrip("﻿")
    rows = []
    if "<" not in text or ">" not in text:  # CSV
        for line in text.splitlines():
            r = lp.parse_line(line)
            if r:
                rows.append(r)
        return rows
    flat = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text)))
    # 1) táblázat: "év hét dátum [4 számláló] számok..."
    heads = list(ROW_HEAD.finditer(flat))
    for i, m in enumerate(heads):
        seg = flat[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(flat)]
        lead = re.match(r"\s*((?:\d{1,2}(?!\d)[\s,;]*)+)", seg)  # csak a sor elején álló számok
        ints = [int(x) for x in re.findall(r"\d{1,2}", lead.group(1))] if lead else []
        sc = _split_counters(ints)
        if sc:
            rows.append({"year": int(m[1]), "week": int(m[2]), "date": m[3],
                         "counters": sc[0], "nums": sc[1]})
    # 2) sorsolási oldal: "45. hét - november 7. (szombat)" + a kihúzott számok
    for m in LATEST_HEAD.finditer(flat):
        month, day = MONTHS[m[2].lower()], int(m[3])
        year = today.year - (1 if month > today.month else 0)
        try:
            d = dt.date(year, month, day)
        except ValueError:
            continue
        run = RUN.search(flat[m.end(): m.end() + 1500])
        if not run:
            continue
        nums = [int(x) for x in re.findall(NUM, run.group(0))]
        week = int(m[1])
        kyear = d.year - (1 if week >= 52 and d.month == 1 else 0) + (1 if week == 1 and d.month == 12 else 0)
        if _valid(nums):
            rows.append({"year": kyear, "week": week, "date": f"{d:%Y.%m.%d.}",
                         "counters": [0, 0, 0, 0], "nums": nums})
    return rows


def download(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    for enc in ("utf-8-sig", "cp1250", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue


def fetch_remote(cfg):
    """Az összes forrás húzásai (év, hét) szerint egyesítve; a számlálós (CSV) sor az erősebb."""
    urls = cfg["source_url"]
    urls = [urls] if isinstance(urls, str) else [u for u in (urls or []) if u]
    merged = {}
    for url in urls:
        try:
            rows = parse_source(download(url))
        except Exception as e:
            log(f"forrás hiba ({url}): {e}")
            continue
        for r in rows:
            old = merged.get(key(r))
            if old is None or (not any(old["counters"]) and any(r["counters"])):
                merged[key(r)] = r
        log(f"forrás: {url} -> {len(rows)} húzás, legutóbbi: "
            f"{max((key(r) for r in rows), default='-')}")
    return [merged[k] for k in sorted(merged)]


# ---------------------------------------------------------------- állapot
def load_state(cfg):
    if os.path.exists(cfg["state_file"]):
        with open(cfg["state_file"], encoding="utf-8") as f:
            return json.load(f)
    return {"tips": [], "update_offset": 0}


def save_state(cfg, st):
    tmp = cfg["state_file"] + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, cfg["state_file"])


def open_tip(st):
    return next((t for t in reversed(st["tips"]) if "hits" not in t and not t.get("skipped")), None)


def done_tips(st):
    return [t for t in st["tips"] if "hits" in t]


# ---------------------------------------------------------------- Telegram
class Telegram:
    def __init__(self, token, chat_id, dry_run=False):
        self.base = f"https://api.telegram.org/bot{token}/"
        self.chat_id, self.dry = chat_id, dry_run

    def call(self, method, **params):
        data = urllib.parse.urlencode(params).encode()
        with urllib.request.urlopen(self.base + method, data=data, timeout=60) as r:
            return json.loads(r.read())

    def send(self, text):
        if self.dry:
            print("\n----- TELEGRAM -----\n" + text + "\n--------------------", flush=True)
            return
        for attempt in range(3):
            try:
                self.call("sendMessage", chat_id=self.chat_id, text=text, parse_mode="HTML")
                return
            except Exception as e:
                log(f"sendMessage hiba ({attempt + 1}/3): {e}")
                time.sleep(5)

    def updates(self, offset, timeout=25):
        if self.dry:
            if timeout:
                time.sleep(timeout)
            return []
        return self.call("getUpdates", offset=offset, timeout=timeout).get("result", [])


def fmt(nums):
    return " ".join(f"{n:>2}" for n in nums)


# ---------------------------------------------------------------- logika
def next_draw_date(cfg, today):
    return today + dt.timedelta(days=(cfg["draw_weekday"] - today.weekday()) % 7)


def tip_key(t):
    """A tipp sorsolásának (év, hét) azonosítója; az adat.csv hetei ISO-hetek."""
    return tuple(dt.date.fromisoformat(t["for_draw"]).isocalendar()[:2])


def skip_tip(cfg, st, t):
    t["skipped"] = True
    save_state(cfg, st)
    log(f"{t['for_draw']} tippje kiértékelés nélkül lezárva")


def make_tip(cfg, st, tg, today):
    rows = read_history(cfg)
    draw = next_draw_date(cfg, today)
    t = open_tip(st)
    if t and t["for_draw"] < draw.isoformat():
        # Múltbeli sorsolás tippje: másnap (az eredménypótlás napján) még várunk rá,
        # utána lezárjuk, hogy a következő sorsolásra új tipp készüljön.
        if today > dt.date.fromisoformat(t["for_draw"]) + dt.timedelta(days=1):
            skip_tip(cfg, st, t)
            t = None
    if t:
        tg.send(tip_text(t, resend=True))
        return
    seed = draw.toordinal()  # ugyanarra a sorsolásra mindig ugyanaz a tipp
    rng = np.random.default_rng(seed)
    cols, kep = lp.pick(cfg["method"], lp.first36(rows), rng)
    control, _ = lp.pick("veletlen", lp.first36(rows), np.random.default_rng(seed + 1))
    t = {"made": today.isoformat(), "for_draw": draw.isoformat(), "method": cfg["method"],
         "cols": cols, "kep": kep, "control": lp.all_numbers(control), "history_len": len(rows)}
    st["tips"].append(t)
    save_state(cfg, st)
    tg.send(tip_text(t))
    log(f"tipp elküldve: {lp.all_numbers(cols)}")


def tip_text(t, resend=False):
    d = dt.date.fromisoformat(t["for_draw"])
    lines = [f"🎰 <b>Luxor tipp</b> – {d:%Y.%m.%d.} ({WEEKDAYS[d.weekday()]})"
             + (" (újraküldve)" if resend else ""),
             f"Módszer: {t['method']}, oszloponként 4 szám", ""]
    lines += [f"<code>{c}: {fmt(t['cols'][c])}</code>" for c in COLS]
    lines += ["", f"Kép (a középső 3x3-ba): <code>{' '.join(map(str, t['kep']))}</code>",
              "Keret: a többi 14 szám", "",
              f"Véletlen kontroll: <code>{' '.join(map(str, t['control']))}</code>",
              "Várható találat véletlennél: ~11.7 (kb. 44 kihúzott számnál)"]
    return "\n".join(lines)


def completion(numbers, order):
    """Hányadik húzásnál lett meg az összes szám (None, ha nem)."""
    pos = {n: i + 1 for i, n in enumerate(order)}
    if all(n in pos for n in numbers):
        return max(pos[n] for n in numbers)
    return None


def evaluate(cfg, st, tg, row):
    t = open_tip(st)
    if t is None:
        log("nincs nyitott tipp, nincs mit kiértékelni")
        return False
    order = row["nums"]
    drawn = set(order)
    mine = lp.all_numbers(t["cols"])
    keret = [n for n in mine if n not in t["kep"]]
    hits = [n for n in mine if n in drawn]
    k = len(order)
    t.update(draw_key=list(key(row)), drawn=k, hits=len(hits),
             control_hits=len(set(t["control"]) & drawn),
             kep_at=completion(t["kep"], order), keret_at=completion(keret, order),
             tele_at=completion(mine, order))
    save_state(cfg, st)

    done = done_tips(st)
    a = sum(x["hits"] for x in done)
    c = sum(x["control_hits"] for x in done)
    mu = sum(lp.hyper(x["drawn"])[0] for x in done)
    var = sum(lp.hyper(x["drawn"])[1] for x in done)
    z = (a - mu) / math.sqrt(var) if var else 0.0
    c1, c2, c3, _ = row["counters"]

    def at(v, first):
        s = f"✅ a {v}. húzásnál" if v else "❌ nem jött össze"
        return s + (f" (a sorsoláson az első: {first}.)" if first else "")

    lines = [f"📊 <b>Luxor eredmény</b> – {row['date'] or key(row)}  ({k} szám kihúzva)", ""]
    for col in COLS:
        cells = " ".join(f"<b>[{n}]</b>" if n in drawn else f"{n}" for n in t["cols"][col])
        lines.append(f"{col}: {cells}")
    lines += ["", f"Találat: <b>{len(hits)}/20</b>  (véletlennél várható: {lp.hyper(k)[0]:.1f})",
              f"Kép (6): {at(t['kep_at'], c2)}",
              f"Keret (14): {at(t['keret_at'], c3)}",
              "Telitalálat: " + (f"✅ a {t['tele_at']}. húzásnál" if t["tele_at"] else
                                 f"❌ hiányzik {20 - len(hits)} szám")
              + (f" (jackpot-határszám: {c1})" if c1 else ""),
              f"🎲 Véletlen kontroll: {t['control_hits']} találat", "",
              f"<b>Összesen {len(done)} hét</b>",
              f"Algoritmus: {a / len(done):.2f} | kontroll: {c / len(done):.2f} | "
              f"elmélet: {mu / len(done):.2f} találat/hét",
              f"z = {z:+.2f}  (|z| &lt; 2: nem különbözik a véletlentől)"]
    tg.send("\n".join(lines))
    log(f"kiértékelve: {len(hits)} találat")
    return True


def merge_new(local, remote):
    last = key(local[-1])
    return [r for r in remote if key(r) > last]


def upgrade_counters(local, remote):
    """A sorsolási oldalról (számlálók nélkül) felvett sorok kiegészítése a CSV számlálóival."""
    by_key = {key(r): r for r in remote}
    changed = 0
    for r in local:
        rr = by_key.get(key(r))
        if rr and not any(r["counters"][:3]) and any(rr["counters"][:3]) and set(rr["nums"]) == set(r["nums"]):
            r["counters"], r["nums"] = rr["counters"], rr["nums"]
            changed += 1
    return changed


def check_result(cfg, st, tg):
    local = read_history(cfg)
    remote = fetch_remote(cfg)
    if upgrade_counters(local[-10:], remote):
        write_history(cfg, local)
        log("számlálók kiegészítve a CSV-ből")
    new = merge_new(local, remote)
    if new:
        write_history(cfg, local + new)
        log(f"{len(new)} új húzás hozzáadva: {[key(r) for r in new]}")
    t = open_tip(st)
    if t is None:
        return False
    # Csak a tipp saját sorsolásával értékelünk (egy késve érkező régebbi húzással nem);
    # a helyi adatban is keresünk, ha egy korábbi futás elmentette, de nem értékelte.
    tk = tip_key(t)
    row = next((r for r in local + new if key(r) == tk), None)
    if row:
        return evaluate(cfg, st, tg, row)
    if new and key(new[-1]) > tk:  # a tipp sorsolása kimaradt a forrásokból
        skip_tip(cfg, st, t)
    return False


def manual_result(cfg, st, tg, text):
    nums = [int(x) for x in re.findall(r"\d+", text)]
    if not (lp.K36 <= len(nums) <= 75 and len(set(nums)) == len(nums) and all(1 <= n <= 75 for n in nums)):
        tg.send("Add meg az összes kihúzott számot (legalább 36, különbözők, 1-75) húzási sorrendben, pl.\n"
                "/eredmeny 53 72 50 4 41 ...")
        return
    rows = read_history(cfg)
    t = open_tip(st)
    d = dt.date.fromisoformat(t["for_draw"]) if t else dt.date.today()
    iso = d.isocalendar()
    row = {"year": iso[0], "week": iso[1], "date": f"{d:%Y.%m.%d.}", "counters": [0, 0, 0, len(nums)],
           "nums": nums}
    if rows and key(row) <= key(rows[-1]):
        tg.send(f"Ez a hét ({key(row)}) már szerepel az adatok között.")
        return
    write_history(cfg, rows + [row])
    if not evaluate(cfg, st, tg, row):
        tg.send("A húzást elmentettem, de nem volt nyitott tipp.")


def stat(cfg, st, tg):
    done = done_tips(st)
    if not done:
        tg.send("Még nincs kiértékelt hét.")
        return
    a = np.array([x["hits"] for x in done], float)
    c = np.array([x["control_hits"] for x in done], float)
    mu = sum(lp.hyper(x["drawn"])[0] for x in done)
    var = sum(lp.hyper(x["drawn"])[1] for x in done)
    z = (a.sum() - mu) / math.sqrt(var)
    kep = sum(1 for x in done if x.get("kep_at"))
    ker = sum(1 for x in done if x.get("keret_at"))
    tg.send(f"📈 <b>Luxor statisztika</b> ({len(done)} hét)\n"
            f"Algoritmus: átlag {a.mean():.2f}, legjobb {int(a.max())}\n"
            f"Kontroll: átlag {c.mean():.2f}\nElmélet: {mu / len(done):.2f}\n"
            f"z = {z:+.2f}\nKép összejött: {kep}×, keret: {ker}×")


def handle_updates(cfg, st, tg, timeout=25):
    for u in tg.updates(st.get("update_offset", 0), timeout=timeout):
        st["update_offset"] = u["update_id"] + 1
        save_state(cfg, st)
        msg = u.get("message") or {}
        if str(msg.get("chat", {}).get("id")) != cfg["chat_id"]:
            continue
        text = (msg.get("text") or "").strip()
        cmd = text.split()[0].split("@")[0].lower() if text else ""
        try:
            if cmd == "/tipp":
                make_tip(cfg, st, tg, dt.date.today())
            elif cmd == "/eredmeny":
                manual_result(cfg, st, tg, text[len("/eredmeny"):])
            elif cmd == "/stat":
                stat(cfg, st, tg)
            elif cmd in ("/help", "/start"):
                tg.send("\n".join(l.strip() for l in __doc__.split("Telegram parancsok")[1].split("\n")[1:]
                                  if l.strip()))
        except Exception as e:
            log(f"parancshiba: {e}")
            tg.send(f"Hiba: {e}")


# ---------------------------------------------------------------- ütemezés
def hm(s):
    return dt.time(*map(int, s.split(":")))


def tip_due(cfg, st, now):
    return (now.weekday() == cfg["draw_weekday"] and now.time() >= hm(cfg["tip_time"])
            and st.get("last_tip_day") != now.date().isoformat())


def in_result_window(cfg, now):
    """A sorsolás napján result_time-tól, másnap result_until-ig."""
    d = cfg["draw_weekday"]
    return ((now.weekday() == d and now.time() >= hm(cfg["result_time"]))
            or (now.weekday() == (d + 1) % 7 and now.time() <= hm(cfg["result_until"])))


def step(cfg, st, tg, now):
    due = tip_due(cfg, st, now)
    if open_tip(st) and cfg["source_url"] and (in_result_window(cfg, now) or due):
        try:
            check_result(cfg, st, tg)
        except Exception as e:
            log(f"forrás hiba: {e}")
    if due:
        make_tip(cfg, st, tg, now.date())
        st["last_tip_day"] = now.date().isoformat()
        save_state(cfg, st)


def run_cron(cfg, tg, now=None):
    st = load_state(cfg)
    try:
        handle_updates(cfg, st, tg, timeout=0)
    except Exception as e:
        log(f"getUpdates hiba: {e}")
    step(cfg, st, tg, now or dt.datetime.now())
    if not os.path.exists(cfg["state_file"]):
        save_state(cfg, st)


def run(cfg, tg):
    st = load_state(cfg)
    log(f"luxor bot indul: {cfg['method']}, sorsolás: {WEEKDAYS[cfg['draw_weekday']]}")
    next_check = None
    while True:
        now = dt.datetime.now()
        if next_check is None or now >= next_check or tip_due(cfg, st, now):
            step(cfg, st, tg, now)
            next_check = now + dt.timedelta(minutes=cfg["result_retry_minutes"])
        try:
            handle_updates(cfg, st, tg)
        except Exception as e:
            log(f"getUpdates hiba: {e}")
            time.sleep(10)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "config.json"))
    ap.add_argument("--dry-run", action="store_true", help="Telegram helyett konzolra ír")
    ap.add_argument("--once", choices=["tipp", "eredmeny", "stat", "cron"])
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    cfg = load_config(a.config)
    if not a.dry_run and (not (cfg["telegram_token"] and cfg["chat_id"])
                          or cfg["telegram_token"].startswith("IDE_")):
        sys.exit("Hiányzik a LUXOR_BOT_TOKEN (vagy a chat_id a config.json-ban).")
    if not os.path.exists(cfg["data_file"]):
        sys.exit(f"Nincs meg az adatfájl: {cfg['data_file']}")
    tg = Telegram(cfg["telegram_token"], cfg["chat_id"], a.dry_run)
    st = load_state(cfg)
    if a.once == "tipp":
        make_tip(cfg, st, tg, dt.date.today())
    elif a.once == "eredmeny":
        if not check_result(cfg, st, tg):
            print("Nincs új húzás a forrásban.")
    elif a.once == "stat":
        stat(cfg, st, tg)
    elif a.once == "cron":
        run_cron(cfg, tg)
    else:
        run(cfg, tg)


if __name__ == "__main__":
    main()
