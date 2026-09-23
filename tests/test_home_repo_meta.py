"""P4b: home repo meta resolution."""

from __future__ import annotations

from pathlib import Path

from app.ui.home_repo_meta import resolve_home_repo_meta


def test_no_git_folder_returns_empty(tmp_path: Path) -> None:
    d = tmp_path / "plain"
    d.mkdir()
    meta = resolve_home_repo_meta(d, login="me")
    assert meta.origin_display == "—"
    assert meta.visibility == "—"
    assert meta.is_mine is None


def test_owner_match_sets_is_mine(monkeypatch, tmp_path: Path) -> None:
    from types import SimpleNamespace

    repo = tmp_path / "r"
    repo.mkdir()
    (repo / ".git").mkdir()

    def fake_status(_folder):
        return SimpleNamespace(
            origin_url="https://github.com/alice/demo.git",
            has_origin=True,
        )

    monkeypatch.setattr("app.git.sync_ops.get_repo_status", fake_status)
    monkeypatch.setattr(
        "app.github.api_client.get_repo_access",
        lambda *a, **k: None,
    )
    meta = resolve_home_repo_meta(repo, login="alice")
    assert meta.is_mine is True
    assert meta.owner == "alice"
    assert "demo" in meta.origin_display


def test_unknown_ownership_cta_treats_as_mine(monkeypatch, tmp_path: Path) -> None:
    """login=None + no API → is_mine None → CTA must be dirty/clean, not not_mine."""
    from types import SimpleNamespace

    from app.ui.home_cta import ProjectKind, build_cta_plan, home_project_kind

    repo = tmp_path / "r"
    repo.mkdir()
    (repo / ".git").mkdir()

    monkeypatch.setattr(
        "app.git.sync_ops.get_repo_status",
        lambda _f: SimpleNamespace(
            origin_url="https://github.com/other/x.git",
            has_origin=True,
        ),
    )
    monkeypatch.setattr(
        "app.github.api_client.get_repo_access",
        lambda *a, **k: None,
    )

    meta = resolve_home_repo_meta(repo, login=None)
    assert meta.is_mine is None
    # Defensive coalesce used by home_shell
    is_mine = True if meta.is_mine is None else meta.is_mine
    assert is_mine is True
    assert home_project_kind(has_git=True, is_mine=None, dirty=True) is ProjectKind.DIRTY
    assert home_project_kind(has_git=True, is_mine=None, dirty=False) is ProjectKind.CLEAN
    plan = build_cta_plan(has_git=True, is_mine=None, dirty=True, signed_in=False)
    assert plan.kind is ProjectKind.DIRTY
    assert plan.actions[0].label.startswith("로그인하고 올리기")
    assert "다른 사람" not in (plan.note or "")


def test_api_private_visibility(monkeypatch, tmp_path: Path) -> None:
    from types import SimpleNamespace

    repo = tmp_path / "r"
    repo.mkdir()
    (repo / ".git").mkdir()

    monkeypatch.setattr(
        "app.git.sync_ops.get_repo_status",
        lambda _f: SimpleNamespace(
            origin_url="https://github.com/bob/x.git",
            has_origin=True,
        ),
    )
    monkeypatch.setattr(
        "app.github.api_client.get_repo_access",
        lambda *a, **k: {"push": False, "private": True, "allow_forking": True},
    )
    monkeypatch.setattr("app.auth.token_store.load_token", lambda: "tok")
    meta = resolve_home_repo_meta(repo, login="alice")
    assert meta.is_mine is False
    assert meta.visibility == "비공개"
