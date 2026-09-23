# P3 gate — `active_palette` / `p.` remnant check

Date: 2026-09-09

```text
grep active_palette|del p|p.  app/ui/home_shell.py app/ui/home_chrome.py
```

| File | Result |
|------|--------|
| `home_shell.py` | **0** `active_palette` · **0** `del p` · chrome uses `HOME_COLORS` only |
| `home_chrome.py` | Still uses `active_palette` — **intentional** (shared Git banner / overflow also used outside home; dual light/dark) |

P3 proceeds with home_shell gate clean.
