import ast
import json
from pathlib import Path
import uuid

from app.config import Settings
from app.files import (
    cleanup_stale_workspaces,
    create_project_zip,
    prepare_workspace,
    read_project_snapshot,
    write_project_files,
)
from app.llm import OllamaClient
from app.sandbox import SandboxRunner

PLAN_PROMPT = """You are a principal software architect.
Design a comprehensive, production-grade repository blueprint for the user's request.
To support large, complete codebases (10,000+ lines total across modules), break the system into 25 to 35 well-structured, modular files (handlers, services, models, repositories, middleware, workers, CLI tools, unit/integration tests, Docker/deploy configs, docs).

Respond ONLY with valid JSON:
{
  "project_name": "slug-name",
  "summary": "detailed architectural overview",
  "files": [
    {
      "path": "src/module/file.py",
      "purpose": "detailed responsibilities and public functions/classes"
    }
  ]
}"""

FILE_PROMPT = """You are a senior software engineer writing one complete file of a large multi-file repository.
Rules:
- Write COMPLETE, runnable, production-ready code with full error handling, logging, type hints, and docstrings.
- NEVER use placeholders like 'TODO', 'pass # implement', or truncated logic.
- Match imports and function/class signatures from the Existing Module Interfaces provided.
- Respond ONLY with valid JSON:
{
  "path": "exact/relative/path.py",
  "content": "complete file source code"
}"""

REPAIR_PROMPT = """Fix the failing Python files reported by the sandbox check.
Return ONLY valid JSON with the complete fixed files:
{
  "files": [
    {
      "path": "relative/path/file.py",
      "content": "complete fixed source code"
    }
  ]
}"""


def _extract_signatures(rel_path: str, content: str) -> str:
    """Extract compact class/function signatures so later files import accurate symbols."""
    if not rel_path.endswith(".py"):
        return f"- {rel_path}"
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return f"- {rel_path} (unparsed)"

    symbols: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            symbols.append(f"class {node.name}({', '.join(methods[:8])})")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a.arg for a in node.args.args]
            symbols.append(f"def {node.name}({', '.join(args)})")
    joined = "; ".join(symbols) if symbols else "module constants/config"
    return f"- {rel_path}: {joined}"


class CodingAgent:
    def __init__(self, settings: Settings, llm: OllamaClient, sandbox: SandboxRunner) -> None:
        self.settings = settings
        self.llm = llm
        self.sandbox = sandbox

    async def build_project_zip(
        self,
        user_id: int,
        prompt: str,
        progress_cb=None,
    ) -> tuple[Path, str, bool, str]:
        cleanup_stale_workspaces(self.settings.workspace_root, self.settings.workspace_ttl_hours)
        job_id = uuid.uuid4().hex[:12]
        workspace = prepare_workspace(self.settings.workspace_root, user_id, job_id)
        zip_path = self.settings.workspace_root / f"user_{user_id}" / f"project_{job_id}.zip"

        if progress_cb:
            await progress_cb("Phase 1/3: Designing multi-module architecture blueprint...")

        plan = await self.llm.chat_json(
            PLAN_PROMPT,
            f"Create a full multi-module repository blueprint for:\n{prompt}",
        )
        summary = str(plan.get("summary", "Generated multi-module project"))
        planned_files = plan.get("files", [])[: self.settings.max_project_files]
        if not planned_files:
            raise ValueError("Model returned an empty file blueprint")

        interface_index: list[str] = []
        total_lines = 0
        written_count = 0

        for idx, spec in enumerate(planned_files, start=1):
            rel_path = str(spec.get("path", "")).strip()
            purpose = str(spec.get("purpose", "")).strip()
            if not rel_path:
                continue

            if progress_cb and (idx == 1 or idx % 2 == 0 or idx == len(planned_files)):
                await progress_cb(
                    f"Phase 2/3: Generating file {idx}/{len(planned_files)} "
                    f"({total_lines:,} lines written so far)...\nCurrent: `{rel_path}`"
                )

            recent_interfaces = "\n".join(interface_index[-25:]) or "None yet"
            file_request = (
                f"Project goal:\n{prompt}\n\n"
                f"Architecture summary:\n{summary}\n\n"
                f"Existing module interfaces:\n{recent_interfaces}\n\n"
                f"Target file to write now:\nPath: {rel_path}\nResponsibilities: {purpose}\n\n"
                f"Write the complete, thorough implementation for `{rel_path}`."
            )
            file_obj = await self.llm.chat_json(FILE_PROMPT, file_request)
            content = str(file_obj.get("content", ""))
            if not content.strip():
                continue

            write_project_files(
                workspace=workspace,
                files=[{"path": rel_path, "content": content}],
                max_files=self.settings.max_project_files,
                max_file_bytes=self.settings.max_file_bytes,
                max_total_bytes=self.settings.max_total_project_bytes,
            )
            written_count += 1
            total_lines += len(content.splitlines())
            interface_index.append(_extract_signatures(rel_path, content))

        if progress_cb:
            await progress_cb(
                f"Phase 3/3: Running isolated Docker checks on {written_count} files ({total_lines:,} lines)..."
            )

        passed, check_log = await self.sandbox.run_python_checks(workspace)

        for attempt in range(1, self.settings.max_repair_rounds + 1):
            if passed:
                break
            if progress_cb:
                await progress_cb(f"Repair attempt {attempt}/{self.settings.max_repair_rounds}...")

            snapshot = read_project_snapshot(workspace, self.settings.max_file_bytes)
            # Send only failing files + error log so context stays within num_ctx
            failing_files = {
                k: v for k, v in snapshot.items() if k in check_log or k.endswith("__init__.py")
            } or dict(list(snapshot.items())[:6])

            fixed = await self.llm.chat_json(
                REPAIR_PROMPT,
                f"Sandbox error output:\n{check_log}\n\nFiles to fix:\n{json.dumps(failing_files)}",
            )
            fixed_files = fixed.get("files", [])
            if fixed_files:
                write_project_files(
                    workspace=workspace,
                    files=fixed_files,
                    max_files=self.settings.max_project_files,
                    max_file_bytes=self.settings.max_file_bytes,
                    max_total_bytes=self.settings.max_total_project_bytes,
                )
            passed, check_log = await self.sandbox.run_python_checks(workspace)

        archive = create_project_zip(workspace, zip_path, self.settings.max_zip_bytes)
        final_summary = f"{summary}\nFiles: {written_count} | Total Lines: {total_lines:,}"
        return archive, final_summary, passed, check_log
