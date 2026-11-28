"""PROTOTYPE, throwaway: three layouts for the public site (platform-docs#43, api#40 and #43).

Question: what should the public site look like and how should a portfolio
visitor move through it? Three structurally different variants on the same
routes, switchable with `?variant=A|B|C` or the arrow keys.

Run from the repository root:

    uv run python web_prototype/serve.py

then open http://localhost:8765/?variant=A

Data: the recorded Jolpica fixtures for 2024 only, imported into in-memory
SQLite and read through the real API with TestClient. Other seasons are listed
so the index has realistic density, but have no data in this prototype.

Not production code: no tests, no Jinja, and the switcher bar uses JavaScript,
which the real site will not. Lives on the prototype/public-site-ui branch only.
"""

import html
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import database  # noqa: E402
from app.importer import Importer  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from tests.fixtures.jolpica.client import FixtureJolpicaClient  # noqa: E402
from tests.migrations import stamp  # noqa: E402

SEASON = 2024
YEARS = list(range(1950, SEASON + 1))
DATA_DATE = "2026-11-28 07:12 UTC"
PORT = 8765


# --- data: the real API over fixture data --------------------------------------------------

def load() -> dict:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    stamp(engine)
    database.engine = engine
    database.readiness_engine = engine
    database.SessionLocal.configure(bind=engine)
    with database.SessionLocal() as session:
        Importer(session, FixtureJolpicaClient()).import_season(SEASON)
    with TestClient(app) as client:
        races = client.get(f"/seasons/{SEASON}/races").json()
        results = {r["round"]: client.get(f"/seasons/{SEASON}/races/{r['round']}/results").json()
                   for r in races}
        drivers = client.get(f"/seasons/{SEASON}/standings/drivers").json()
        constructors = client.get(f"/seasons/{SEASON}/standings/constructors").json()
    return {"races": races, "results": results, "drivers": drivers,
            "constructors": constructors}


D: dict = {}
e = html.escape


def driver_name(d: dict) -> str:
    return e(f"{d['given_name']} {d['family_name']}")


def winner(round_number: int) -> dict | None:
    rows = D["results"].get(round_number) or []
    return rows[0] if rows else None


def race(round_number: int) -> dict:
    return next(r for r in D["races"] if r["round"] == round_number)


def footer(cls: str = "") -> str:
    return (f'<footer class="{cls}">Data: <a href="https://github.com/jolpica/jolpica-f1">'
            'Jolpica F1</a>, <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/">'
            f'CC BY-NC-SA 4.0</a> · Data as of {DATA_DATE} · '
            '<a href="/about">About this site</a></footer>')


def about_body() -> str:
    return ("<p>Formula Insights is a portfolio project in platform engineering. This site is "
            "generated once a day from the Formula Insights API, using the release the "
            "<code>local</code> environment runs, and published to GitHub Pages.</p>"
            "<ul><li><a href='https://github.com/fabriciolelis/formula-insights-api'>"
            "formula-insights-api</a></li><li><a href='https://github.com/fabriciolelis/"
            "platform-gitops'>platform-gitops</a></li><li><a href='https://github.com/"
            "fabriciolelis/platform-docs'>platform-docs</a> (decisions and SLOs)</li></ul>")


def no_data(year: int) -> str:
    return f"<p><em>PROTOTYPE: only {SEASON} is recorded; {year} has no data here.</em></p>"


# --- Variant A: reference archive ----------------------------------------------------------
# Plain, dense, table-first. Index by decade; one long season page; separate race pages.

CSS_A = """
body{font:15px/1.5 Georgia,serif;max-width:960px;margin:0 auto;padding:16px;color:#202122;
background:#fff}
a{color:#3366cc;text-decoration:none}a:hover{text-decoration:underline}
header{border-bottom:1px solid #a2a9b1;margin-bottom:12px}header b{font-size:22px}
.crumbs{font:13px sans-serif;color:#54595d}
table{border-collapse:collapse;width:100%;font:14px sans-serif;margin:8px 0 24px}
th,td{border:1px solid #c8ccd1;padding:4px 8px;text-align:left}th{background:#eaecf0}
td.n{text-align:right}h2{border-bottom:1px solid #a2a9b1;font-weight:normal}
.decade{display:flex;gap:6px;flex-wrap:wrap;margin:4px 0 12px;font:14px sans-serif}
.decade b{width:60px}.toc{font:14px sans-serif;background:#f8f9fa;border:1px solid #a2a9b1;
display:inline-block;padding:8px 16px}
footer{font:12px sans-serif;color:#54595d;border-top:1px solid #a2a9b1;margin-top:32px;
padding-top:8px}.pn{display:flex;justify-content:space-between;font:14px sans-serif}
"""


def a_page(title: str, crumbs: str, body: str) -> str:
    return (f"<style>{CSS_A}</style><header><b>Formula Insights</b> — historical Formula 1 "
            f"results</header><div class='crumbs'>{crumbs}</div><h1>{title}</h1>{body}"
            + footer())


def a_index() -> str:
    rows = ""
    for start in range(1950, SEASON + 1, 10):
        links = " ".join(f"<a href='/seasons/{y}'>{y}</a>"
                         for y in YEARS if start <= y < start + 10)
        rows += f"<div class='decade'><b>{start}s</b> {links}</div>"
    return a_page("Seasons", "Home", f"<p>{len(YEARS)} seasons, 1950 to {SEASON}.</p>{rows}")


def a_season(year: int) -> str:
    crumbs = f"<a href='/'>Home</a> › {year}"
    if year != SEASON:
        return a_page(f"{year} season", crumbs, no_data(year))
    cal = "".join(
        f"<tr><td class='n'>{r['round']}</td><td>{r['date']}</td><td><a href='/seasons/{year}/"
        f"races/{r['round']}'>{e(r['name'])}</a></td><td>{e(r['circuit']['name'])}</td>"
        f"<td>{driver_name(w['driver']) if (w := winner(r['round'])) else '—'}</td></tr>"
        for r in D["races"])
    drv = "".join(f"<tr><td class='n'>{e(s['position_text'])}</td><td>{driver_name(s)}</td>"
                  f"<td class='n'>{s['wins']}</td><td class='n'>{s['points']:g}</td></tr>"
                  for s in D["drivers"])
    con = "".join(f"<tr><td class='n'>{e(s['position_text'])}</td><td>{e(s['name'])}</td>"
                  f"<td class='n'>{s['wins']}</td><td class='n'>{s['points']:g}</td></tr>"
                  for s in D["constructors"])
    body = ("<div class='toc'>Contents<br>1 <a href='#calendar'>Calendar</a><br>2 <a href="
            "'#drivers'>Drivers' standings</a><br>3 <a href='#constructors'>Constructors' "
            "standings</a></div>"
            f"<h2 id='calendar'>Calendar</h2><table><tr><th>Rd</th><th>Date</th><th>Grand Prix"
            f"</th><th>Circuit</th><th>Winner</th></tr>{cal}</table>"
            f"<h2 id='drivers'>Drivers' standings</h2><table><tr><th>Pos</th><th>Driver</th>"
            f"<th>Wins</th><th>Points</th></tr>{drv}</table>"
            f"<h2 id='constructors'>Constructors' standings</h2><table><tr><th>Pos</th><th>"
            f"Constructor</th><th>Wins</th><th>Points</th></tr>{con}</table>")
    return a_page(f"{year} Formula One season", crumbs, body)


def a_race(year: int, rnd: int) -> str:
    r = race(rnd)
    rows = "".join(
        f"<tr><td class='n'>{e(x['position_text'])}</td><td>{driver_name(x['driver'])}</td>"
        f"<td>{e(x['constructor']['name'])}</td><td>{e(x['status'])}</td>"
        f"<td class='n'>{x['points']:g}</td></tr>" for x in D["results"][rnd])
    prev_ = (f"<a href='/seasons/{year}/races/{rnd - 1}'>‹ {e(race(rnd - 1)['name'])}</a>"
             if rnd > 1 else "<span></span>")
    next_ = (f"<a href='/seasons/{year}/races/{rnd + 1}'>{e(race(rnd + 1)['name'])} ›</a>"
             if rnd < len(D["races"]) else "<span></span>")
    body = (f"<p>Round {rnd} · {r['date']} · {e(r['circuit']['name'])}</p><table><tr><th>Pos"
            f"</th><th>Driver</th><th>Constructor</th><th>Status</th><th>Points</th></tr>{rows}"
            f"</table><div class='pn'>{prev_}{next_}</div>")
    return a_page(f"{year} {e(r['name'])}",
                  f"<a href='/'>Home</a> › <a href='/seasons/{year}'>{year}</a> › Round {rnd}",
                  body)


# --- Variant B: app shell with sidebar -----------------------------------------------------
# No index page: lands on the latest season. Persistent sidebar (seasons + rounds).
# Season page leads with the championship; race page leads with the podium.

CSS_B = """
*{box-sizing:border-box}body{margin:0;font:14px/1.4 system-ui,sans-serif;background:#0f1115;
color:#e6e6e6;display:grid;grid-template-columns:240px 1fr;min-height:100vh}
a{color:inherit;text-decoration:none}
aside{background:#171a21;border-right:1px solid #262b36;height:100vh;position:sticky;top:0;
display:flex;flex-direction:column}
aside .brand{padding:16px;font-weight:700;letter-spacing:.5px;color:#ff4d4d}
aside select{margin:0 16px 12px;padding:6px;background:#0f1115;color:#e6e6e6;
border:1px solid #333}
aside nav{overflow:auto;flex:1}aside nav a{display:flex;gap:8px;padding:6px 16px;color:#aab}
aside nav a:hover,aside nav a.on{background:#232835;color:#fff}aside nav small{color:#667;
width:22px}aside .sec{padding:10px 16px 4px;color:#667;font-size:11px;text-transform:uppercase}
main{padding:24px 32px;max-width:1100px}
.hero{display:flex;gap:16px;margin-bottom:24px}.card{background:#171a21;border:1px solid
#262b36;border-radius:10px;padding:16px;flex:1}.card .k{color:#889;font-size:12px;
text-transform:uppercase}.card .v{font-size:26px;font-weight:700;margin-top:4px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}
table{width:100%;border-collapse:collapse}td,th{padding:6px 8px;border-bottom:1px solid
#232835;text-align:left}th{color:#889;font-weight:500;font-size:12px}td.n{text-align:right}
.podium{display:grid;grid-template-columns:1fr 1.2fr 1fr;gap:12px;align-items:end;
margin-bottom:24px}.podium .card{text-align:center}.p1{border-color:#ff4d4d!important;
padding:28px 16px!important}.pos{font-size:32px;font-weight:800;color:#ff4d4d}
footer{color:#667;font-size:12px;margin-top:32px}footer a{text-decoration:underline}
"""


# PLACEHOLDER art: generic helmet and car shapes painted in the team colour. Not the
# drivers' real helmet designs nor the teams' real cars (see the image-source question).
TEAM_COLOURS = {  # 2024 only; a real site would need a curated table back to 1950
    "red_bull": "#3671C6", "mclaren": "#FF8000", "ferrari": "#E8002D", "mercedes": "#27F4D2",
    "aston_martin": "#229971", "alpine": "#0093CC", "williams": "#64C4FF", "rb": "#6692FF",
    "haas": "#B6BABD", "sauber": "#52E252",
}


def colour(constructor_id: str) -> str:
    return TEAM_COLOURS.get(constructor_id, "#888")


def helmet(c: str, size: int = 22) -> str:
    return (f"<svg width='{size}' height='{size}' viewBox='0 0 32 32' style='vertical-align:"
            f"middle;flex:none'><path d='M4 20a12 12 0 0 1 24-4v6H14l-2 4H6a2 2 0 0 1-2-2z' "
            f"fill='{c}'/><path d='M15 14h12v5H15z' fill='#111' opacity='.75'/>"
            f"<path d='M6 22h22' stroke='#fff' stroke-width='1.5' opacity='.6'/></svg>")


def car(c: str, width: int = 160) -> str:
    return (f"<svg width='{width}' viewBox='0 0 200 50' style='display:block;margin:8px auto'>"
            f"<path d='M8 34h22l10-10h40l8-8h22l6 8h40l20 6 16 2v6H8z' fill='{c}'/>"
            f"<path d='M96 16h18l4 8H92z' fill='#111'/><rect x='2' y='22' width='10' "
            f"height='14' fill='{c}'/><rect x='186' y='30' width='12' height='8' fill='{c}'/>"
            f"<circle cx='40' cy='40' r='9' fill='#111'/><circle cx='158' cy='40' r='9' "
            f"fill='#111'/></svg>")


def team_of_driver() -> dict[str, dict]:
    # The API's driver standings carry no constructor; the prototype takes each driver's
    # team from their last race result.
    teams: dict[str, dict] = {}
    for rnd in sorted(D["results"]):
        for x in D["results"][rnd]:
            teams[x["driver"]["id"]] = x["constructor"]
    return teams


def who(driver: dict, constructor: dict, size: int = 22) -> str:
    return (f"<span style='display:inline-flex;gap:8px;align-items:center'>"
            f"{helmet(colour(constructor['id']), size)}{driver_name(driver)}</span>")


def stripe(constructor: dict) -> str:
    return (f"<span style='display:inline-block;width:4px;height:14px;margin-right:8px;"
            f"vertical-align:middle;background:{colour(constructor['id'])}'></span>"
            f"{e(constructor['name'])}")


def b_shell(year: int, active: str, body: str) -> str:
    opts = "".join(f"<option value='/seasons/{y}' {'selected' if y == year else ''}>{y}</option>"
                   for y in reversed(YEARS))
    rounds = "".join(
        f"<a class='{'on' if active == str(r['round']) else ''}' href='/seasons/{year}/races/"
        f"{r['round']}'><small>{r['round']}</small>{e(r['name'].replace(' Grand Prix', ''))}</a>"
        for r in D["races"]) if year == SEASON else ""
    nav = (f"<a class='{'on' if active == 'home' else ''}' href='/'><small>⌂</small>Home</a>"
           f"<a class='{'on' if active == 'season' else ''}' href='/seasons/{year}'>"
           f"<small>★</small>Championship</a><div class='sec'>Races</div>{rounds}")
    return (f"<style>{CSS_B}</style><aside><div class='brand'>FORMULA INSIGHTS</div>"
            "<select onchange='location=this.value+location.search'>"
            f"{opts}</select><nav>{nav}</nav></aside><main>{body}{footer()}</main>")


def b_season(year: int) -> str:
    if year != SEASON:
        return b_shell(year, "season", f"<h1>{year}</h1>{no_data(year)}")
    teams = team_of_driver()
    d1, d2 = D["drivers"][0], D["drivers"][1]
    c1 = D["constructors"][0]
    hero = (f"<div class='hero'><div class='card'><div class='k'>Drivers' champion</div><div "
            f"class='v'>{who(d1, teams[d1['id']], 30)}</div>{d1['points']:g} pts · "
            f"{d1['wins']} wins</div><div class='card'><div class='k'>Margin to P2</div><div "
            f"class='v'>{d1['points'] - d2['points']:g} pts</div>over {driver_name(d2)}</div>"
            f"<div class='card'><div class='k'>Constructors' champion</div><div class='v'>"
            f"{e(c1['name'])}</div>{car(colour(c1['id']), 140)}{c1['points']:g} pts</div></div>")
    drv = "".join(f"<tr><td>{e(s['position_text'])}</td><td>{who(s, teams[s['id']])}</td>"
                  f"<td class='n'>{s['points']:g}</td></tr>" for s in D["drivers"])
    con = "".join(f"<tr><td>{e(s['position_text'])}</td><td>{stripe(s)}</td><td class='n'>"
                  f"{s['points']:g}</td></tr>" for s in D["constructors"])
    body = (f"<h1>{year} championship</h1>{hero}<div class='cols'><div class='card'><table>"
            f"<tr><th>#</th><th>Driver</th><th>Pts</th></tr>{drv}</table></div><div "
            f"class='card'><table><tr><th>#</th><th>Constructor</th><th>Pts</th></tr>{con}"
            "</table></div></div>")
    return b_shell(year, "season", body)


def podium(res: list[dict], car_width: int = 150) -> str:
    def step(i: int, cls: str) -> str:
        x = res[i]
        return (f"<div class='card {cls}'><div class='pos'>P{i + 1}</div>"
                f"{car(colour(x['constructor']['id']), car_width)}"
                f"<b>{who(x['driver'], x['constructor'])}</b><br>"
                f"{e(x['constructor']['name'])}</div>")
    return f"<div class='podium'>{step(1, '')}{step(0, 'p1')}{step(2, '')}</div>"


def b_race(year: int, rnd: int) -> str:
    r, res = race(rnd), D["results"][rnd]
    rows = "".join(f"<tr><td>{e(x['position_text'])}</td><td>"
                   f"{who(x['driver'], x['constructor'])}</td><td>{stripe(x['constructor'])}"
                   f"</td><td>{e(x['status'])}</td><td class='n'>{x['points']:g}</td></tr>"
                   for x in res)
    body = (f"<h1>{e(r['name'])}</h1><p style='color:#889'>Round {rnd} · {r['date']} · "
            f"{e(r['circuit']['name'])}</p>{podium(res)}<div class='card'><table><tr><th>Pos"
            f"</th><th>Driver</th><th>Constructor</th><th>Status</th><th>Pts</th></tr>{rows}"
            "</table></div>")
    return b_shell(year, str(rnd), body)


# --- Home options inside variant B ---------------------------------------------------------

def last_race() -> dict:
    return [r for r in D["races"] if D["results"].get(r["round"])][-1]


def top5_table() -> str:
    teams = team_of_driver()
    rows = "".join(f"<tr><td>{s['position_text']}</td><td>{who(s, teams[s['id']])}</td>"
                   f"<td class='n'>{s['points']:g}</td></tr>" for s in D["drivers"][:5])
    return (f"<div class='card'><div class='k'>Championship</div><table>{rows}</table>"
            f"<a href='/seasons/{SEASON}' style='color:#ff4d4d'>Full standings →</a></div>")


def b_home_latest() -> str:
    r = last_race()
    body = (f"<div style='color:#889;text-transform:uppercase;font-size:12px'>Latest race · "
            f"Round {r['round']} · {r['date']}</div><h1 style='margin-top:4px'>"
            f"<a href='/seasons/{SEASON}/races/{r['round']}'>{e(r['name'])}</a></h1>"
            f"{podium(D['results'][r['round']], 170)}<div class='cols'>{top5_table()}"
            f"<div class='card'><div class='k'>Browse</div><p>Every season from 1950 to "
            f"{SEASON}: races, results and standings, updated daily.</p><p><a href='/seasons/"
            f"{SEASON}' style='color:#ff4d4d'>{SEASON} season →</a></p></div></div>")
    return b_shell(SEASON, "home", body)


def b_home_grid() -> str:
    tiles = ""
    for r in D["races"]:
        w = winner(r["round"])
        c = colour(w["constructor"]["id"]) if w else "#333"
        inner = (f"{helmet(c, 34)}<b>{e(w['driver']['family_name'])}</b>" if w
                 else "<span style='color:#667'>Not run yet</span>")
        tiles += (f"<a class='card' href='/seasons/{SEASON}/races/{r['round']}' style='display:"
                  f"flex;flex-direction:column;gap:6px;align-items:flex-start;border-top:3px "
                  f"solid {c}'><small style='color:#889'>R{r['round']} · {r['date'][5:]}</small>"
                  f"<span>{e(r['name'].replace(' Grand Prix', ''))}</span>{inner}</a>")
    d1 = D["drivers"][0]
    body = (f"<h1>{SEASON} at a glance</h1><p style='color:#889'>{driver_name(d1)} champion "
            f"with {d1['points']:g} points. Every race and its winner:</p><div style='display:"
            f"grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px'>{tiles}"
            "</div>")
    return b_shell(SEASON, "home", body)


def b_home_intro() -> str:
    r = last_race()
    body = ("<div class='card' style='padding:28px;margin-bottom:16px'><h1 style='margin:0 0 "
            "8px'>Formula 1 history, served by a platform</h1><p style='color:#aab;max-width:"
            "640px'>Every Formula 1 season since 1950, imported from Jolpica F1 and served by "
            "the Formula Insights API. This site is regenerated daily by a GitHub Actions "
            "publication using the release the platform runs; the platform itself is built with "
            "Kubernetes, Argo CD, Terraform and Prometheus.</p><p><a href='/about' style='color:"
            "#ff4d4d'>How it works →</a> &nbsp; <a href='https://github.com/fabriciolelis/"
            "platform-docs' style='color:#ff4d4d'>Decisions and SLOs →</a></p></div>"
            f"<div class='cols'><div class='card'><div class='k'>Latest race · {e(r['name'])}"
            f"</div>{podium(D['results'][r['round']], 90)}</div>{top5_table()}</div>")
    return b_shell(SEASON, "home", body)


# --- Variant C: editorial timeline ---------------------------------------------------------
# Home tells the latest season as a story: champions, then a vertical timeline of rounds
# with each winner. Race pages read like a headline; standings are bars; seasons are a strip.

CSS_C = """
body{margin:0;font:16px/1.6 'Helvetica Neue',Arial,sans-serif;color:#111;background:#f4f1ea}
a{color:inherit}.wrap{max-width:760px;margin:0 auto;padding:24px 16px}
.mast{font-weight:900;font-size:13px;letter-spacing:3px;text-transform:uppercase;
border-bottom:3px solid #111;padding-bottom:6px;display:flex;justify-content:space-between}
.mast a{text-decoration:none}
h1{font-size:44px;line-height:1.05;margin:24px 0 8px;font-weight:900}
.dek{font-size:20px;color:#444;margin-bottom:24px}
.tl{border-left:3px solid #111;margin-left:8px;padding-left:24px}
.tl a{display:block;text-decoration:none;position:relative;padding:10px 0;border-bottom:1px solid
#d8d2c4}.tl a:before{content:'';position:absolute;left:-32px;top:18px;width:13px;height:13px;
background:#f4f1ea;border:3px solid #111;border-radius:50%}.tl a:hover:before{background:#d00}
.tl small{color:#777;font-size:12px;text-transform:uppercase;letter-spacing:1px}
.tl b{display:block;font-size:18px}
.bar{display:grid;grid-template-columns:28px 180px 1fr 48px;gap:8px;align-items:center;
font-size:14px;margin:3px 0}.bar i{display:block;height:12px;background:#111}
.bar:first-of-type i{background:#d00}
.strip{display:flex;flex-wrap:wrap;gap:4px;font-size:12px;margin-top:8px}
.strip a{padding:2px 6px;border:1px solid #bbb;text-decoration:none}
.strip a.on{background:#111;color:#f4f1ea}
details{margin-top:16px}summary{cursor:pointer;font-weight:700}
table{width:100%;border-collapse:collapse;font-size:14px}td{padding:4px;border-bottom:1px solid
#d8d2c4}.top{font-size:18px}.top td{padding:8px 4px}
footer{font-size:12px;color:#777;border-top:3px solid #111;margin-top:48px;padding-top:8px}
"""


def c_page(body: str, year: int = SEASON) -> str:
    strip = "".join(f"<a class='{'on' if y == year else ''}' href='/seasons/{y}'>{y}</a>"
                    for y in reversed(YEARS))
    return (f"<style>{CSS_C}</style><div class='wrap'><div class='mast'><a href='/'>Formula "
            f"Insights</a><a href='/seasons/{year}/standings'>Standings</a></div>{body}"
            f"<h3>Every season</h3><div class='strip'>{strip}</div>{footer()}</div>")


def c_season(year: int) -> str:
    if year != SEASON:
        return c_page(f"<h1>{year}</h1>{no_data(year)}", year)
    d1, c1 = D["drivers"][0], D["constructors"][0]
    items = "".join(
        f"<a href='/seasons/{year}/races/{r['round']}'><small>Round {r['round']} · {r['date']}"
        f"</small><b>{e(r['name'])}</b>"
        f"{'Won by ' + driver_name(w['driver']) + ', ' + e(w['constructor']['name']) if (w := winner(r['round'])) else 'Not run yet'}"
        "</a>" for r in D["races"])
    body = (f"<h1>The {year} season</h1><div class='dek'>{driver_name(d1)} took the title with "
            f"{d1['points']:g} points and {d1['wins']} wins; {e(c1['name'])} won the "
            f"constructors' championship.</div><div class='tl'>{items}</div>")
    return c_page(body, year)


def c_race(year: int, rnd: int) -> str:
    r, res = race(rnd), D["results"][rnd]
    w = res[0]
    top = "".join(f"<tr><td>{e(x['position_text'])}</td><td>{driver_name(x['driver'])}</td>"
                  f"<td>{e(x['constructor']['name'])}</td><td>{x['points']:g}</td></tr>"
                  for x in res[:3])
    rest = "".join(f"<tr><td>{e(x['position_text'])}</td><td>{driver_name(x['driver'])}</td>"
                   f"<td>{e(x['constructor']['name'])}</td><td>{e(x['status'])}</td></tr>"
                   for x in res[3:])
    body = (f"<p><small>{year} · Round {rnd} · {r['date']} · {e(r['circuit']['name'])}</small>"
            f"</p><h1>{driver_name(w['driver'])} wins the {e(r['name'])}</h1><div class='dek'>"
            f"for {e(w['constructor']['name'])}, ahead of {driver_name(res[1]['driver'])} and "
            f"{driver_name(res[2]['driver'])}.</div><table class='top'>{top}</table>"
            f"<details><summary>Full classification</summary><table>{rest}</table></details>"
            f"<p><a href='/seasons/{year}'>← The {year} season</a></p>")
    return c_page(body, year)


def c_standings(year: int) -> str:
    def bars(rows: list[dict], name) -> str:
        top = rows[0]["points"] or 1
        return "".join(f"<div class='bar'><span>{e(s['position_text'])}</span><span>{name(s)}"
                       f"</span><i style='width:{100 * s['points'] / top:.0f}%'></i><span>"
                       f"{s['points']:g}</span></div>" for s in rows)
    body = (f"<h1>{year} standings</h1><h3>Drivers</h3>{bars(D['drivers'], driver_name)}"
            f"<h3>Constructors</h3>{bars(D['constructors'], lambda s: e(s['name']))}")
    return c_page(body, year)


# --- routing and the prototype switcher ----------------------------------------------------

VARIANTS = {"B1": "B, home: latest race", "B2": "B, home: season grid",
            "B3": "B, home: portfolio intro"}
HOMES = {"B1": b_home_latest, "B2": b_home_grid, "B3": b_home_intro}

SWITCHER = """
<div id="proto" style="position:fixed;bottom:16px;left:50%;transform:translateX(-50%);
background:#ff0;color:#000;font:600 13px system-ui;padding:8px 14px;border-radius:999px;
box-shadow:0 4px 16px rgba(0,0,0,.35);display:flex;gap:12px;align-items:center;z-index:99">
<a href="#" onclick="go(-1);return false" style="color:#000">◀</a>
<span>PROTOTYPE · %s</span>
<a href="#" onclick="go(1);return false" style="color:#000">▶</a></div>
<script>
const keys=%s, cur="%s";
function go(d){const i=(keys.indexOf(cur)+d+keys.length)%%keys.length;
const u=new URL(location);u.searchParams.set('variant',keys[i]);location=u}
document.addEventListener('keydown',ev=>{if(ev.target.closest('input,textarea,select,[contenteditable]'))return;
if(ev.key==='ArrowLeft')go(-1);if(ev.key==='ArrowRight')go(1)});
// keep ?variant on every internal link
document.querySelectorAll('a[href^="/"]').forEach(a=>{const u=new URL(a.href);
u.searchParams.set('variant',cur);a.href=u});
</script>
"""


def render(path: str, v: str) -> tuple[int, str]:
    full, v = v, v[0]
    parts = [p for p in path.split("/") if p]
    if parts == ["about"]:
        body = about_body()
        page = {"A": lambda: a_page("About this site", "<a href='/'>Home</a>", body),
                "B": lambda: b_shell(SEASON, "", f"<h1>About this site</h1>{body}"),
                "C": lambda: c_page(f"<h1>About this site</h1>{body}")}[v]()
    elif not parts:
        page = HOMES[full]()
    elif parts[0] == "seasons" and len(parts) == 2:
        page = {"A": a_season, "B": b_season, "C": c_season}[v](int(parts[1]))
    elif parts[0] == "seasons" and len(parts) == 3 and parts[2] == "standings":
        page = {"A": a_season, "B": b_season, "C": c_standings}[v](int(parts[1]))
    elif parts[0] == "seasons" and len(parts) == 4 and parts[2] == "races":
        page = {"A": a_race, "B": b_race, "C": c_race}[v](int(parts[1]), int(parts[3]))
    else:
        return 404, "not found"
    label = f"{full} ({VARIANTS[full]})"
    v = full
    switcher = (SWITCHER.replace("PROTOTYPE · %s", f"PROTOTYPE · {label}")
                .replace("keys=%s", f"keys={list(VARIANTS)}").replace('cur="%s"', f'cur="{v}"')
                .replace("%%", "%"))
    return 200, ("<!doctype html><meta charset='utf-8'><meta name='viewport' "
                 f"content='width=device-width,initial-scale=1'><title>Formula Insights</title>"
                 f"{page}{switcher}")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        v = parse_qs(url.query).get("variant", ["B1"])[0].upper()
        v = v if v in VARIANTS else "B1"
        try:
            status, body = render(url.path, v)
        except (KeyError, StopIteration, ValueError, IndexError):
            status, body = 404, "not found"
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    D.update(load())
    print(f"PROTOTYPE public site: http://localhost:{PORT}/?variant=B1  (B2, B3; arrow keys)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
