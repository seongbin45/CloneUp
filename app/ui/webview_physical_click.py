"""Physical click helpers for QWebEngineView (text → rect → mouse events).

JS ``element.click()`` is ignored on some GitHub Primer controls. We locate
targets by visible text, read ``getBoundingClientRect()``, then synthesize
real mouse press/release on the WebEngine focus proxy.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

# Find target by kind and return viewport CSS rect for a physical click.
# kind: "expiry" (want = "7"|"30"|"60"|"90"|"") | "generate"
_JS_FIND_TARGET_RECT = r"""
(function(kind, want) {
  const out = {
    ok: false, x: 0, y: 0, w: 0, h: 0, dpr: 1, zoom: 1,
    label: "", method: "", detail: ""
  };
  try { out.dpr = window.devicePixelRatio || 1; } catch (e) {}
  const txt = (el) =>
    ((el && (el.innerText || el.textContent || el.value || el.getAttribute("aria-label") || "")) + "")
      .replace(/\s+/g, " ").trim();
  const visible = (el) => {
    if (!el || !el.getBoundingClientRect) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    const st = window.getComputedStyle(el);
    if (st && (st.visibility === "hidden" || st.display === "none" || st.pointerEvents === "none"))
      return false;
    return r.bottom > 0 && r.right > 0 && r.top < (window.innerHeight || 800);
  };
  const pack = (el, method, label) => {
    const r = el.getBoundingClientRect();
    out.ok = true;
    out.x = r.left; out.y = r.top; out.w = r.width; out.h = r.height;
    out.method = method;
    out.label = (label || txt(el) || "").slice(0, 80);
    return JSON.stringify(out);
  };
  const isNone = (t) => /no expiration|만료 없음|never/i.test(t || "");
  const isDays = (t, d) => {
    if (!d) return false;
    return new RegExp("(^|\\b)" + d + "\\s*days?(\\b|$)", "i").test(t || "");
  };
  const w = (want == null ? "" : String(want)).trim();

  if (kind === "generate") {
    const nodes = Array.from(document.querySelectorAll(
      "button, input[type=submit], input[type=button], a.Button, [role=button]"
    ));
    for (const el of nodes) {
      const t = txt(el);
      if (!t || /Generate new token/i.test(t)) continue;
      if (/^Generate token$/i.test(t) && visible(el)) return pack(el, "generate-btn", t);
    }
    const form = document.querySelector(
      "#new_oauth_access, form[action*='settings/tokens'], form[action*='personal-access-tokens']"
    );
    if (form) {
      const sub = form.querySelector("button[type=submit], input[type=submit]");
      if (sub && visible(sub) && !/Generate new token/i.test(txt(sub)))
        return pack(sub, "generate-submit", txt(sub));
    }
    out.detail = "generate-not-found";
    return JSON.stringify(out);
  }

  if (kind === "expiry") {
    const ww = (!w || String(w).toLowerCase() === "none") ? "none" : w;
    // Primer action-menu: match data-value even if popover is closed
    const byVal = Array.from(document.querySelectorAll(
      "#token-expiration button[data-value], .js-new-default-token-expiration-item button[data-value], [role=menuitemradio][data-value]"
    ));
    for (const el of byVal) {
      const v = ((el.getAttribute("data-value") || "") + "").trim();
      const t = txt(el);
      const ok = (ww === "none" && (v === "none" || isNone(t))) ||
        (ww !== "none" && (v === ww || isDays(t, ww)));
      if (!ok) continue;
      const r = el.getBoundingClientRect();
      if (r.width >= 2 && r.height >= 2) return pack(el, "expiry-option", t || v);
    }
    const candidates = Array.from(document.querySelectorAll(
      "option, [role=option], [role=menuitem], [role=menuitemradio], label, button, a, li, summary"
    ));
    for (const el of candidates) {
      const t = txt(el);
      const v = ((el.getAttribute("data-value") || "") + "").trim();
      if (!t || t.length > 80) continue;
      const ok = (ww === "none" && (v === "none" || isNone(t))) ||
        (ww !== "none" && (v === ww || isDays(t, ww)));
      if (!ok || !visible(el)) continue;
      if (el.tagName === "OPTION" && el.parentElement) {
        const sel = el.parentElement;
        return pack(sel, "expiry-select", t + "|value=" + (el.value || ""));
      }
      return pack(el, "expiry-option", t);
    }
    // Opener label is often "30 days …", not the word Expiration
    const primerOpen = document.querySelector(
      ".js-new-default-token-expiration-select button[aria-haspopup], #token-expiration action-menu button[aria-haspopup], #token-expiration button[aria-haspopup]"
    );
    if (primerOpen && visible(primerOpen)) {
      return pack(primerOpen, "expiry-opener", txt(primerOpen) || "expiration-menu");
    }
    const openers = Array.from(document.querySelectorAll(
      "summary, button, [role=button], [aria-haspopup], select"
    ));
    for (const el of openers) {
      const t = txt(el);
      const idn = ((el.id || "") + " " + (el.name || "") + " " + (el.className || "")).toLowerCase();
      if (
        visible(el) && (
          /^Expiration$/i.test(t) ||
          (/Expiration/i.test(t) && t.length < 40) ||
          idn.indexOf("expire") >= 0 ||
          idn.indexOf("token-expiration") >= 0
        )
      ) {
        return pack(el, "expiry-opener", t || idn);
      }
    }
    out.detail = "expiry-not-found:" + ww;
    return JSON.stringify(out);
  }

  out.detail = "bad-kind";
  return JSON.stringify(out);
})
"""


def parse_target_rect(raw: object) -> dict[str, Any]:
    try:
        data = json.loads(str(raw) if raw is not None else "")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def physical_click_webview(
    view: Any,
    *,
    css_x: float,
    css_y: float,
    css_w: float,
    css_h: float,
    zoom: float = 1.0,
) -> bool:
    """
    Synthesize left-click at the center of a CSS viewport rect inside ``view``.
    """
    if view is None or css_w < 1 or css_h < 1:
        return False
    z = float(zoom) if zoom and zoom > 0 else 1.0
    # Map CSS viewport → widget local (WebEngine: content under focusProxy)
    lx = int((css_x + css_w / 2.0) * z)
    ly = int((css_y + css_h / 2.0) * z)
    target = None
    try:
        target = view.focusProxy()
    except Exception:
        target = None
    if target is None:
        target = view
    local = QPoint(lx, ly)
    # Clamp into widget
    try:
        wr = target.rect()
        lx = max(0, min(lx, max(0, wr.width() - 1)))
        ly = max(0, min(ly, max(0, wr.height() - 1)))
        local = QPoint(lx, ly)
    except Exception:
        pass

    try:
        target.setFocus(Qt.FocusReason.MouseFocusReason)
    except Exception:
        pass

    app = QApplication.instance()
    try:
        # Prefer QTest when available (more complete mouse sequence)
        from PySide6.QtTest import QTest

        QTest.mouseClick(target, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, local)
        if app is not None:
            app.processEvents()
        return True
    except Exception:
        pass

    # Fallback: send press + release
    try:
        global_pt = target.mapToGlobal(local)
        for etype, button_down in (
            (QMouseEvent.Type.MouseButtonPress, True),
            (QMouseEvent.Type.MouseButtonRelease, False),
        ):
            ev = QMouseEvent(
                etype,
                QPointF(local),
                QPointF(global_pt),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton if button_down else Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
            )
            QApplication.sendEvent(target, ev)
        if app is not None:
            app.processEvents()
        return True
    except Exception:
        return False


def find_target_and_physical_click(
    view: Any,
    *,
    kind: str,
    want: str = "",
    zoom: float = 1.0,
    on_done: Callable[[bool, str], None] | None = None,
) -> None:
    """
    Async: JS locate by text → physical click on rect → ``on_done(ok, detail)``.
    """
    if view is None or view.page() is None:
        if on_done:
            on_done(False, "no-view")
        return
    js = f"{_JS_FIND_TARGET_RECT}({kind!r},{want!r});"

    def _done(result: object) -> None:
        data = parse_target_rect(result)
        if not data.get("ok"):
            if on_done:
                on_done(False, str(data.get("detail") or "not-found"))
            return
        ok = physical_click_webview(
            view,
            css_x=float(data.get("x") or 0),
            css_y=float(data.get("y") or 0),
            css_w=float(data.get("w") or 0),
            css_h=float(data.get("h") or 0),
            zoom=zoom,
        )
        detail = f"{data.get('method')}:{data.get('label')}"
        if on_done:
            on_done(ok, detail if ok else "click-failed:" + detail)

    try:
        view.page().runJavaScript(js, _done)
    except Exception as e:
        if on_done:
            on_done(False, f"js-error:{e}")
