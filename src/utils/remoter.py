"""SSH/rsync deployment + remote-run support for the Gravedancer TUI.

Pure standard library — no paramiko, no fabric. Uses the system OpenSSH and
rsync binaries, which are present on both macOS and Ubuntu. Key-based auth is
assumed (optionally via ``~/.ssh/config``); ``BatchMode=yes`` makes failures
fail fast instead of prompting.

A "remote target" is an Ubuntu box running the same project. Deployment:

    1. ``mkdir -p <proj_dir>`` on the host
    2. ``rsync`` the project (excluding venv/log/episodes/Images/.models/.git)
    3. create a ``venv`` if missing (stdlib-only, so no MLX install needed —
       remote runs use HTTP harnesses like Ollama, never in-process MLX)

A remote run executes ``run_creative_pipeline.py`` over SSH with the remote
process attached as a local ``Popen`` so the TUI can stream its output and
kill it (both locally via the ssh client, and remotely via ``pkill``).

NOTE: every remote command is passed to OpenSSH as a *single* argv element,
because sshd re-parses the joined argv through the remote shell. Anything that
needs to survive that re-split (spaces, quotes, ``$(...)``, ``;``, and-mp
redirects) must arrive inside an already-shell-quoted string. Remote project
dirs should be simple paths (no spaces) since ``~/`` is expanded via ``$HOME``.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SSH_BIN = "ssh"
RSYNC_BIN = "rsync"

DEFAULT_PROJ_DIR = "~/gravedancer"
DEFAULT_INFERENCE_BASE = "http://127.0.0.1:11434"

DEPLOY_EXCLUDES = (
    "venv",
    "log",
    "log.txt",
    "episodes",
    "Images",
    ".models",
    ".git",
    "__pycache__",
    "*.safetensors",
    ".pytest_cache",
    ".streamlit",
    ".venv",
    ".DS_Store",
)


@dataclass
class RemoteTarget:
    """An SSH host that can run the pipeline."""

    host: str
    user: str = ""
    port: int = 22
    proj_dir: str = DEFAULT_PROJ_DIR
    inference_base: str = DEFAULT_INFERENCE_BASE

    def hostspec(self) -> str:
        return f"{self.user}@{self.host}" if self.user else self.host

    def validate(self) -> str | None:
        """Return an error message when fields could be parsed as ssh options."""
        for label, value in (("host", self.host), ("user", self.user)):
            if value.startswith("-"):
                return f"{label} cannot start with '-'"
        return None

    def remote_inference_url(self) -> str:
        root = (self.inference_base or DEFAULT_INFERENCE_BASE).strip().rstrip("/")
        if root.endswith("/v1/chat/completions"):
            return root
        return f"{root}/v1/chat/completions"


def _dir_expr(dirpath: str) -> str:
    """Remote-shell-safe directory expression (``~/x`` -> ``$HOME/x``).

    The result is quoted for use in remote command strings while keeping
    ``$HOME`` expansion intact for ``~``-prefixed paths.
    """
    p = (dirpath or DEFAULT_PROJ_DIR).strip()
    if p == "~":
        return '$HOME'
    if p.startswith("~/"):
        return '"$HOME"' + shlex.quote(p[1:])
    return shlex.quote(p)


def _ssh_cmd(target: RemoteTarget, remote_code: str, connect_timeout: int = 8) -> list[str]:
    """Build ssh argv that runs ``remote_code`` as a single remote command."""
    base = [
        SSH_BIN,
        "-o",
        f"ConnectTimeout={connect_timeout}",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ServerAliveInterval=15",
    ]
    if target.port != 22:
        base += ["-p", str(target.port)]
    # "--" ends option processing so a hostspec beginning with "-" (e.g. a
    # pasted "-oProxyCommand=...") cannot inject additional ssh options.
    return base + ["--", target.hostspec(), remote_code]


def run_ssh(target: RemoteTarget, remote_code: str, timeout: float = 30) -> dict[str, object]:
    """Run a foreground SSH command (single shell string) and return output."""
    cmd = _ssh_cmd(target, remote_code)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {
            "ok": False,
            "code": None,
            "stdout": "",
            "stderr": str(exc),
            "error": str(exc),
            "cmd": " ".join(cmd),
        }
    return {
        "ok": proc.returncode == 0,
        "code": proc.returncode,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
        "error": "" if proc.returncode == 0 else (proc.stderr or proc.stdout or "").strip(),
        "cmd": " ".join(cmd),
    }


def test_connection(target: RemoteTarget) -> dict[str, object]:
    """Reachability probe (fast, BatchMode so it never prompts)."""
    return run_ssh(target, "echo connected", timeout=10)


def remote_info(target: RemoteTarget) -> dict[str, object]:
    """Report python3/venv/ollama/project-dir presence on the host."""
    probe = (
        'echo "__PY__=$(command -v python3 || echo missing)"; '
        f'echo "__VENV__=$(test -x {_dir_expr(target.proj_dir)}/venv/bin/python && echo yes || echo no)"; '
        'echo "__OLLAMA__=$(command -v ollama || echo missing)"; '
        f'echo "__DIR__=$(test -d {_dir_expr(target.proj_dir)} && echo yes || echo no)"'
    )
    result = run_ssh(target, probe, timeout=15)
    info: dict[str, object] = {"host": target.host}
    if not result["ok"]:
        info.update(ok=False, error=result.get("error") or result.get("stderr", ""))
        return info
    info["ok"] = True
    for line in str(result.get("stdout", "")).splitlines():
        key, sep, value = line.partition("=")
        if sep:
            info[key] = value.strip('"')
    return info


def deploy(target: RemoteTarget, timeout: float = 180) -> dict[str, object]:
    """rsync the project and ensure a venv exists on the host."""
    step_results: list[str] = []
    work_dir = _dir_expr(target.proj_dir)

    mkdir = run_ssh(target, f"mkdir -p {work_dir}", timeout=15)
    if not mkdir["ok"]:
        return {"ok": False, "steps": [f"mkdir ✗ {mkdir.get('error')}"], "error": mkdir.get("error")}
    step_results.append("mkdir ✓")

    rsync_cmd = [RSYNC_BIN, "-az"]
    for exclude in DEPLOY_EXCLUDES:
        rsync_cmd += ["--exclude", exclude]
    if target.port != 22:
        rsync_cmd += ["-e", f"ssh -p {target.port}"]
    rsync_cmd += [str(PROJECT_ROOT) + "/", f"{target.hostspec()}:{target.proj_dir}/"]
    try:
        proc = subprocess.run(rsync_cmd, capture_output=True, text=True, timeout=timeout)
        rsync_ok = proc.returncode == 0
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"ok": False, "steps": step_results, "error": str(exc)}
    if not rsync_ok:
        step_results.append("rsync ✗")
        return {"ok": False, "steps": step_results, "error": (proc.stderr or "")[-300:]}
    step_results.append("rsync ✓")

    venv_code = (
        f"cd {work_dir} && "
        "(test -x venv/bin/python || python3 -m venv venv) && "
        "venv/bin/python -c 'import sys; print(sys.version_info[:2])'"
    )
    venv = run_ssh(target, venv_code, timeout=120)
    step_results.append("venv " + ("✓" if venv["ok"] else f"✗ {venv.get('error')}"))
    if not venv["ok"]:
        return {"ok": False, "steps": step_results, "error": venv.get("error")}

    return {"ok": True, "steps": step_results, "error": "", "info": remote_info(target)}


def remote_models(target: RemoteTarget, timeout: float = 20) -> list[str]:
    """List model ids served by the remote inference server via ssh curl."""
    url = target.remote_inference_url().replace("/v1/chat/completions", "/v1/models")
    result = run_ssh(target, f"curl -s -m 8 {shlex.quote(url)} || true", timeout=timeout)
    ids: list[str] = []
    stdout = str(result.get("stdout", ""))
    if stdout:
        try:
            payload = json.loads(stdout)
            for item in payload.get("data", []):
                if isinstance(item, dict) and item.get("id"):
                    ids.append(str(item["id"]))
        except json.JSONDecodeError:
            pass
    return sorted(set(ids))


def remote_run_command(
    target: RemoteTarget,
    extra_env: dict[str, str],
    seed: str,
    run_token: str = "",
) -> list[str]:
    """Build the ssh argv that runs the pipeline on the host."""
    env = {"GRAVEDANCER_LMSTUDIO_URL": target.remote_inference_url()}
    env.update(extra_env)
    env_prefix = " ".join(f"{shlex.quote(k)}={shlex.quote(v)}" for k, v in env.items())
    token_args = f" --run-token {shlex.quote(run_token)}" if run_token else ""
    work = (
        f"cd {_dir_expr(target.proj_dir)} && "
        f"{env_prefix} venv/bin/python -u run_creative_pipeline.py "
        f"--seed {int(seed)} --model {shlex.quote(extra_env['MODEL_REF'])}{token_args}"
    )
    return _ssh_cmd(target, work, connect_timeout=10)


def start_remote(
    target: RemoteTarget,
    extra_env: dict[str, str],
    seed: str,
    run_token: str = "",
) -> subprocess.Popen:
    """Start a remote pipeline run; returns a Popen attached to the ssh client."""
    return subprocess.Popen(
        remote_run_command(target, extra_env, seed, run_token=run_token),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )


def _pkill_pattern(marker: str) -> str:
    """Regex matching *marker* without matching the invoking shell's own cmdline."""
    escaped = re.escape(marker)
    return f"[{escaped[0]}]{escaped[1:]}" if escaped else marker


def remote_pkill(target: RemoteTarget, marker: str, timeout: float = 15) -> None:
    """Best-effort kill of a marker-named process on the host."""
    run_ssh(target, f"pkill -f {shlex.quote(_pkill_pattern(marker))} || true", timeout=timeout)