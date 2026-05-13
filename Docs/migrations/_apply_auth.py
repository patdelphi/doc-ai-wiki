"""程序说明：在 clean pages.py 上安全添加登录/认证功能。"""
import re

MAIN = "src/ui/pages.py"

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

# 1. 添加 auth_service 参数
content = content.replace(
    "def build_ui(*, ingest_service, retrieval_service, quality_service, review_service, runtime_config",
    "def build_ui(*, ingest_service, retrieval_service, quality_service, review_service, auth_service, runtime_config"
)

# 2. 替换 UI 入口：在 with gr.Blocks 后面加登录页，在 with gr.Tabs 前加 main_content wrapper
old_ui_start = '''    with gr.Blocks(title="中文知识库系统") as demo:
        gr.Markdown("# 中文知识库系统 MVP")

        with gr.Tabs():'''

new_ui_start = '''    with gr.Blocks(title="中文知识库系统") as demo:
        login_state = gr.State({"user_id": None, "username": None, "is_admin": False, "permissions": None})
        with gr.Column(elem_id="auth-page", visible=True) as auth_page:
            with gr.Column(elem_id="auth-center-container"):
                gr.Markdown("# 中文知识库系统")
                auth_login_form = gr.Column(elem_id="auth-login-form", visible=True)
                with auth_login_form:
                    gr.Markdown("### 登录")
                    auth_login_username = gr.Textbox(label="用户名", placeholder="请输入用户名")
                    auth_login_password = gr.Textbox(label="密码", type="password", placeholder="请输入密码")
                    auth_login_result = gr.HTML(elem_id="auth-login-result")
                    with gr.Row():
                        auth_login_submit = ui_button("登录", variant="primary")
                        auth_register_btn = ui_button("注册新用户")
                auth_register_form = gr.Column(elem_id="auth-register-form", visible=False)
                with auth_register_form:
                    gr.Markdown("### 注册新用户")
                    auth_register_username = gr.Textbox(label="用户名", placeholder="请输入用户名")
                    auth_register_password = gr.Textbox(label="密码", type="password", placeholder="请设置密码")
                    auth_register_password_confirm = gr.Textbox(label="重复密码", type="password", placeholder="再次输入密码")
                    auth_register_result = gr.HTML(elem_id="auth-register-result")
                    with gr.Row():
                        auth_register_submit = ui_button("注册", variant="primary")
                        auth_login_btn = ui_button("返回登录")
        with gr.Column(elem_id="main-content", visible=False) as main_content:
            with gr.Row(elem_id="menu-bar"):
                with gr.Column():
                    pass
                with gr.Column(elem_id="user-info-bar"):
                    auth_user_display = gr.Markdown(value="", elem_id="auth-user-display")
                    auth_logout_btn = ui_button("退出登录", variant="danger")
            with gr.Tabs():
                with gr.Tab("AI 质检"):'''

content = content.replace(old_ui_start, new_ui_start)

# Remove the original first tab line that's now duplicated
content = content.replace(
    "            with gr.Tab(\"AI 质检\"):\n            with gr.Tab(\"AI 质检\"):",
    "            with gr.Tab(\"AI 质检\"):"
)

# 3. 在 return demo 前添加认证事件绑定
old_return = "    return demo"
new_return = '''        def _do_login(username, password):
            try:
                user = auth_service.authenticate(username, password)
                if not user:
                    return ({"user_id": None, "username": None}, gr.update(),
                            format_operation_result_html({"success": False, "message": "用户名或密码错误"}, title="登录失败"),
                            gr.update(visible=True), gr.update(visible=False))
                perms = auth_service.get_user_permissions(user.user_id)
                session = {"user_id": user.user_id, "username": user.username, "is_admin": user.is_admin,
                           "permissions": {"tab_names": perms.tab_names, "kb_ids": perms.kb_ids} if perms else {"tab_names": [], "kb_ids": []}}
                return (session, gr.update(value=f"👤 {user.username}"),
                        format_operation_result_html({"success": True, "message": "登录成功"}, title="登录成功"),
                        gr.update(visible=False), gr.update(visible=True))
            except Exception as e:
                return ({"user_id": None, "username": None}, gr.update(),
                        format_operation_result_html({"success": False, "message": str(e)}, title="错误"),
                        gr.update(visible=True), gr.update(visible=False))

        def _do_register(username, password, password_confirm):
            if password != password_confirm:
                return format_operation_result_html({"success": False, "message": "两次密码不一致"}, title="注册失败")
            success, msg = auth_service.register_user(username, password)
            return format_operation_result_html({"success": success, "message": msg}, title="注册成功" if success else "注册失败")

        def _do_logout():
            return {"user_id": None, "username": None, "is_admin": False, "permissions": None}

        auth_register_btn.click(fn=lambda: (gr.update(visible=False), gr.update(visible=True)), outputs=[auth_login_form, auth_register_form])
        auth_login_btn.click(fn=lambda: (gr.update(visible=True), gr.update(visible=False)), outputs=[auth_login_form, auth_register_form])
        auth_login_submit.click(fn=_do_login, inputs=[auth_login_username, auth_login_password],
                                outputs=[login_state, auth_user_display, auth_login_result, auth_page, main_content])
        auth_register_submit.click(fn=_do_register,
                                   inputs=[auth_register_username, auth_register_password, auth_register_password_confirm],
                                   outputs=[auth_register_result])
        auth_logout_btn.click(fn=_do_logout, outputs=[login_state])
        auth_logout_btn.click(fn=lambda: (gr.update(visible=True), gr.update(visible=False), gr.update(visible=True), gr.update(visible=False)),
                              outputs=[auth_page, main_content, auth_login_form, auth_register_form])

    return demo'''

content = content.replace(old_return, new_return)

with open(MAIN, "w", encoding="utf-8") as f:
    f.write(content)

print(f"Updated: {MAIN} ({len(content.splitlines())} lines)")

import py_compile
try:
    py_compile.compile(MAIN, doraise=True)
    print("OK: compile passed")
except py_compile.PyCompileError as e:
    print(f"FAIL: {e}")
    m = re.search(r'line (\d+)', str(e))
    if m:
        el = int(m.group(1))
        with open(MAIN, "r", encoding="utf-8") as f:
            ml = f.readlines()
        for i in range(max(0, el-3), min(len(ml), el+3)):
            print(f"{'>>>' if i==el-1 else '   '} {i+1}: {ml[i].rstrip()[:80]}")
