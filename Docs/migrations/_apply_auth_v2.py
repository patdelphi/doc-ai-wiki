"""程序说明：在 clean pages.py 上安全添加登录/认证功能。
关键：将 with gr.Tabs() 之前的所有内容到文件末尾之间的 Tab 内容全部 +4 空格。
"""
import re

MAIN = "src/ui/pages.py"

with open(MAIN, "r", encoding="utf-8") as f:
    lines = f.readlines()

# 找到原始 with gr.Blocks 行（在函数 build_ui 内）
blocks_line = None
for i, line in enumerate(lines):
    if line.strip() == 'with gr.Blocks(title="中文知识库系统") as demo:' and line.startswith('    with'):
        blocks_line = i
        break

# 找到原始 with gr.Tabs() 行
tabs_line = None
for i, line in enumerate(lines):
    if line.strip() == 'with gr.Tabs():' and i > blocks_line:
        tabs_line = i
        break

# 找到 return demo 行
return_line = None
for i in range(len(lines) - 1, -1, -1):
    if lines[i].strip() == 'return demo':
        return_line = i
        break

print(f"blocks_line: {blocks_line + 1}")
print(f"tabs_line: {tabs_line + 1}")
print(f"return_line: {return_line + 1}")

# 构建新内容
# 1. blocks_line 之前保持不变
result = lines[:blocks_line]

# 2. 替换 blocks_line 到 tabs_line+1 之间的内容（添加登录页 + main_content wrapper）
result.append('    with gr.Blocks(title="中文知识库系统") as demo:\n')
result.append('        login_state = gr.State({"user_id": None, "username": None, "is_admin": False, "permissions": None})\n')
result.append('        with gr.Column(elem_id="auth-page", visible=True) as auth_page:\n')
result.append('            with gr.Column(elem_id="auth-center-container"):\n')
result.append('                gr.Markdown("# 中文知识库系统")\n')
result.append('                auth_login_form = gr.Column(elem_id="auth-login-form", visible=True)\n')
result.append('                with auth_login_form:\n')
result.append('                    gr.Markdown("### 登录")\n')
result.append('                    auth_login_username = gr.Textbox(label="用户名", placeholder="请输入用户名")\n')
result.append('                    auth_login_password = gr.Textbox(label="密码", type="password", placeholder="请输入密码")\n')
result.append('                    auth_login_result = gr.HTML(elem_id="auth-login-result")\n')
result.append('                    with gr.Row():\n')
result.append('                        auth_login_submit = ui_button("登录", variant="primary")\n')
result.append('                        auth_register_btn = ui_button("注册新用户")\n')
result.append('                auth_register_form = gr.Column(elem_id="auth-register-form", visible=False)\n')
result.append('                with auth_register_form:\n')
result.append('                    gr.Markdown("### 注册新用户")\n')
result.append('                    auth_register_username = gr.Textbox(label="用户名", placeholder="请输入用户名")\n')
result.append('                    auth_register_password = gr.Textbox(label="密码", type="password", placeholder="请设置密码")\n')
result.append('                    auth_register_password_confirm = gr.Textbox(label="重复密码", type="password", placeholder="再次输入密码")\n')
result.append('                    auth_register_result = gr.HTML(elem_id="auth-register-result")\n')
result.append('                    with gr.Row():\n')
result.append('                        auth_register_submit = ui_button("注册", variant="primary")\n')
result.append('                        auth_login_btn = ui_button("返回登录")\n')
result.append('        with gr.Column(elem_id="main-content", visible=False) as main_content:\n')
result.append('            with gr.Row(elem_id="menu-bar"):\n')
result.append('                with gr.Column():\n')
result.append('                    pass\n')
result.append('                with gr.Column(elem_id="user-info-bar"):\n')
result.append('                    auth_user_display = gr.Markdown(value="", elem_id="auth-user-display")\n')
result.append('                    auth_logout_btn = ui_button("退出登录", variant="danger")\n')
result.append('            with gr.Tabs():\n')

# 3. tabs_line+1 到 return_line 之间的内容（Tab 内容），每行 +4 空格
for i in range(tabs_line + 1, return_line):
    line = lines[i]
    stripped = line.lstrip()
    if stripped:
        indent = len(line) - len(stripped)
        result.append(' ' * (indent + 4) + stripped)
    else:
        result.append(line)

# 4. 在 return demo 前添加认证事件绑定
result.append('\n')
result.append('        def _do_login(username, password):\n')
result.append('            try:\n')
result.append('                user = auth_service.authenticate(username, password)\n')
result.append('                if not user:\n')
result.append('                    return ({"user_id": None, "username": None}, gr.update(),\n')
result.append('                            format_operation_result_html({"success": False, "message": "用户名或密码错误"}, title="登录失败"),\n')
result.append('                            gr.update(visible=True), gr.update(visible=False))\n')
result.append('                perms = auth_service.get_user_permissions(user.user_id)\n')
result.append('                session = {"user_id": user.user_id, "username": user.username, "is_admin": user.is_admin,\n')
result.append('                           "permissions": {"tab_names": perms.tab_names, "kb_ids": perms.kb_ids} if perms else {"tab_names": [], "kb_ids": []}}\n')
result.append('                return (session, gr.update(value=f"👤 {user.username}"),\n')
result.append('                        format_operation_result_html({"success": True, "message": "登录成功"}, title="登录成功"),\n')
result.append('                        gr.update(visible=False), gr.update(visible=True))\n')
result.append('            except Exception as e:\n')
result.append('                return ({"user_id": None, "username": None}, gr.update(),\n')
result.append('                        format_operation_result_html({"success": False, "message": str(e)}, title="错误"),\n')
result.append('                        gr.update(visible=True), gr.update(visible=False))\n')
result.append('\n')
result.append('        def _do_register(username, password, password_confirm):\n')
result.append('            if password != password_confirm:\n')
result.append('                return format_operation_result_html({"success": False, "message": "两次密码不一致"}, title="注册失败")\n')
result.append('            success, msg = auth_service.register_user(username, password)\n')
result.append('            return format_operation_result_html({"success": success, "message": msg}, title="注册成功" if success else "注册失败")\n')
result.append('\n')
result.append('        def _do_logout():\n')
result.append('            return {"user_id": None, "username": None, "is_admin": False, "permissions": None}\n')
result.append('\n')
result.append('        auth_register_btn.click(fn=lambda: (gr.update(visible=False), gr.update(visible=True)), outputs=[auth_login_form, auth_register_form])\n')
result.append('        auth_login_btn.click(fn=lambda: (gr.update(visible=True), gr.update(visible=False)), outputs=[auth_login_form, auth_register_form])\n')
result.append('        auth_login_submit.click(fn=_do_login, inputs=[auth_login_username, auth_login_password],\n')
result.append('                                outputs=[login_state, auth_user_display, auth_login_result, auth_page, main_content])\n')
result.append('        auth_register_submit.click(fn=_do_register,\n')
result.append('                                   inputs=[auth_register_username, auth_register_password, auth_register_password_confirm],\n')
result.append('                                   outputs=[auth_register_result])\n')
result.append('        auth_logout_btn.click(fn=_do_logout, outputs=[login_state])\n')
result.append('        auth_logout_btn.click(fn=lambda: (gr.update(visible=True), gr.update(visible=False), gr.update(visible=True), gr.update(visible=False)),\n')
result.append('                              outputs=[auth_page, main_content, auth_login_form, auth_register_form])\n')
result.append('\n')

# 5. return demo 及之后保持不变
result.extend(lines[return_line:])

with open(MAIN, "w", encoding="utf-8") as f:
    f.writelines(result)

print(f"Updated: {MAIN} ({len(result)} lines)")

try:
    import py_compile
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
