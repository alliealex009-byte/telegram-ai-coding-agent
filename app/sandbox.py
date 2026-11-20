import asyncio, docker
from docker.errors import ImageNotFound, DockerException
from app.config import cfg

class Sandbox:
    def __init__(self): self.client = docker.from_env()

    async def check(self, root):
        return await asyncio.to_thread(self._check, root)

    def _check(self, root):
        try: self.client.images.get(cfg.image)
        except ImageNotFound: raise RuntimeError(f"Missing sandbox image {cfg.image}; build it from sandbox/Dockerfile")
        except DockerException as e: raise RuntimeError(f"Docker unavailable: {e}")
        c = None
        try:
            c = self.client.containers.run(
                cfg.image,
                command=["-m", "compileall", "-q", "."],
                detach=True, working_dir="/workspace",
                volumes={str(root.resolve()): {"bind": "/workspace", "mode": "rw"}},
                network_mode="none", read_only=True,
                tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},
                cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
                mem_limit=cfg.memory, nano_cpus=int(cfg.cpus * 1_000_000_000),
                pids_limit=cfg.pids, user="1000:1000"
            )
            result = c.wait(timeout=cfg.job_seconds)
            logs = c.logs().decode("utf-8", "replace")[-10000:]
            return {"ok": result.get("StatusCode") == 0, "exit": result.get("StatusCode"), "logs": logs}
        except Exception:
            if c:
                try: c.kill()
                except Exception: pass
            raise
        finally:
            if c:
                try: c.remove(force=True)
                except Exception: pass
