"""Background helpers for Path B CDP / UIA so the guide dialog stays responsive.

All Playwright CDP connect/evaluate and CDP port polling run here — never on
the Qt UI thread. UIA fallback also runs in the worker (Windows UIA is OK
off-main).
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class PathBAddressWorker(QThread):
    """One-shot browser sample (+ optional Expiration OCR) off the UI thread.

    Emits a dict: ``{sample, expiry_days, expiry_detail}``.

    On ASK_EXPIRY, prefer ``sample_address=False`` so we skip the slow UIA
    page walk and only run fast screenshot OCR.
    """

    sample_ready = Signal(object)

    def __init__(
        self,
        *,
        read_expiry: bool = False,
        sample_address: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._read_expiry = bool(read_expiry)
        self._sample_address = bool(sample_address)

    def run(self) -> None:  # noqa: N802
        sample = None
        expiry_days = None
        expiry_detail = ""
        if self._sample_address:
            try:
                from app.util.browser_address import read_browser_page_sample

                sample = read_browser_page_sample()
            except Exception as e:
                expiry_detail = f"sample-error:{e}"
            # UIA miss on passkey / email auth → screenshot OCR supplement.
            # Skipped when UIA already classified auth (cheap path).
            try:
                from app.util.auth_ocr import enrich_sample_with_auth_ocr

                sample, ocr_det = enrich_sample_with_auth_ocr(sample)
                if ocr_det and ocr_det.startswith("ocr-"):
                    if expiry_detail:
                        expiry_detail = f"{expiry_detail}|{ocr_det}"
                    else:
                        expiry_detail = ocr_det
            except Exception as e:
                extra = f"auth-ocr-error:{e}"
                expiry_detail = (
                    f"{expiry_detail}|{extra}" if expiry_detail else extra
                )
        if self._read_expiry:
            parts: list[str] = []
            try:
                from app.util.expiry_ocr import read_token_expiration_ocr

                expiry_days, d_ocr = read_token_expiration_ocr()
                parts.append(f"ocr:{d_ocr}")
            except Exception as e:
                expiry_days = None
                parts.append(f"ocr-error:{e}")
            # UIA tree walk is slow — only if OCR missed.
            if expiry_days is None:
                try:
                    from app.util.browser_address import read_token_expiration_uia

                    uia_days, d_uia = read_token_expiration_uia()
                    parts.append(f"uia:{d_uia}")
                    if uia_days is not None:
                        expiry_days = uia_days
                except Exception as e:
                    parts.append(f"uia-error:{e}")
            expiry_detail = "|".join(parts)
        self.sample_ready.emit(
            {
                "sample": sample,
                "expiry_days": expiry_days,
                "expiry_detail": expiry_detail or "",
            }
        )


class PathBAssistWorker(QThread):
    """One-shot background op for Path B browser assist.

    ``op``:
      - ``wait_ready`` — poll CDP ``/json/version``
      - ``expiry`` — CDP Expiration then UIA fallback (needs ``days``)
      - ``generate`` — CDP Generate then UIA fallback
      - ``nudge`` — expiry (if needed) then generate (needs ``days``, ``skip_expiry``)
    """

    finished_result = Signal(str, bool, str)  # op, ok, detail

    def __init__(
        self,
        op: str,
        *,
        days: str | None = None,
        skip_expiry: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._op = (op or "").strip()
        self._days = (days or "90").strip() or "90"
        self._skip_expiry = bool(skip_expiry)

    def run(self) -> None:  # noqa: N802
        op = self._op
        try:
            if op == "wait_ready":
                from app.util.browser_cdp import wait_for_cdp_ready

                ok = wait_for_cdp_ready(attempts=12, interval_s=0.35)
                self.finished_result.emit(op, bool(ok), "ready" if ok else "timeout")
                return

            if op == "expiry":
                ok, detail = self._run_expiry(self._days)
                self.finished_result.emit(op, bool(ok), detail)
                return

            if op == "generate":
                ok, detail = self._run_generate()
                self.finished_result.emit(op, bool(ok), detail)
                return

            if op == "nudge":
                parts: list[str] = []
                if not self._skip_expiry:
                    ok_e, det_e = self._run_expiry(self._days)
                    parts.append(f"expiry:{det_e}")
                    if not ok_e:
                        # Still try Generate (same as previous nudge UX).
                        pass
                ok_g, det_g = self._run_generate()
                parts.append(f"generate:{det_g}")
                self.finished_result.emit(op, bool(ok_g), "|".join(parts))
                return

            self.finished_result.emit(op, False, f"unknown-op:{op}")
        except Exception as e:
            self.finished_result.emit(op, False, f"worker-error:{e}")

    @staticmethod
    def _run_expiry(days: str) -> tuple[bool, str]:
        from app.util.browser_address import try_set_token_expiration_uia
        from app.util.browser_cdp import try_cdp_expiration_then_uia_fallback

        try:
            return try_cdp_expiration_then_uia_fallback(
                days,
                uia_fallback=lambda d: try_set_token_expiration_uia(
                    d, allow_click=True
                ),
            )
        except Exception:
            return try_set_token_expiration_uia(days, allow_click=True)

    @staticmethod
    def _run_generate() -> tuple[bool, str]:
        from app.util.browser_address import try_invoke_generate_token_button
        from app.util.browser_cdp import try_cdp_generate_then_uia_fallback

        try:
            return try_cdp_generate_then_uia_fallback(
                uia_fallback=lambda: try_invoke_generate_token_button(
                    allow_click=True
                ),
            )
        except Exception:
            return try_invoke_generate_token_button(allow_click=True)
