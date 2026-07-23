# Work Radar

A personal macOS menu bar dashboard, built as a [SwiftBar](https://github.com/swiftbar/SwiftBar) plugin.

It sits in the menu bar as a sunglasses icon.
Click it to open a dropdown with everything that needs your attention right now.

## What it shows

1. **PRs awaiting approval** - your own open pull requests that still need review.
   Each row shows how many of the required approvals it has so far (`0/2`, `1/2`).
   PRs with changes requested are flagged and sorted to the top, then the least-approved and oldest.
   Fully approved and draft PRs are hidden, since they no longer need you.
   The submenu on each PR shows the repo, age, and who approved or requested changes.
2. **Sprint · In Progress** - your current-sprint stories in the `In Progress` status.
3. **Sprint · To Do** - your current-sprint stories in the `To Do` status.

Every row is clickable and opens the PR or Jira issue in your browser.
The footer shows the last refresh time, a manual "Refresh now" action, and quick links to GitHub and your Jira board.

## How it works

The plugin is a single Python script, `dashboard.5m.py`.
The `.5m.` in the filename tells SwiftBar to run it every 5 minutes in the background.
Opening the menu is instant because it shows the last cached result; use "Refresh now" for an on-demand update.

It reuses your already-authenticated command line tools rather than managing any of its own auth:

- **GitHub** via the `gh` CLI - one GraphQL call returns your open PRs with their approval state.
- **Jira** via the `jira` CLI - one call per status against your current sprint.

The Jira server and board are read from your `jira-cli` config, so nothing in this repository is specific to any one person or organization.
Because it shells out to these CLIs, there are no API tokens stored in this repository.

## Setup (new machine or teammate)

You need [Homebrew](https://brew.sh) and macOS.
From a clone of this repo, run:

```sh
./setup.sh
```

The script is idempotent and handles everything:

- installs `gh`, `jira-cli`, and SwiftBar if missing,
- authenticates the GitHub CLI if needed,
- verifies `jira-cli` is configured,
- stores your Jira API token in the login Keychain,
- links the plugin into `~/.swiftbar`, points SwiftBar at it, and enables launch at login.

### Authenticate the two CLIs first

Everything is per-user, driven by these two logins:

- **GitHub:** `gh auth login`
- **Jira:** `jira init` - you'll need a Jira API token from
  <https://id.atlassian.com/manage-profile/security/api-tokens>.

## Jira token

The `jira` CLI reads its token from the `JIRA_API_TOKEN` environment variable, which normally comes from your shell.
SwiftBar does not load your shell config, so the token is also kept in the macOS login Keychain under the service `work-radar-jira`, and the plugin retrieves it at runtime.
`setup.sh` stores it for you.

If you rotate your Jira API token, update the Keychain copy:

```sh
security add-generic-password -U -a "$USER" -s work-radar-jira -T /usr/bin/security -w "<new-token>"
```

The plugin prefers `JIRA_API_TOKEN` from the environment if present, and falls back to the Keychain otherwise.

## Customizing

- **Refresh interval** - rename the file, changing `5m` to any interval such as `1m`, `10m`, or `1h`.
- **Required approvals** - set the `WORK_RADAR_REQUIRED_APPROVALS` env var, or change the default in the script.
- **Which PRs** - the search query is `author:@me is:pr is:open` in `fetch_prs`; adjust it to change scope.
- **Server / board** - detected automatically from your `jira-cli` config; no code change needed.

## Troubleshooting

Run the plugin directly to see its raw output and any errors:

```sh
./dashboard.5m.py
```

To simulate SwiftBar's minimal environment (no shell config):

```sh
env -i HOME="$HOME" PATH="/usr/bin:/bin" ./dashboard.5m.py
```

If the menu bar icon turns into a warning triangle, one or both data sources failed.
Open the menu; the failing section shows the error message in its submenu.

To force a refresh from the command line:

```sh
open "swiftbar://refreshallplugins"
```
