"""程序说明：验证认证服务的默认安全行为与权限初始化逻辑。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.auth.service import AuthService
from src.db.connection import initialize_database


def create_auth_service(database_path: Path) -> tuple[sqlite3.Connection, AuthService]:
    """创建测试用认证服务。"""

    initialize_database(database_path)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection, AuthService(connection)


def test_auth_service_should_not_create_default_admin_implicitly(tmp_path: Path) -> None:
    """认证服务初始化时不应再自动创建弱口令管理员。"""

    connection, auth_service = create_auth_service(tmp_path / "app.db")
    _ = auth_service

    count = connection.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'").fetchone()[0]
    connection.close()

    assert count == 0


def test_authenticate_should_reject_inactive_user(tmp_path: Path) -> None:
    """被禁用用户即使密码正确，也不应通过认证。"""

    connection, auth_service = create_auth_service(tmp_path / "app.db")
    success, _message = auth_service.register_user("disabled_user", "StrongPass#123")
    assert success is True
    connection.execute("UPDATE users SET is_active = 0 WHERE username = ?", ("disabled_user",))
    connection.commit()

    user = auth_service.authenticate("disabled_user", "StrongPass#123")
    connection.close()

    assert user is None


def test_register_user_should_grant_default_ui_permissions(tmp_path: Path) -> None:
    """新注册用户应默认拥有当前 UI 所需的基础页签与知识库权限。"""

    connection, auth_service = create_auth_service(tmp_path / "app.db")
    success, _message = auth_service.register_user("normal_user", "StrongPass#123")
    assert success is True

    user_id = connection.execute(
        "SELECT user_id FROM users WHERE username = ?",
        ("normal_user",),
    ).fetchone()[0]
    permissions = auth_service.get_user_permissions(user_id)
    connection.close()

    assert permissions is not None
    assert {"AI 质检", "人工审核", "知识库管理", "知识库检索", "功能设置"}.issubset(set(permissions.tab_names))
    assert "default" in permissions.kb_ids


def test_register_user_should_store_password_with_pbkdf2_scheme(tmp_path: Path) -> None:
    """新注册用户应统一写入带盐 PBKDF2 密码哈希。"""

    connection, auth_service = create_auth_service(tmp_path / "app.db")
    success, _message = auth_service.register_user("pbkdf2_user", "StrongPass#123")
    assert success is True

    password_hash = connection.execute(
        "SELECT password_hash FROM users WHERE username = ?",
        ("pbkdf2_user",),
    ).fetchone()[0]
    connection.close()

    assert password_hash.startswith("pbkdf2_sha256$")
    assert auth_service._verify_password(password_hash, "StrongPass#123") is True


def test_authenticate_should_remain_compatible_with_legacy_sha256_hash(tmp_path: Path) -> None:
    """历史 SHA256 密码哈希仍应可登录，避免旧用户被破坏。"""

    connection, auth_service = create_auth_service(tmp_path / "app.db")
    legacy_hash = auth_service._hash_legacy_password("LegacyPass#123")
    connection.execute(
        """
        INSERT INTO users (user_id, username, password_hash, is_active, is_admin, created_at, updated_at)
        VALUES (?, ?, ?, 1, 0, '2026-05-13 16:00:00', '2026-05-13 16:00:00')
        """,
        ("legacy-user-1", "legacy_user", legacy_hash),
    )
    connection.commit()

    user = auth_service.authenticate("legacy_user", "LegacyPass#123")
    connection.close()

    assert user is not None
    assert user.username == "legacy_user"
