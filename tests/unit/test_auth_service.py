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


def test_auth_service_should_create_default_admin_on_initialization(tmp_path: Path) -> None:
    """数据库初始化时应自动创建 admin/admin 用户并开通全部权限。"""

    connection, auth_service = create_auth_service(tmp_path / "app.db")

    # admin 用户应存在
    admin_row = connection.execute("SELECT user_id, is_admin FROM users WHERE username = 'admin'").fetchone()
    assert admin_row is not None
    assert admin_row["is_admin"] == 1

    # 应能用 admin/admin 登录
    user = auth_service.authenticate("admin", "admin")
    assert user is not None
    assert user.username == "admin"
    assert user.is_admin is True

    # admin 应拥有全部 tab 和知识库权限
    permissions = auth_service.get_user_permissions(admin_row["user_id"])
    assert permissions is not None
    assert set(permissions.tab_names) == {"AI 质检", "人工审核", "知识库管理", "知识库检索", "PageIndex 深度检索", "功能设置"}

    connection.close()


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


def test_register_user_should_not_grant_any_default_permissions(tmp_path: Path) -> None:
    """除 admin 外，新注册用户默认不应拥有任何菜单或知识库权限。"""

    connection, auth_service = create_auth_service(tmp_path / "app.db")
    success, _message = auth_service.register_user("normal_user", "StrongPass#123")
    assert success is True

    user_id = connection.execute(
        "SELECT user_id FROM users WHERE username = ?",
        ("normal_user",),
    ).fetchone()[0]
    permissions = auth_service.get_user_permissions(user_id)
    tab_access_count = connection.execute(
        "SELECT COUNT(*) FROM user_tab_access WHERE user_id = ?",
        (user_id,),
    ).fetchone()[0]
    kb_access_count = connection.execute(
        "SELECT COUNT(*) FROM user_kb_access WHERE user_id = ?",
        (user_id,),
    ).fetchone()[0]
    connection.close()

    assert permissions is not None
    assert permissions.tab_names == []
    assert permissions.kb_ids == []
    assert tab_access_count == 0
    assert kb_access_count == 0


def test_register_user_should_reject_password_longer_than_20_chars(tmp_path: Path) -> None:
    """注册密码超过 20 个字符时，应直接返回业务错误。"""

    connection, auth_service = create_auth_service(tmp_path / "app.db")

    success, message = auth_service.register_user("too_long_user", "123456789012345678901")
    user_count = connection.execute(
        "SELECT COUNT(*) FROM users WHERE username = ?",
        ("too_long_user",),
    ).fetchone()[0]
    connection.close()

    assert success is False
    assert message == "密码长度不能超过20个字符"
    assert user_count == 0


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


def test_list_users_should_include_registered_non_admin_users(tmp_path: Path) -> None:
    """用户列表应能返回已注册普通用户，供后台用户管理页面消费。"""

    connection, auth_service = create_auth_service(tmp_path / "app.db")
    success, _message = auth_service.register_user("list_user", "StrongPass#123")
    assert success is True

    users = auth_service.list_users()
    connection.close()

    target_user = next(item for item in users if item["username"] == "list_user")
    assert target_user["is_admin"] is False
    assert str(target_user["user_id"]).strip() != ""
    # admin 用户也应存在
    admin_user = next(item for item in users if item["username"] == "admin")
    assert admin_user["is_admin"] is True


def test_update_user_permissions_should_persist_tabs_and_knowledge_bases(tmp_path: Path) -> None:
    """显式配置后的菜单权限与知识库权限应可正确读回。"""

    connection, auth_service = create_auth_service(tmp_path / "app.db")
    success, _message = auth_service.register_user("permission_user", "StrongPass#123")
    assert success is True
    user_id = connection.execute(
        "SELECT user_id FROM users WHERE username = ?",
        ("permission_user",),
    ).fetchone()[0]

    updated, message = auth_service.update_user_permissions(
        user_id,
        ["知识库检索", "文档管理"],
        ["default"],
    )
    permissions = auth_service.get_user_permissions(user_id)
    connection.close()

    assert updated is True
    assert message == "权限已更新"
    assert permissions is not None
    assert permissions.tab_names == ["知识库检索", "知识库管理"]
    assert permissions.kb_ids == ["default"]


def test_initialize_database_should_upgrade_legacy_user_permissions_table(tmp_path: Path) -> None:
    """旧 user_permissions 表应自动升级到新结构，并迁移历史权限数据。"""

    database_path = tmp_path / "legacy_auth.db"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE users (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE user_tab_access (
            user_id TEXT NOT NULL,
            tab_name TEXT NOT NULL,
            PRIMARY KEY (user_id, tab_name)
        );

        CREATE TABLE user_kb_access (
            user_id TEXT NOT NULL,
            knowledge_base_id TEXT NOT NULL,
            PRIMARY KEY (user_id, knowledge_base_id)
        );

        CREATE TABLE user_permissions (
            user_id TEXT PRIMARY KEY,
            tab_names TEXT NOT NULL DEFAULT '[]',
            kb_ids TEXT NOT NULL DEFAULT '[]'
        );

        INSERT INTO users (
            user_id, username, password_hash, is_active, is_admin, created_at, updated_at
        ) VALUES (
            'legacy-user-1', 'legacy_permission_user', 'pbkdf2_sha256$1$abc$hash', 1, 0, '2026-05-14 00:00:00', '2026-05-14 00:00:00'
        );

        INSERT INTO user_permissions (user_id, tab_names, kb_ids)
        VALUES (
            'legacy-user-1',
            '["文档管理", "知识库检索"]',
            '["default", "kb_demo"]'
        );
        """
    )
    connection.commit()
    connection.close()

    initialize_database(database_path)

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    auth_service = AuthService(connection)
    permissions = auth_service.get_user_permissions("legacy-user-1")
    columns = [
        row["name"]
        for row in connection.execute("PRAGMA table_info(user_permissions)").fetchall()
    ]
    marker_row = connection.execute(
        "SELECT user_id, permissions_json FROM user_permissions WHERE user_id = ?",
        ("legacy-user-1",),
    ).fetchone()
    connection.close()

    assert "permissions_json" in columns
    assert "updated_at" in columns
    assert "tab_names" not in columns
    assert permissions is not None
    assert set(permissions.tab_names) == {"知识库管理", "知识库检索"}
    assert set(permissions.kb_ids) == {"default", "kb_demo"}
    assert marker_row is not None
    assert marker_row["permissions_json"] == "{}"


def test_get_user_permissions_should_not_fallback_to_full_access_without_marker(tmp_path: Path) -> None:
    """普通旧用户缺少权限标记时，也不应被回退成全菜单和全知识库。"""

    connection, auth_service = create_auth_service(tmp_path / "app.db")
    connection.execute(
        """
        INSERT INTO users (user_id, username, password_hash, is_active, is_admin, created_at, updated_at)
        VALUES (?, ?, ?, 1, 0, '2026-05-14 00:00:00', '2026-05-14 00:00:00')
        """,
        ("legacy-no-marker", "legacy_no_marker", "pbkdf2_sha256$1$abc$hash"),
    )
    connection.commit()

    permissions = auth_service.get_user_permissions("legacy-no-marker")
    connection.close()

    assert permissions is not None
    assert permissions.tab_names == []
    assert permissions.kb_ids == []


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
