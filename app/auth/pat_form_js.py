"""Shared classic PAT form DOM helpers (Path A WebView + Path B CDP).

These scripts prefer the Primer hidden Expiration field — that value is what
GitHub POSTs — and a precise Generate token submit.
"""

from __future__ import annotations

# Set Expiration BEFORE Generate — prefer hidden field (form POST source of truth).
# Avoid clicking closed Primer menu items (Catalyst often ignores / reverts).
JS_SET_EXPIRATION = r"""
(function(want) {
  let w = (want == null ? "" : String(want)).trim();
  if (w === "" || w.toLowerCase() === "none") w = "none";
  const txt = (el) => ((el && (el.innerText || el.textContent || el.value || el.getAttribute("aria-label") || "")) + "").replace(/\s+/g, " ").trim();
  const isNoneLabel = (t) => /no expiration|만료 없음|never|없음/i.test(t || "");
  const isDaysLabel = (t, days) => {
    if (!days || days === "none") return false;
    return new RegExp("(^|\\b)" + days + "\\s*days?(\\b|$)", "i").test(t || "");
  };
  const fire = (el) => {
    try {
      el.dispatchEvent(new Event("input", { bubbles: true, cancelable: true }));
      el.dispatchEvent(new Event("change", { bubbles: true, cancelable: true }));
    } catch (e) {}
  };
  const setNative = (el, value) => {
    try {
      const proto = window.HTMLInputElement && window.HTMLInputElement.prototype;
      const desc = proto && Object.getOwnPropertyDescriptor(proto, "value");
      if (desc && desc.set) desc.set.call(el, value);
      else el.value = value;
    } catch (e) {
      el.value = value;
    }
    fire(el);
  };

  // --- A) Primer action-menu hidden input (current classic PAT) ---
  const root = document.querySelector("#token-expiration") || document;
  const hid = root.querySelector(
    "input[name='oauth_access[default_expires_at]'], input[name='oauth_access[expires_at]']"
  );
  if (hid) {
    const val = (w === "none" ? "none" : w);
    setNative(hid, val);
    // Keep menu UI roughly in sync (optional; submit uses hidden)
    const items = Array.from(root.querySelectorAll(
      "button[data-value], [role=menuitemradio][data-value]"
    ));
    for (const el of items) {
      const v = ((el.getAttribute("data-value") || "") + "").trim();
      const on = (val === "none" && (v === "none" || isNoneLabel(txt(el)))) ||
        (val !== "none" && v === val);
      try { el.setAttribute("aria-checked", on ? "true" : "false"); } catch (e) {}
    }
    if ((hid.value || "") === val || (val === "none" && !hid.value)) {
      return "set-hidden:" + (hid.value || val);
    }
    return "set-hidden-mismatch:" + (hid.value || "");
  }

  // --- B) Legacy native <select> ---
  const pickSelect = (sel) => {
    let matched = false;
    for (const opt of Array.from(sel.options || [])) {
      const v = (opt.value || "").trim();
      const t = txt(opt);
      if (w === "none" && (v === "" || v === "none" || isNoneLabel(t))) {
        sel.value = opt.value; matched = true; break;
      }
      if (w !== "none" && (v === w || isDaysLabel(t, w))) {
        sel.value = opt.value; matched = true; break;
      }
    }
    if (!matched) return "";
    fire(sel);
    return "set-select:" + (sel.value || "");
  };
  for (const sel of Array.from(document.querySelectorAll("select"))) {
    const idn = ((sel.id || "") + " " + (sel.name || "")).toLowerCase();
    if (idn.indexOf("expire") >= 0 || idn.indexOf("oauth_access") >= 0) {
      const r = pickSelect(sel);
      if (r) return r;
    }
  }
  return "no-select:" + w;
})
"""

JS_READ_EXPIRATION = r"""
(() => {
  const root = document.querySelector("#token-expiration") || document;
  const hid = root.querySelector(
    "input[name='oauth_access[default_expires_at]'], input[name='oauth_access[expires_at]']"
  );
  if (hid) return String(hid.value || "");
  for (const sel of Array.from(document.querySelectorAll("select"))) {
    const idn = ((sel.id || "") + " " + (sel.name || "")).toLowerCase();
    if (idn.indexOf("expire") >= 0 || idn.indexOf("oauth_access") >= 0) {
      return String(sel.value || "");
    }
  }
  return "";
})()
"""

# Submit classic PAT form. Prefer requestSubmit (fires validators) over .click().
JS_CLICK_GENERATE_TOKEN = r"""
(() => {
  const labelOf = (el) =>
    ((el.innerText || el.textContent || el.value || el.getAttribute("aria-label") || "") + "")
      .replace(/\s+/g, " ")
      .trim();
  const form = document.querySelector(
    "#new_oauth_access, form.new_oauth_access, form[action*='settings/tokens'], form[action*='personal-access-tokens']"
  );
  // 1) requestSubmit via the real Generate token button
  if (form) {
    const nodes = Array.from(form.querySelectorAll(
      "button[type=submit], input[type=submit], button, input[type=button]"
    ));
    for (const el of nodes) {
      const t = labelOf(el);
      if (!t || /Generate new token/i.test(t)) continue;
      if (/^Generate token$/i.test(t)) {
        try {
          if (typeof form.requestSubmit === "function") {
            form.requestSubmit(el);
            return "submitted:requestSubmit:" + t;
          }
        } catch (e) {}
        try { el.click(); return "clicked:" + t; } catch (e2) {}
      }
    }
    const sub = form.querySelector("button[type=submit], input[type=submit]");
    if (sub && !/Generate new token/i.test(labelOf(sub))) {
      try {
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit(sub);
          return "submitted:requestSubmit:form-submit";
        }
      } catch (e) {}
      try { sub.click(); return "clicked:form-submit:" + labelOf(sub); } catch (e2) {}
    }
  }
  // 2) Page-wide exact Generate token
  for (const el of Array.from(document.querySelectorAll(
    "button, input[type=submit], input[type=button], a.Button"
  ))) {
    const t = labelOf(el);
    if (!t || /Generate new token/i.test(t)) continue;
    if (/^Generate token$/i.test(t)) {
      try { el.click(); return "clicked:" + t; } catch (e) {}
    }
  }
  return "not-found";
})()
"""
