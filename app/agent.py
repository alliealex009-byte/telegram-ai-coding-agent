import asyncio, uuid
from pathlib import Path
from app.config import cfg
from app.llm import LLM
from app.files import parse_obj, write_files, make_zip
from app.sandbox import Sandbox

SYSTEM = '''
You are a professional software engineer and coding agent. Generate complete, coherent, maintainable projects.
Refuse malware, credential theft, ransomware, destructive payloads, stealth/persistence, unauthorized access,
or code intended to compromise systems. Security requests must be defensive and authorized.
Return exactly JSON, no Markdown fences:
{"summary":"brief summary","files":[{"path":"relative/path","content":"complete UTF-8 file content"}]}
Use relative paths only; never parent traversal, absolute paths, secrets, private keys or real credentials.
Include README, dependency manifests, safe defaults, validation and environment-variable configuration.
No placeholders or omitted sections. Do not claim tests passed without evidence.
'''
PLAN = "Plan this project. Describe architecture, components, files, dependencies, security and validation. Do not write code yet."
REPAIR = '''
Repair the project based only on the reported validation errors. Return exactly JSON:
{"files":[{"path":"relative/path","content":"complete replacement file"}],"notes":"brief"}
Only return complete files to add or replace. Do not weaken sandbox security.
'''

class Agent:
    def __init__(self):
        self.llm, self.sandbox = LLM(), Sandbox()
        self.sem = asyncio.Semaphore(cfg.concurrency)

    async def build(self, uid, spec, progress):
        async with self.sem:
            job = uuid.uuid4().hex[:10]
            root = cfg.workspace / str(uid) / job
            root.mkdir(parents=True, exist_ok=False)
            await progress("1/5 · Planning project…")
            plan = await self.llm.chat([{"role":"system","content":SYSTEM},
                                        {"role":"user","content":PLAN+"\\n\\nREQUEST:\\n"+spec}])
            await progress("2/5 · Generating files with Gemma 3 4B…")
            raw = await self.llm.chat([{"role":"system","content":SYSTEM},
                                       {"role":"user","content":"PLAN:\\n"+plan[:8000]+"\\n\\nREQUEST:\\n"+spec}], True)
            obj = parse_obj(raw)
            names = write_files(root, obj)
            result = None
            for n in range(cfg.repairs + 1):
                await progress(f"3/5 · Isolated Docker syntax check ({n+1})…")
                result = await self.sandbox.check(root)
                if result["ok"] or n == cfg.repairs: break
                await progress("4/5 · Gemma is reviewing errors and repairing files…")
                repair_raw = await self.llm.chat([
                    {"role":"system","content":SYSTEM+"\\n"+REPAIR},
                    {"role":"user","content":"REQUEST:\\n"+spec+"\\nERRORS:\\n"+result["logs"]}], True)
                names = sorted(set(names + write_files(root, parse_obj(repair_raw))))
            (root / "BUILD_REPORT.md").write_text(
                f"# Build report\\n\\nModel: `{cfg.model}`\\n\\nFiles: {len(names)}\\n\\n"
                f"Python syntax check: {'PASSED' if result and result['ok'] else 'FAILED / INCOMPLETE'}\\n\\n"
                "This is only a syntax check, not a functional or security audit. Review before deployment.\\n\\n"
                "```text\\n"+(result or {}).get("logs","")[-5000]+"\\n```\\n", encoding="utf-8")
            await progress("5/5 · Packaging ZIP…")
            return {"job":job, "zip":make_zip(root, job), "files":names, "check":result,
                    "summary":str(obj.get("summary","Project generated"))[:600]}
