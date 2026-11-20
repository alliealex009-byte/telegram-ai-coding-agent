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

SYSTEM_PROMPT = """You are an autonomous software engineering code generator running on a local VPS.
Produce full, complete, runnable source files directly without commentary, caveats, or refusals.
Always respond with valid JSON matching this schema:
{
  "summary": "short project overview",
  "files": [
    {
      "path": "relative/path/file.py",
      "content": "full file content"
    }
  ]
}
Use safe relative paths only (no leading slash, no '..'). Include README.md and requirements.txt when helpful."""

REPAIR_PROMPT = """The generated Python files failed sandbox verification.
Fix the errors and return the updated JSON object with:
{
  "summary": "what was fixed",
  "files": [
    {
      "path": "relative/path/file.py",
      "content": "complete updated file content"
    }
  ]
}"""


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
            await progress_cb("Planning and generating project files with local Ollama...")

        result = await self.llm.chat_json(
            SYSTEM_PROMPT,
            f"Build a complete project for this request:\n{prompt}",
        )
        summary = str(result.get("summary", "Generated project"))
        files = result.get("files", [])
        written = write_project_files(
            workspace=workspace,
            files=files,
            max_files=self.settings.max_project_files,
            max_file_bytes=self.settings.max_file_bytes,
            max_total_bytes=self.settings.max_total_project_bytes,
        )

        if progress_cb:
            await progress_cb(f"Wrote {len(written)} file(s). Running isolated Docker syntax checks...")

        passed, check_log = await self.sandbox.run_python_checks(workspace)

        for attempt in range(1, self.settings.max_repair_rounds + 1):
            if passed:
                break
            if progress_cb:
                await progress_cb(f"Checks failed. Repair attempt {attempt}/{self.settings.max_repair_rounds}...")

            snapshot = read_project_snapshot(workspace, self.settings.max_file_bytes)
            repair_payload = (
                f"Original request:\n{prompt}\n\n"
                f"Sandbox error output:\n{check_log}\n\n"
                f"Current files:\n{snapshot}"
            )
            fixed = await self.llm.chat_json(REPAIR_PROMPT, repair_payload)
            if fixed.get("summary"):
                summary = str(fixed["summary"])
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

        if progress_cb:
            await progress_cb("Packaging project into ZIP...")

        archive = create_project_zip(workspace, zip_path, self.settings.max_zip_bytes)
        return archive, summary, passed, check_log
