import asyncio
from pathlib import Path
import docker
from docker.errors import ContainerError, DockerException
from app.config import Settings


class SandboxRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = docker.from_env()

    def _run_syntax_check_sync(self, workspace: Path) -> tuple[bool, str]:
        # Compile all .py files inside the workspace using an isolated container
        cmd = [
            "-B",
            "-c",
            (
                "import pathlib, py_compile, sys; "
                "files = sorted(str(p) for p in pathlib.Path('/workspace').rglob('*.py')); "
                "errs = []; "
                "[errs.append(f'{f}: failed') for f in files if not py_compile.compile(f, doraise=False)]; "
                "print(f'Checked {len(files)} Python file(s).'); "
                "sys.exit(1 if errs else 0)"
            ),
        ]
        try:
            output = self.client.containers.run(
                image=self.settings.sandbox_image,
                command=cmd,
                volumes={str(workspace.resolve()): {"bind": "/workspace", "mode": "ro"}},
                working_dir="/workspace",
                user="1000:1000",
                network_mode="none",
                read_only=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                mem_limit=self.settings.sandbox_memory,
                nano_cpus=int(self.settings.sandbox_cpus * 1_000_000_000),
                pids_limit=self.settings.sandbox_pids_limit,
                remove=True,
                stdout=True,
                stderr=True,
            )
            text = output.decode("utf-8", errors="replace") if isinstance(output, bytes) else str(output)
            return True, text.strip()
        except ContainerError as exc:
            stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else str(exc)
            return False, stderr.strip()
        except DockerException as exc:
            return False, f"Docker sandbox error: {exc}"

    async def run_python_checks(self, workspace: Path) -> tuple[bool, str]:
        return await asyncio.to_thread(self._run_syntax_check_sync, workspace)
