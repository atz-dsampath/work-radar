#!/usr/bin/python3
# <swiftbar.title>Work Radar</swiftbar.title>
# <swiftbar.version>1.0</swiftbar.version>
# <swiftbar.author>Work Radar</swiftbar.author>
# <swiftbar.desc>My open PRs awaiting approval + my current-sprint To Do / In Progress stories.</swiftbar.desc>
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
"""
Work Radar - a SwiftBar menu bar dashboard.

Sections:
  1. PRs I opened that still need approval (2 approvals required), with how many
     approvals each has so far. Fully approved and draft PRs are hidden.
  2. My current-sprint stories that are In Progress.
  3. My current-sprint stories that are To Do.

Reuses the already-authenticated `gh` and `jira` CLIs, so there are no tokens in
this file. Runs on a 5-minute interval (see the .5m. in the filename).
"""

import json
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

# --- Config -----------------------------------------------------------------
# Approvals a PR needs before it drops off the list (override via env var).
REQUIRED_APPROVALS = int(os.environ.get("WORK_RADAR_REQUIRED_APPROVALS", "2"))
# Keychain service that stores the Jira API token (see setup.sh / README).
JIRA_TOKEN_SERVICE = "work-radar-jira"
GITHUB_PR_URL = "https://github.com/pulls?q=is%3Aopen+is%3Apr+author%3A%40me+archived%3Afalse"
CLI_TIMEOUT = 30  # seconds per CLI call
# JIRA_SERVER / JIRA_BOARD_URL are read from your jira-cli config below, so there
# is nothing org-specific hardcoded in this file.

# Colors chosen to read well in both light and dark menus.
MUTED = "#8e8e93"
RED = "#ff453a"
ORANGE = "#ff9f0a"
GREEN = "#32d74b"

# SwiftBar runs plugins with a slim PATH; make sure Homebrew + system dirs are on it.
ENV = {**os.environ}
ENV["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:" + ENV.get("PATH", "")


def resolve(name, default):
    if os.path.exists(default):
        return default
    return shutil.which(name, path=ENV["PATH"]) or default


GH = resolve("gh", "/opt/homebrew/bin/gh")
JIRA = resolve("jira", "/opt/homebrew/bin/jira")


def read_jira_config():
    """Read the Jira server URL and board id from the jira-cli config file.

    This keeps the plugin free of any org-specific values: each teammate only
    needs `jira init`, and their own server + board are picked up here.
    """
    server, board_id = None, None
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    candidates = [
        os.environ.get("JIRA_CONFIG_FILE"),
        os.path.join(xdg, ".jira", ".config.yml"),
        os.path.expanduser("~/.jira/.config.yml"),
    ]
    path = next((p for p in candidates if p and os.path.exists(p)), None)
    if not path:
        return server, board_id
    try:
        in_board = False
        with open(path) as f:
            for line in f:
                if server is None:
                    m = re.match(r"server:\s*(\S+)", line)
                    if m:
                        server = m.group(1).strip().rstrip("/")
                if re.match(r"\S", line):              # a top-level key
                    in_board = line.strip() == "board:"
                elif in_board and board_id is None:    # indented under `board:`
                    m = re.search(r"\bid:\s*(\d+)", line)
                    if m:
                        board_id = m.group(1)
    except Exception:
        pass
    return server, board_id


JIRA_SERVER, JIRA_BOARD_ID = read_jira_config()
JIRA_BOARD_URL = (
    "%s/secure/RapidBoard.jspa?rapidView=%s" % (JIRA_SERVER, JIRA_BOARD_ID)
    if JIRA_SERVER and JIRA_BOARD_ID else (JIRA_SERVER or "")
)


def jira_env():
    """Env for `jira`, ensuring JIRA_API_TOKEN is set (from shell or Keychain)."""
    env = dict(ENV)
    if not env.get("JIRA_API_TOKEN"):
        try:
            r = subprocess.run(
                ["/usr/bin/security", "find-generic-password", "-w", "-s", JIRA_TOKEN_SERVICE],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0 and r.stdout.strip():
                env["JIRA_API_TOKEN"] = r.stdout.strip()
        except Exception:
            pass
    return env


JIRA_ENV = jira_env()


# --- Helpers ----------------------------------------------------------------
def run(cmd, env=ENV):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=CLI_TIMEOUT, env=env)


def esc(s):
    """SwiftBar uses '|' to separate text from params, so neutralize it."""
    return (s or "").replace("|", "\u00a6").replace("\n", " ").strip()


def truncate(s, n=52):
    return s if len(s) <= n else s[: n - 1] + "\u2026"


def human_age(iso):
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        if delta.days >= 1:
            return "%dd ago" % delta.days
        hours = delta.seconds // 3600
        if hours >= 1:
            return "%dh ago" % hours
        return "%dm ago" % (delta.seconds // 60)
    except Exception:
        return "recently"


# --- Data: GitHub -----------------------------------------------------------
def fetch_prs():
    q = "author:@me is:pr is:open archived:false"
    query = (
        "query($q:String!){ search(query:$q, type:ISSUE, first:50){ nodes{ "
        "... on PullRequest{ number title url isDraft createdAt "
        "repository{nameWithOwner} reviewDecision "
        "latestOpinionatedReviews(first:50){nodes{state author{login}}} } } } }"
    )
    r = run([GH, "api", "graphql", "-f", "q=" + q, "-f", "query=" + query])
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "gh graphql failed")

    nodes = json.loads(r.stdout)["data"]["search"]["nodes"]
    prs = []
    for p in nodes:
        if not p or p.get("isDraft"):
            continue
        if p.get("reviewDecision") == "APPROVED":  # already has its 2 approvals
            continue
        revs = (p.get("latestOpinionatedReviews") or {}).get("nodes") or []
        approvers = [x["author"]["login"] for x in revs if x.get("state") == "APPROVED" and x.get("author")]
        changers = [x["author"]["login"] for x in revs if x.get("state") == "CHANGES_REQUESTED" and x.get("author")]
        prs.append({
            "number": p["number"],
            "title": p["title"],
            "url": p["url"],
            "repo": p["repository"]["nameWithOwner"],
            "created": p["createdAt"],
            "approvers": approvers,
            "changers": changers,
        })
    # Most urgent first: changes-requested, then fewest approvals, then oldest.
    prs.sort(key=lambda x: (len(x["changers"]) == 0, len(x["approvers"]), x["created"]))
    return prs


# --- Data: Jira -------------------------------------------------------------
def jira_me():
    r = run([JIRA, "me"], env=JIRA_ENV)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "jira me failed")
    return r.stdout.strip().splitlines()[0].strip()


def fetch_sprint(me, status):
    r = run([
        JIRA, "sprint", "list", "--current", "-a", me, "-s", status,
        "--plain", "--no-headers", "--columns", "KEY,SUMMARY",
    ], env=JIRA_ENV)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "jira sprint list failed")
    items = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)  # KEY has no spaces; rest is the summary
        if len(parts) == 2:
            items.append({"key": parts[0], "summary": parts[1]})
    return items


# --- Render -----------------------------------------------------------------
def main():
    body = []
    pr_count = None
    sprint_count = 0
    had_error = False

    # Kick off all network calls at once so a refresh takes about as long as the
    # single slowest call rather than the sum of them.
    pool = ThreadPoolExecutor(max_workers=4)
    f_prs = pool.submit(fetch_prs)
    sprint_futures = {}
    jira_error = None
    try:
        me = jira_me()
        for status in ("In Progress", "To Do"):
            sprint_futures[status] = pool.submit(fetch_sprint, me, status)
    except Exception as e:
        jira_error = e

    # PRs awaiting my approval
    try:
        prs = f_prs.result()
        pr_count = len(prs)
        body.append("---")
        body.append("PRs awaiting approval (%d) | size=13 color=%s" % (len(prs), MUTED))
        if not prs:
            body.append("All caught up | color=%s sfimage=checkmark.seal.fill" % GREEN)
        for p in prs:
            n_appr = len(p["approvers"])
            changes = len(p["changers"]) > 0
            if changes:
                icon, color = "exclamationmark.triangle.fill", ORANGE
            elif n_appr >= 1:
                icon, color = "circle.lefthalf.filled", ""
            else:
                icon, color = "circle", ""
            badge = "changes \u00b7 %d/%d" % (n_appr, REQUIRED_APPROVALS) if changes else "%d/%d" % (n_appr, REQUIRED_APPROVALS)
            text = "#%d  %s   %s" % (p["number"], truncate(esc(p["title"]), 48), badge)
            params = "href=%s sfimage=%s size=14" % (p["url"], icon)
            if color:
                params += " color=%s" % color
            body.append("%s | %s" % (text, params))
            body.append("-- %s \u00b7 opened %s | href=%s" % (p["repo"], human_age(p["created"]), p["url"]))
            if p["approvers"]:
                body.append("-- Approved by %s | color=%s" % (esc(", ".join(p["approvers"])), GREEN))
            if p["changers"]:
                body.append("-- Changes requested by %s | color=%s" % (esc(", ".join(p["changers"])), ORANGE))
    except Exception as e:
        had_error = True
        body.append("---")
        body.append("PRs: couldn't load | color=%s sfimage=exclamationmark.triangle.fill" % RED)
        body.append("-- %s" % truncate(esc(str(e)), 300))

    # Current sprint: In Progress, then To Do
    if jira_error is not None:
        had_error = True
        body.append("---")
        body.append("Jira: couldn't load | color=%s sfimage=exclamationmark.triangle.fill" % RED)
        body.append("-- %s" % truncate(esc(str(jira_error)), 300))
    else:
        for label, status, icon in [
            ("Sprint \u00b7 In Progress", "In Progress", "circle.fill"),
            ("Sprint \u00b7 To Do", "To Do", "circle"),
        ]:
            try:
                items = sprint_futures[status].result()
                sprint_count += len(items)
                body.append("---")
                body.append("%s (%d) | size=13 color=%s" % (label, len(items), MUTED))
                if not items:
                    body.append("None | color=%s" % MUTED)
                for it in items:
                    url = "%s/browse/%s" % (JIRA_SERVER, it["key"])
                    body.append("%s  %s | href=%s sfimage=%s size=14" % (
                        it["key"], truncate(esc(it["summary"]), 50), url, icon))
            except Exception as e:
                had_error = True
                body.append("---")
                body.append("%s: couldn't load | color=%s sfimage=exclamationmark.triangle.fill" % (label, RED))
                body.append("-- %s" % truncate(esc(str(e)), 300))

    pool.shutdown(wait=False)

    # Menu bar: icon only (all counts live in the dropdown).
    if had_error and pr_count is None and sprint_count == 0:
        print("| sfimage=exclamationmark.triangle.fill color=%s" % RED)  # everything failed
    elif had_error:
        print("| sfimage=sunglasses.fill color=%s" % ORANGE)  # one source failed
    else:
        print("| sfimage=sunglasses.fill")

    for line in body:
        print(line)

    # Footer
    print("---")
    print("Refreshed %s | size=11 color=%s" % (datetime.now().strftime("%-I:%M %p"), MUTED))
    print("Refresh now | refresh=true sfimage=arrow.clockwise")
    print("Open my PRs on GitHub | href=%s sfimage=arrow.up.forward.square" % GITHUB_PR_URL)
    if JIRA_BOARD_URL:
        print("Open sprint board | href=%s sfimage=arrow.up.forward.square" % JIRA_BOARD_URL)


if __name__ == "__main__":
    main()
