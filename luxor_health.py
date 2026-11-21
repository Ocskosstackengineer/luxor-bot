"""
luxor_health.py - a Luxor-bot egészségfigyelése (a Kenó-bot keno_health.py mintájára).

Mit figyel (az állapot a bot_state.json "health" kulcsa alatt):
  1. Forráshiba: ha egy forrás egymás után `SOURCE_FAIL_LIMIT`-szer hibát ad vagy 0 húzást
     olvas ki belőle -> egyszeri riasztás; amikor újra működik -> "helyreállt" üzenet.
  2. Ellentmondás: ha a két forrás ugyanarra a hétre (év, hét) más számsort ad -> riasztás (hetente egyszer).
     A sorrendet is összeveti, mert a kép/keret kiértékelése a húzási sorrendre épül.
  3. Hiányzó eredmény: ha a sorsolás másnapján `result_until` (alap 12:00) is elmúlt, és még
     nincs eredmény -> egyszeri riasztás.
"""
import datetime as dt

SOURCE_FAIL_LIMIT = 3


def _health(st):
    h = st.setdefault("health", {})
    h.setdefault("sources", {})
    h.setdefault("mismatch_alerted", [])
    h.setdefault("missing_alerted", [])
    return h


def note_source(st, url, ok, n_rows=0, latest=None, error=None):
    """Egy forrás letöltésének eredménye. Visszaad: riasztandó üzenet vagy None."""
    s = _health(st)["sources"].setdefault(url, {"fail": 0, "alerted": False})
    if ok and n_rows > 0:
        msg = None
        if s.get("alerted"):
            msg = f"✅ <b>Luxor-forrás helyreállt</b>\n{url}\n(legutóbbi húzás: {latest})"
        s.update(fail=0, alerted=False, last_ok=dt.datetime.now().isoformat(timespec="minutes"),
                 latest=str(latest) if latest else None)
        return msg
    s["fail"] = s.get("fail", 0) + 1
    s["last_error"] = (str(error) if error else "0 húzás olvasható ki")[:200]
    if s["fail"] >= SOURCE_FAIL_LIMIT and not s.get("alerted"):
        s["alerted"] = True
        return (f"⚠️ <b>Luxor forráshiba</b> ({s['fail']}× egymás után)\n{url}\n"
                f"Hiba: {s['last_error']}\n"
                "Ha az oldal szerkezete változott, a parse_source-t kell igazítani.")
    return None


def check_consistency(st, rows_by_url):
    """rows_by_url: {url: [sor-dict (year, week, date, nums), ...]}. Visszaad: riasztások listája.
    Csak a legutóbbi 5 hetet veti össze (a régi CSV-sorok eltérései nem érdekesek)."""
    h = _health(st)
    keys = sorted({(r["year"], r["week"]) for rows in rows_by_url.values() for r in rows})[-5:]
    seen, msgs = {}, []
    for url, rows in rows_by_url.items():
        for r in rows:
            k = (r["year"], r["week"])
            if k not in keys:
                continue
            if k in seen and seen[k][1] != list(r["nums"]):
                tag = f"{k[0]}-{k[1]}"
                if tag not in h["mismatch_alerted"]:
                    h["mismatch_alerted"] = (h["mismatch_alerted"] + [tag])[-50:]
                    same_set = set(seen[k][1]) == set(r["nums"])
                    msgs.append(f"⚠️ <b>Eltérő Luxor-húzás két forrásban</b> – {k[0]}/{k[1]}. hét\n"
                                + ("Ugyanazok a számok, más sorrendben (a kép/keret húzásszáma ettől pontatlan lehet).\n"
                                   if same_set else "")
                                + f"{seen[k][0]}: {' '.join(map(str, seen[k][1]))}\n"
                                f"{url}: {' '.join(map(str, r['nums']))}")
            else:
                seen.setdefault(k, (url, list(r["nums"])))
    return msgs


def missing_result(st, open_tip, now, result_until="12:00"):
    """Ha a sorsolás (open_tip['for_draw']) másnapján result_until is elmúlt eredmény nélkül -> riasztás (egyszer)."""
    if not open_tip or not open_tip.get("for_draw"):
        return None
    draw = dt.date.fromisoformat(open_tip["for_draw"])
    h, m = map(int, result_until.split(":"))
    deadline = dt.datetime.combine(draw + dt.timedelta(days=1), dt.time(h, m))
    hs = _health(st)
    if now >= deadline and open_tip["for_draw"] not in hs["missing_alerted"]:
        hs["missing_alerted"] = (hs["missing_alerted"] + [open_tip["for_draw"]])[-50:]
        state = "\n".join(f"• {u.rstrip('/').split('/')[-1]}: legutóbbi {s.get('latest') or '-'}, hibák: {s.get('fail', 0)}"
                          for u, s in hs["sources"].items()) or "• (nincs adat a forrásokról)"
        return (f"⚠️ <b>Nincs Luxor-eredmény</b> a(z) {draw:%Y.%m.%d.} sorsoláshoz "
                f"{(draw + dt.timedelta(days=1)):%m.%d.} {result_until}-ig.\nForrások:\n{state}\n"
                "A bot a következő szombati tipp előtt még egyszer keresi. "
                "Kézzel: /eredmeny + az összes kihúzott szám húzási sorrendben.")
    return None
