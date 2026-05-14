"""程序说明：用户认证与权限管理服务（适配现有数据库结构）。"""

import hmac
import hashlib
import os
import time
from dataclasses import dataclass, field

AUTH_TAB_NAMES = [
    "AI 质检",
    "人工审核",
    "知识库管理",
    "知识库检索",
    "功能设置",
]

LEGACY_TAB_NAME_MAP = {
    "文档管理": "知识库管理",
    "文档检索": "知识库检索",
}


def normalize_auth_tab_name(tab_name: str) -> str:
    """兼容历史权限表中的旧页签名称。"""

    normalized = str(tab_name or "").strip()
    return LEGACY_TAB_NAME_MAP.get(normalized, normalized)


@dataclass
class User:
    """用户实体。"""
    user_id: str
    username: str
    password_hash: str
    is_admin: bool
    created_at: str


@dataclass
class UserPermission:
    """用户权限。"""
    user_id: str
    tab_names: list[str] = field(default_factory=list)
    kb_ids: list[str] = field(default_factory=list)


class AuthService:
    """用户认证与权限管理服务。

    适配现有数据库结构：
    - users 表：user_id (TEXT UUID), password_hash (PBKDF2/bcrypt/SHA256), is_admin (INTEGER)
    - user_tab_access 表：user_id (TEXT), tab_name (TEXT)
    - user_kb_access 表：user_id (TEXT), knowledge_base_id (TEXT)
    """

    PASSWORD_SCHEME = "pbkdf2_sha256"
    PASSWORD_ITERATIONS = 390000
    PASSWORD_MAX_LENGTH = 20

    def __init__(self, db):
        self._db = db

    def _hash_password(self, password: str) -> str:
        """使用带盐 PBKDF2-SHA256 生成新密码哈希。"""

        salt = os.urandom(16).hex()
        password_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            self.PASSWORD_ITERATIONS,
        ).hex()
        return f"{self.PASSWORD_SCHEME}${self.PASSWORD_ITERATIONS}${salt}${password_hash}"

    def _hash_legacy_password(self, password: str) -> str:
        """兼容旧库中的 SHA256 密码格式。"""

        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def _verify_password(self, stored_hash: str, password: str) -> bool:
        if stored_hash.startswith("$2b$"):
            try:
                import bcrypt
                return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
            except ImportError:
                return self._hash_legacy_password(password) == stored_hash
        if stored_hash.startswith(f"{self.PASSWORD_SCHEME}$"):
            _, iterations, salt, password_hash = stored_hash.split("$", 3)
            candidate_hash = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt.encode("utf-8"),
                int(iterations),
            ).hex()
            return hmac.compare_digest(candidate_hash, password_hash)
        return self._hash_legacy_password(password) == stored_hash

    def authenticate(self, username: str, password: str) -> User | None:
        """验证用户名和密码，返回用户对象或 None。"""
        row = self._db.execute(
            "SELECT user_id, username, password_hash, is_active, is_admin, created_at FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        if not row:
            return None
        if not bool(row[3]):
            return None
        if not self._verify_password(row[2], password):
            return None
        return User(
            user_id=row[0],
            username=row[1],
            password_hash=row[2],
            is_admin=bool(row[4]),
            created_at=row[5],
        )

    def get_user_by_id(self, user_id: str) -> User | None:
        """按用户 ID 获取用户对象。"""
        row = self._db.execute(
            "SELECT user_id, username, password_hash, is_admin, created_at FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        return User(
            user_id=row[0],
            username=row[1],
            password_hash=row[2],
            is_admin=bool(row[3]),
            created_at=row[4],
        )

    def register_user(self, username: str, password: str) -> tuple[bool, str]:
        """注册新用户，返回 (成功, 消息)。"""
        if not username or not username.strip():
            return False, "用户名不能为空"
        if not password:
            return False, "密码不能为空"
        if len(password) > self.PASSWORD_MAX_LENGTH:
            return False, f"密码长度不能超过{self.PASSWORD_MAX_LENGTH}个字符"

        existing = self._db.execute("SELECT COUNT(*) FROM users WHERE username = ?", (username.strip(),)).fetchone()[0]
        if existing > 0:
            return False, "用户名已存在"

        import uuid
        user_id = str(uuid.uuid4())
        password_hash = self._hash_password(password)
        created_at = time.strftime("%Y-%m-%d %H:%M:%S")

        try:
            self._db.execute(
                "INSERT INTO users (user_id, username, password_hash, is_active, is_admin, created_at, updated_at) VALUES (?, ?, ?, 1, 0, ?, ?)",
                (user_id, username.strip(), password_hash, created_at, created_at)
            )
            self._upsert_permission_marker(user_id)
            self._db.commit()
            return True, "注册成功"
        except Exception as e:
            self._db.rollback()
            return False, f"注册失败: {e}"

    def change_password(self, user_id: str, new_password: str) -> tuple[bool, str]:
        """修改用户密码。"""
        if not new_password:
            return False, "密码不能为空"
        if len(new_password) > self.PASSWORD_MAX_LENGTH:
            return False, f"密码长度不能超过{self.PASSWORD_MAX_LENGTH}个字符"
        password_hash = self._hash_password(new_password)
        updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self._db.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE user_id = ?",
            (password_hash, updated_at, user_id)
        )
        self._db.commit()
        return True, "密码修改成功"

    def list_users(self) -> list[dict]:
        """列出所有用户。"""
        rows = self._db.execute(
            "SELECT user_id, username, is_admin, created_at FROM users ORDER BY user_id"
        ).fetchall()
        return [
            {
                "user_id": r[0],
                "username": r[1],
                "is_admin": bool(r[2]),
                "created_at": r[3],
            }
            for r in rows
        ]

    def delete_user(self, user_id: str) -> tuple[bool, str]:
        """删除用户（不能删除 admin）。"""
        user = self._db.execute("SELECT username, is_admin FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not user:
            return False, "用户不存在"
        if user[1] == 1:
            return False, "不能删除 admin 用户"
        self._db.execute("DELETE FROM user_tab_access WHERE user_id = ?", (user_id,))
        self._db.execute("DELETE FROM user_kb_access WHERE user_id = ?", (user_id,))
        self._db.execute("DELETE FROM user_permissions WHERE user_id = ?", (user_id,))
        self._db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        self._db.commit()
        return True, "用户已删除"

    def get_user_permissions(self, user_id: str) -> UserPermission | None:
        """获取用户权限。"""
        user = self._db.execute("SELECT user_id, is_admin FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not user:
            return None
        if bool(user[1]):
            return UserPermission(
                user_id=user_id,
                tab_names=list(AUTH_TAB_NAMES),
                kb_ids=self._list_knowledge_base_ids(),
            )
        tab_rows = self._db.execute(
            "SELECT tab_name FROM user_tab_access WHERE user_id = ?",
            (user_id,)
        ).fetchall()
        kb_rows = self._db.execute(
            "SELECT knowledge_base_id FROM user_kb_access WHERE user_id = ?",
            (user_id,)
        ).fetchall()
        marker_row = self._db.execute(
            "SELECT 1 FROM user_permissions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        tab_names = [normalize_auth_tab_name(r[0]) for r in tab_rows]
        kb_ids = [r[0] for r in kb_rows]
        if not tab_names and not marker_row:
            tab_names = list(AUTH_TAB_NAMES)
        if not kb_ids and not marker_row:
            kb_ids = self._list_knowledge_base_ids()
        return UserPermission(
            user_id=user_id,
            tab_names=tab_names,
            kb_ids=kb_ids,
        )

    def update_user_permissions(self, user_id: str, tab_names: list[str], kb_ids: list[str]) -> tuple[bool, str]:
        """更新用户权限。"""
        user = self._db.execute("SELECT username FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not user:
            return False, "用户不存在"
        try:
            self._db.execute("DELETE FROM user_tab_access WHERE user_id = ?", (user_id,))
            for tab in tab_names:
                self._db.execute(
                    "INSERT INTO user_tab_access (user_id, tab_name) VALUES (?, ?)",
                    (user_id, normalize_auth_tab_name(tab))
                )
            self._db.execute("DELETE FROM user_kb_access WHERE user_id = ?", (user_id,))
            for kb in kb_ids:
                self._db.execute(
                    "INSERT INTO user_kb_access (user_id, knowledge_base_id) VALUES (?, ?)",
                    (user_id, kb)
                )
            self._upsert_permission_marker(user_id)
            self._db.commit()
            return True, "权限已更新"
        except Exception as e:
            self._db.rollback()
            return False, f"权限更新失败: {e}"

    def _list_knowledge_base_ids(self) -> list[str]:
        """读取当前所有知识库 ID。"""

        rows = self._db.execute("SELECT knowledge_base_id FROM knowledge_bases ORDER BY knowledge_base_id").fetchall()
        return [str(row[0]) for row in rows]

    def _upsert_permission_marker(self, user_id: str) -> None:
        """标记用户权限已显式初始化，避免旧数据回退逻辑误判。"""

        updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self._db.execute(
            """
            INSERT INTO user_permissions (user_id, permissions_json, updated_at)
            VALUES (?, '{}', ?)
            ON CONFLICT(user_id) DO UPDATE SET
                permissions_json = excluded.permissions_json,
                updated_at = excluded.updated_at
            """,
            (user_id, updated_at),
        )
