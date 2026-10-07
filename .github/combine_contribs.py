"""Merge several GitHub accounts' contribution calendars into one forge-styled SVG.

Usage: GITHUB_TOKEN=... python combine_contribs.py OUT.svg user1 user2 ...
"""
import json, os, re, sys, urllib.request
from datetime import date

QUERY = """query($u:String!){user(login:$u){contributionsCollection{contributionCalendar{
  totalContributions weeks{contributionDays{date contributionCount}}}}}}"""
LEVELS = ["#2A221C", "#6B2A10", "#B8420F", "#FF5F1F", "#FFB23E"]
CELL, GAP, PAD_X, TOP = 16, 4, 70, 104


def fetch(user, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"u": user}}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": "forge-profile"},
    )
    body = json.load(urllib.request.urlopen(req))
    if "errors" in body:
        sys.exit(f"{user}: {body['errors']}")
    return body["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def render(calendars, users, fonts=""):
    """calendars: list of contributionCalendar dicts, same order as users."""
    counts = {}
    for cal in calendars:
        for w in cal["weeks"]:
            for d in w["contributionDays"]:
                counts[d["date"]] = counts.get(d["date"], 0) + d["contributionCount"]
    weeks = [[d["date"] for d in w["contributionDays"]] for w in calendars[0]["weeks"]]
    peak = max(counts.values(), default=0) or 1
    total = sum(counts.values())
    width = PAD_X * 2 + len(weeks) * (CELL + GAP) - GAP
    height = TOP + 7 * (CELL + GAP) + 50

    out, last_month = [], None
    for x, week in enumerate(weeks):
        cx = PAD_X + x * (CELL + GAP)
        month = date.fromisoformat(week[0]).strftime("%b")
        if month != last_month and x < len(weeks) - 2:
            out.append(f'<text class="m" x="{cx}" y="{TOP - 12}" font-size="13" fill="#8C7D70">{month}</text>')
            last_month = month
        for day in week:
            y = TOP + date.fromisoformat(day).isoweekday() % 7 * (CELL + GAP)
            n = counts.get(day, 0)
            lvl = 0 if n == 0 else min(4, 1 + (n * 4 - 1) // peak)
            out.append(f'<rect x="{cx}" y="{y}" width="{CELL}" height="{CELL}" rx="3" fill="{LEVELS[lvl]}"><title>{n} on {day}</title></rect>')

    split = " + ".join(f"{u} {c['totalContributions']}" for u, c in zip(users, calendars))
    ly = TOP + 7 * (CELL + GAP) + 22
    legend = "".join(
        f'<rect x="{width - PAD_X - 5 * 20 + i * 20 + 4}" y="{ly - 12}" width="14" height="14" rx="3" fill="{c}"/>'
        for i, c in enumerate(LEVELS))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none">
<style>{fonts}.m{{font-family:'JBM',ui-monospace,Consolas,monospace}}.mb{{font-family:'JBM',ui-monospace,Consolas,monospace;font-weight:700}}</style>
<rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="16" fill="#17130F" stroke="#3B3028" stroke-width="2"/>
<text class="mb" x="{PAD_X}" y="48" font-size="22" fill="#FFB23E">{total} contributions in the last year</text>
<text class="m" x="{PAD_X}" y="72" font-size="14" fill="#B3A79B">{split}</text>
{"".join(out)}
<text class="m" x="{PAD_X}" y="{ly}" font-size="12" fill="#8C7D70">all accounts, merged daily</text>
<text class="m" x="{width - PAD_X - 5 * 20 - 40}" y="{ly}" font-size="12" fill="#8C7D70">less</text>{legend}
<text class="m" x="{width - PAD_X + 10}" y="{ly}" font-size="12" fill="#8C7D70">more</text>
</svg>"""


def demo():
    cal = lambda counts: {"totalContributions": sum(counts), "weeks": [{"contributionDays": [
        {"date": f"2026-09-{6 + i:02d}", "contributionCount": c} for i, c in enumerate(counts)]}]}
    svg = render([cal([0, 1, 0, 0, 0, 0, 2]), cal([0, 3, 0, 0, 0, 0, 0])], ["a", "b"])
    assert "6 contributions in the last year" in svg and "a 3 + b 3" in svg
    assert '<title>4 on 2026-09-07</title>' in svg and LEVELS[4] in svg  # peak day merged
    assert svg.count("<rect ") == 1 + 7 + 5
    print("demo ok")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        demo(); sys.exit()
    out, users = sys.argv[1], sys.argv[2:]
    token = os.environ["GITHUB_TOKEN"]
    # reuse the JetBrains Mono embed from the forge assets so text matches the other cards
    src = open(os.path.join(os.path.dirname(out), "about.svg"), encoding="utf8").read()
    fonts = "".join(re.findall(r"@font-face\{font-family:'JBM';[^}]+\}", src))
    with open(out, "w", encoding="utf8") as f:
        f.write(render([fetch(u, token) for u in users], users, fonts))
