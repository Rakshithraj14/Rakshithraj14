"""Local GraphQL relay that folds extra GitHub accounts into the main account's contributions.

The 3D contrib action reads GITHUB_ENDPOINT, so pointing it here makes it draw one
calendar with every account's contributions summed per day.

Usage: python merge_proxy.py PORT extra_user1 [extra_user2 ...]
"""
import json, sys, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

UPSTREAM = "https://api.github.com/graphql"
LEVELS = ["NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE"]
TOTALS = ["totalCommitContributions", "totalIssueContributions", "totalPullRequestContributions",
          "totalPullRequestReviewContributions", "totalRepositoryContributions"]


def post(body, auth):
    req = urllib.request.Request(UPSTREAM, data=json.dumps(body).encode(), headers={
        "Authorization": auth, "Content-Type": "application/json", "User-Agent": "forge-merge"})
    return json.load(urllib.request.urlopen(req))


def merge(main, extras):
    """Sum extra accounts' contributionsCollection into main's, in place. Returns main."""
    col = main["data"]["user"]["contributionsCollection"]
    cal = col["contributionCalendar"]
    days = [d for w in cal["weeks"] for d in w["contributionDays"]]
    by_date = {d["date"][:10]: d for d in days}
    for extra in extras:
        ecol = extra["data"]["user"]["contributionsCollection"]
        for w in ecol["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                if d["date"][:10] in by_date:
                    by_date[d["date"][:10]]["contributionCount"] += d["contributionCount"]
        for k in TOTALS:
            if k in col:
                col[k] += ecol[k]
        if "commitContributionsByRepository" in col:
            col["commitContributionsByRepository"] += ecol["commitContributionsByRepository"]
    if "totalContributions" in cal:
        cal["totalContributions"] = sum(d["contributionCount"] for d in days)
    # re-bucket like GitHub: quartiles of the non-zero days
    nz = sorted(d["contributionCount"] for d in days if d["contributionCount"])
    cuts = [nz[len(nz) * q // 4] for q in (1, 2, 3)] if nz else []
    for d in days:
        n = d["contributionCount"]
        d["contributionLevel"] = LEVELS[0 if n == 0 else 1 + sum(n >= c for c in cuts)]
    return main


class Relay(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        auth = self.headers["Authorization"]
        res = post(body, auth)
        if "contributionCalendar" in body["query"] and res.get("data"):
            extras = [post({**body, "variables": {**body["variables"], "login": u}}, auth) for u in EXTRA]
            res = merge(res, extras)
        out = json.dumps(res).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def demo():
    resp = lambda counts, commits: {"data": {"user": {"contributionsCollection": {
        "totalCommitContributions": commits, "commitContributionsByRepository": [{"x": commits}],
        "contributionCalendar": {"totalContributions": sum(counts), "weeks": [{"contributionDays": [
            {"date": f"2026-09-0{i + 1}T00:00:00.000+00:00", "contributionCount": c, "contributionLevel": "NONE"}
            for i, c in enumerate(counts)]}]}}}}}
    m = merge(resp([0, 1, 2, 0, 5], 8), [resp([0, 3, 0, 1, 0], 4)])
    col = m["data"]["user"]["contributionsCollection"]
    days = col["contributionCalendar"]["weeks"][0]["contributionDays"]
    assert [d["contributionCount"] for d in days] == [0, 4, 2, 1, 5]
    assert [d["contributionLevel"] for d in days] == [
        "NONE", "THIRD_QUARTILE", "SECOND_QUARTILE", "FIRST_QUARTILE", "FOURTH_QUARTILE"]
    assert col["contributionCalendar"]["totalContributions"] == 12
    assert col["totalCommitContributions"] == 12 and len(col["commitContributionsByRepository"]) == 2
    print("demo ok")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        demo(); sys.exit()
    EXTRA = sys.argv[2:]
    HTTPServer(("127.0.0.1", int(sys.argv[1])), Relay).serve_forever()
