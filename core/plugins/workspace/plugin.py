"""
AI Workspace Plugin
===================
Gives the AI agent the ability to read/write files and execute
sandboxed shell commands inside a designated workspace directory.

Tools provided:
  workspace_read    - Read a file
  workspace_write   - Write / overwrite a file
  workspace_list    - List directory contents
  workspace_execute - Execute a sandboxed shell command
  workspace_delete  - Delete a file or empty directory
"""

import os
import re
import subprocess
import shlex
from pathlib import Path
from typing import Any, Dict, List

from core.plugin import PluginBase
from core.tools.registry import ToolDefinition, ToolParameter
from core.llm.context.section import PromptSection


class WorkspacePlugin(PluginBase):
    """AI workspace plugin — file I/O + sandboxed shell execution."""

    # ------------------------------------------------------------------
    # Constants
    # ------------------------------------------------------------------

    WORKSPACE_DIR = Path(__file__).parent.parent.parent / "data" / "workspace"
    MAX_FILE_SIZE = 500_000
    MAX_COMMAND_OUTPUT = 50_000
    COMMAND_TIMEOUT = 30

    # 仅保留安全只读 / 无副作用命令；移除 make / git / sed / env 等可导致
    # 任意代码执行或敏感信息泄露的命令。
    _ALLOWED_COMMANDS: frozenset = frozenset({
        "cat", "head", "tail", "wc", "sort", "uniq", "grep",
        "cut", "tr", "diff", "cmp",
        "echo", "printf", "which", "file", "du", "df", "date",
        "cal", "uname", "pwd", "ls",
        "jq", "yq", "tree",
    })

    # 不接受参数路径校验的命令（其参数不是文件路径，无需走沙盒解析）。
    _NON_PATH_COMMANDS: frozenset = frozenset({
        "echo", "printf", "date", "cal", "uname", "pwd", "df", "which",
    })

    # 可经「文件中列出的路径」间接读取任意文件的危险选项：即使选项值本身在
    # 工作区内，其指向的列表文件内容仍可引用工作区外的绝对路径，无法靠路径
    # 校验拦截，故整体拒绝。
    _DANGEROUS_FILE_OPTIONS: frozenset = frozenset({
        "--files0-from",  # sort / wc / du：从文件读取待处理文件名列表
    })

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _activate(self) -> None:
        self.WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    def _deactivate(self) -> None:
        pass

    # ------------------------------------------------------------------
    # ToolProvider
    # ------------------------------------------------------------------

    def get_tool_definitions(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name="workspace_write",
                description="写入文件到 AI 工作区",
                parameters=[
                    ToolParameter("path", "文件路径（相对于工作区根目录）"),
                    ToolParameter("content", "要写入的文件内容"),
                ],
            ),
            ToolDefinition(
                name="workspace_read",
                description="读取工作区中的文件",
                parameters=[
                    ToolParameter("path", "文件路径（相对于工作区根目录）"),
                    ToolParameter("max_lines", "最大读取行数", required=False, default="200"),
                ],
            ),
            ToolDefinition(
                name="workspace_list",
                description="列出工作区目录中的文件和子目录",
                parameters=[
                    ToolParameter("path", "目录路径（相对于工作区根目录，默认 '.'）", required=False, default="."),
                ],
            ),
            ToolDefinition(
                name="workspace_execute",
                description="在工作区中执行沙盒化的 shell 命令",
                parameters=[
                    ToolParameter("command", "要执行的 shell 命令"),
                ],
            ),
            ToolDefinition(
                name="workspace_delete",
                description="删除工作区中的文件或空目录",
                parameters=[
                    ToolParameter("path", "要删除的文件或空目录路径（相对于工作区根目录）"),
                ],
            ),
        ]

    def execute_tool(self, func_name: str, parameters: dict) -> Any:
        method_name = func_name.removeprefix("workspace_")
        method = getattr(self, f"_tool_{method_name}", None)
        if method is None:
            return {"status": "failed", "error": f"未知工具: {func_name}"}
        try:
            return method(parameters)
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    # ------------------------------------------------------------------
    # Path safety
    # ------------------------------------------------------------------

    def _resolve_path(self, user_path: str) -> Path:
        """Resolve *user_path* relative to WORKSPACE_DIR and enforce sandbox.

        Raises ValueError if the resolved absolute path escapes the workspace.
        """
        workspace_root = self.WORKSPACE_DIR.resolve()
        candidate = (workspace_root / user_path).resolve()
        if not str(candidate).startswith(str(workspace_root) + os.sep) and candidate != workspace_root:
            raise ValueError(f"路径逃逸检测: {user_path} -> {candidate}")
        return candidate

    # ----------------------------------------------------------------
    # Tool implementations
    # ----------------------------------------------------------------

    def _tool_write(self, params: dict) -> dict:
        path = self._resolve_path(params["path"])
        content = params["content"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        size = path.stat().st_size
        return {
            "status": "success",
            "file": str(path.relative_to(self.WORKSPACE_DIR)),
            "size": size,
        }

    def _tool_read(self, params: dict) -> dict:
        path = self._resolve_path(params["path"])
        if not path.exists():
            return {"status": "failed", "error": f"文件不存在: {params['path']}"}
        if not path.is_file():
            return {"status": "failed", "error": f"不是文件: {params['path']}"}
        if path.stat().st_size > self.MAX_FILE_SIZE:
            return {"status": "failed", "error": f"文件过大 (max {self.MAX_FILE_SIZE} bytes)"}

        max_lines_raw = params.get("max_lines", "200")
        try:
            max_lines = int(max_lines_raw)
        except (ValueError, TypeError):
            max_lines = 200

        lines = path.read_text(encoding="utf-8").splitlines()
        total_lines = len(lines)
        truncated = total_lines > max_lines
        content = "\n".join(lines[:max_lines])

        return {
            "status": "success",
            "file": str(path.relative_to(self.WORKSPACE_DIR)),
            "content": content,
            "total_lines": total_lines,
            "truncated": truncated,
        }

    def _tool_list(self, params: dict) -> dict:
        user_path = params.get("path", ".")
        path = self._resolve_path(user_path)
        if not path.exists():
            return {"status": "failed", "error": f"路径不存在: {user_path}"}
        if not path.is_dir():
            return {"status": "failed", "error": f"不是目录: {user_path}"}

        entries: list = []
        for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            entry = {
                "name": child.name,
                "type": "dir" if child.is_dir() else "file",
            }
            if child.is_file():
                entry["size"] = child.stat().st_size
            entries.append(entry)

        return {
            "status": "success",
            "path": str(path.relative_to(self.WORKSPACE_DIR)),
            "entries": entries,
            "count": len(entries),
        }

    def _tool_execute(self, params: dict) -> dict:
        command = params["command"]
        if not command.strip():
            return {"status": "failed", "error": "命令为空"}

        # 解析命令并使用白名单校验
        try:
            tokens = shlex.split(command)
        except ValueError as e:
            return {"status": "failed", "error": f"命令解析失败: {e}"}

        if not tokens:
            return {"status": "failed", "error": "命令为空"}
        base_cmd = os.path.basename(tokens[0]).lower()
        if base_cmd not in self._ALLOWED_COMMANDS:
            return {"status": "failed", "error": f"命令不被允许: {base_cmd}"}

        # 校验参数：拒绝绝对路径、包含 ".." 的 token，以及可读取任意文件的危险选项。
        # 注意：选项参数（- 开头）也可能内联文件路径（如 --opt=/etc/passwd、-f/etc/passwd），
        # 不能整体跳过；位置参数与选项内联值统一通过 _resolve_path 限定在工作区内，
        # 防止读取/逃逸到工作区外。
        if base_cmd not in self._NON_PATH_COMMANDS:
            for arg in tokens[1:]:
                opt_name = arg.split("=", 1)[0]
                # 危险文件列表选项：可间接读取任意文件，整体拒绝
                if opt_name in self._DANGEROUS_FILE_OPTIONS:
                    return {"status": "failed", "error": f"选项不被允许: {opt_name}"}
                # grep 的 -f/--file 从文件读取模式 → 可回显任意文件内容
                if base_cmd == "grep" and (
                    opt_name in ("-f", "--file")
                    or (arg.startswith("-f") and not arg.startswith("--") and len(arg) > 2)
                ):
                    return {"status": "failed", "error": f"选项不被允许: {arg}"}

                # 提取需要做路径校验的候选值：位置参数本身，或选项的内联值
                # （--opt=VALUE / 短选项粘连值 -XVALUE）；裸选项名（-n、--color）跳过。
                if arg.startswith("--"):
                    candidate_val = arg.split("=", 1)[1] if "=" in arg else None
                elif arg.startswith("-"):
                    candidate_val = arg[2:] if len(arg) > 2 else None
                else:
                    candidate_val = arg
                if not candidate_val:
                    continue

                if os.path.isabs(candidate_val) or ".." in candidate_val.split(os.sep):
                    return {"status": "failed", "error": f"参数路径不被允许: {arg}"}
                # 统一通过 _resolve_path 限定在工作区内（容忍不存在的目标路径，
                # 非路径参数如普通 grep pattern 会解析到工作区内、不会误报）。
                try:
                    self._resolve_path(candidate_val)
                except ValueError:
                    return {"status": "failed", "error": f"参数路径逃逸: {arg}"}

        # 构造最小化环境，避免向子进程泄露 API key / token 等敏感变量。
        safe_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.WORKSPACE_DIR),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        }

        try:
            proc = subprocess.run(
                tokens,
                shell=False,
                cwd=str(self.WORKSPACE_DIR),
                capture_output=True,
                text=True,
                timeout=self.COMMAND_TIMEOUT,
                env=safe_env,
            )
        except subprocess.TimeoutExpired:
            return {"status": "failed", "error": f"命令超时 ({self.COMMAND_TIMEOUT}s)"}

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        stdout_truncated = len(stdout) > self.MAX_COMMAND_OUTPUT
        stderr_truncated = len(stderr) > self.MAX_COMMAND_OUTPUT
        if stdout_truncated:
            stdout = stdout[:self.MAX_COMMAND_OUTPUT]
        if stderr_truncated:
            stderr = stderr[:self.MAX_COMMAND_OUTPUT]

        return {
            "status": "success" if proc.returncode == 0 else "failed",
            "returncode": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }

    def _tool_delete(self, params: dict) -> dict:
        path = self._resolve_path(params["path"])
        if not path.exists():
            return {"status": "failed", "error": f"路径不存在: {params['path']}"}
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            try:
                path.rmdir()  # empty dirs only
            except OSError as e:
                return {"status": "failed", "error": f"无法删除目录 (可能非空): {e}"}
        else:
            return {"status": "failed", "error": f"未知路径类型: {params['path']}"}
        return {"status": "success", "deleted": str(path.relative_to(self.WORKSPACE_DIR))}

    # ------------------------------------------------------------------
    # PromptSectionProvider
    # ------------------------------------------------------------------

    def get_prompt_sections(self) -> List[tuple]:
        prompt_content = self._build_workspace_prompt()
        section = PromptSection(
            name="workspace_capabilities",
            content=prompt_content,
            cacheable=True,
            order=50,
        )
        return [("chat", section)]

    def _build_workspace_prompt(self) -> str:
        return """
## AI 工作区 (Workspace)

你拥有一个工作区目录 `data/workspace/`，可以通过以下工具进行文件读写和命令执行。

### 可用工具

1. **workspace_write** — 写入文件
   - `path` (必填): 文件路径，相对于工作区根目录
   - `content` (必填): 要写入的文件内容（UTF-8）

2. **workspace_read** — 读取文件
   - `path` (必填): 文件路径，相对于工作区根目录
   - `max_lines` (可选): 最大读取行数，默认 200

3. **workspace_list** — 列出目录
   - `path` (可选): 目录路径，默认 "."（根目录）

4. **workspace_execute** — 执行沙盒命令
   - `command` (必填): 要执行的 shell 命令
   - 限制：30 秒超时，最大输出 50,000 字符，禁止 shell 管道/重定向/通配符，仅允许白名单内的安全只读命令（echo、cat、ls、grep 等），且参数路径同样限定在工作区内

5. **workspace_delete** — 删除文件或空目录
   - `path` (必填): 要删除的路径

### 使用格式

当你需要使用工具时，在 `<act>` 标签中描述你的意图，系统会自动调用对应的工具：

```
<act>使用 workspace_write 写入文件 output.txt，内容为计算结果</act>
<act>使用 workspace_read 读取 data.txt 的前 100 行</act>
<act>使用 workspace_execute 执行 python script.py 并查看输出</act>
<act>使用 workspace_list 列出当前目录的所有文件</act>
<act>使用 workspace_delete 删除 temp.txt</act>
```

### 使用示例

- 保存数据：`<act>workspace_write 写入 report.md</act>`
- 读取日志：`<act>workspace_read 读取 server.log 的最后 50 行</act>`
- 运行脚本：`<act>workspace_execute 执行 node index.js</act>`
- 浏览文件：`<act>workspace_list 列出当前目录</act>`
- 清理文件：`<act>workspace_delete 删除 outdated.txt</act>`

### 注意事项

- 所有路径均为相对路径，自动限定在工作区范围内，无法访问工作区外的文件（命令参数中的路径同样受限，禁止绝对路径与 ".."）
- 命令执行有 30 秒超时限制，且不再支持 shell 管道/重定向/通配符
- 命令需在白名单内（echo、cat、ls、grep 等只读命令），否则会被自动拦截
- 单个文件读取上限 500KB
- 命令输出上限 50,000 字符，超出部分会被截断
- 只允许删除空目录，防止误删
""".strip()
