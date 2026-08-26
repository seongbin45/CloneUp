"""Cross-check: which GitHub sub-URLs start (or skip) away-return rollback."""

from __future__ import annotations

from app.ui.webview_flow_detect import (
    classify_webview_sample,
    should_start_away_return_countdown,
)

LOGGED_OUT = "Sign up for GitHub\nSign in to GitHub\nProduct"
LOGGED_IN = "Dashboard\nPull requests\nYour teams"

SAMPLES: list[tuple[str, str, str]] = [
    ("https://github.com/", LOGGED_OUT, "main LO"),
    ("https://github.com/", LOGGED_IN, "main LI"),
    ("https://github.com/login", "", "login"),
    ("https://github.com/login?return_to=%2Fsettings%2Ftokens%2Fnew", "", "login return_to"),
    ("https://github.com/logout", "", "logout"),
    ("https://github.com/sessions/two-factor", "", "2fa"),
    ("https://github.com/settings/tokens", LOGGED_IN, "tokens list LI"),
    ("https://github.com/settings/tokens/new?scopes=repo", LOGGED_IN, "tokens new LI"),
    ("https://github.com/settings/tokens", LOGGED_OUT, "tokens list LO"),
    ("https://github.com/settings/profile", LOGGED_IN, "settings profile LI"),
    ("https://github.com/settings/profile", LOGGED_OUT, "settings profile LO"),
    ("https://github.com/settings", LOGGED_IN, "settings root LI"),
    ("https://github.com/notifications", LOGGED_IN, "notifications LI"),
    ("https://github.com/notifications", LOGGED_OUT, "notifications LO"),
    ("https://github.com/explore", LOGGED_IN, "explore LI"),
    ("https://github.com/explore", LOGGED_OUT, "explore LO"),
    ("https://github.com/marketplace", LOGGED_OUT, "marketplace LO"),
    ("https://github.com/pulls", LOGGED_IN, "pulls LI"),
    ("https://github.com/issues", LOGGED_IN, "issues LI"),
    ("https://github.com/octocat", LOGGED_OUT, "profile LO"),
    ("https://github.com/octocat", LOGGED_IN, "profile LI"),
    ("https://github.com/octocat?tab=repositories", LOGGED_OUT, "repos tab LO"),
    ("https://github.com/octocat?tab=repositories", LOGGED_IN, "repos tab LI"),
    ("https://github.com/octocat/Hello-World", LOGGED_IN, "repo LI"),
    ("https://github.com/octocat/Hello-World", LOGGED_OUT, "repo LO"),
    ("https://github.com/orgs/github", LOGGED_IN, "org LI"),
    ("https://github.com/orgs/github", LOGGED_OUT, "org LO"),
    ("https://github.com/features", LOGGED_OUT, "features LO"),
    ("https://github.com/pricing", LOGGED_OUT, "pricing LO"),
    ("https://github.com/new", LOGGED_IN, "new LI"),
    ("https://github.com/search?q=cloneup", LOGGED_IN, "search LI"),
    ("https://github.com/dashboard", LOGGED_IN, "dashboard LI"),
    ("https://github.com/dashboard", LOGGED_OUT, "dashboard LO"),
    ("https://github.com/settings/personal-access-tokens/new", LOGGED_IN, "fine new"),
    ("https://accounts.google.com/o/oauth2/auth", "", "google oauth"),
    ("https://appleid.apple.com/auth/authorize?client_id=x", "", "apple"),
    ("https://www.youtube.com/watch?v=1", "watch", "youtube"),
]


def main() -> int:
    print(f"{'label':28} {'kind':12} {'rb':5} url")
    print("-" * 100)
    stagnate: list[str] = []
    rollback: list[str] = []
    for url, html, label in SAMPLES:
        kind, idx, _meta = classify_webview_sample(url, title="", html=html)
        rb = should_start_away_return_countdown(kind, url)
        mark = "YES" if rb else "no"
        print(f"{label:28} {kind:12} {mark:5} {url}")
        row = f"{label} | {kind} idx={idx} | {url}"
        (rollback if rb else stagnate).append(row)
    print("\n=== ROLLBACK (5s → tokens/new) ===")
    for r in rollback:
        print(" +", r)
    print("\n=== NO ROLLBACK (정체 가능) ===")
    for r in stagnate:
        print(" -", r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
