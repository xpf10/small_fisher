import sys
import subprocess
import shutil
import logging
from typing import List, Optional
from rich.console import Console
from rich.logging import RichHandler

# Set up beautiful console
console = Console(stderr=True)

# Set up logger
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False, markup=True)]
)
logger = logging.getLogger("small_fisher")

from contextvars import ContextVar
from typing import List, Optional, Callable

import os
import signal

import os
import signal
import atexit

# Global dictionaries to track active processes for cancellation/cleanup
ACTIVE_PROCESSES = {} # { pid: process }
JOB_TO_PID = {} # { job_id: pid }

# Thread-safe context-local variables
# The callback accepts: (log_line: str, is_progress: bool)
CURRENT_LOG_CALLBACK: ContextVar[Optional[Callable[[str, bool], None]]] = ContextVar("current_log_callback", default=None)
CURRENT_JOB_ID: ContextVar[Optional[str]] = ContextVar("current_job_id", default=None)

def cancel_job_process(job_id: str):
    """Terminate the active process group for a job."""
    pid = JOB_TO_PID.get(job_id)
    if pid:
        process = ACTIVE_PROCESSES.get(pid)
        if process:
            logger.info(f"Canceling process group {pid} for job {job_id}...")
            try:
                # We ran with start_new_session=True, so process is the session/group leader
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except Exception as e:
                try:
                    process.terminate()
                except Exception:
                    pass

def kill_all_active_processes():
    """Kill all registered active process groups."""
    pids = list(ACTIVE_PROCESSES.keys())
    if pids:
        logger.info(f"Cleaning up {len(pids)} active background processes...")
        for pid in pids:
            process = ACTIVE_PROCESSES.get(pid)
            if process:
                try:
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                except Exception:
                    try:
                        process.terminate()
                    except Exception:
                        pass
        ACTIVE_PROCESSES.clear()
        JOB_TO_PID.clear()

# Register atexit handler to ensure background processes are always cleaned up
atexit.register(kill_all_active_processes)

def get_console() -> Console:
    return console

def run_command(cmd: List[str], description: str, env: Optional[dict] = None) -> bool:
    """
    Run a system command and stream its output.
    Returns True if successful, False otherwise.
    """
    cmd_str = " ".join(cmd)
    logger.info(f"[bold blue]Running {description}:[/bold blue] {cmd_str}")
    
    # Retrieve the active context-local log callback
    callback = CURRENT_LOG_CALLBACK.get()
    if callback:
        callback(f"Running {description}: {cmd_str}", False)
    
    job_id = CURRENT_JOB_ID.get()
    process = None
    try:
        try:
            # Merge stdout and stderr into one stream to read chronologically
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                text=True,
                start_new_session=True
            )
            ACTIVE_PROCESSES[process.pid] = process
            if job_id:
                JOB_TO_PID[job_id] = process.pid
            
            # Read character by character to handle carriage returns (\r) in real-time
            buffer = []
            while True:
                char = process.stdout.read(1)
                if not char:
                    if buffer:
                        line = "".join(buffer)
                        sys.stdout.write(line + "\n")
                        sys.stdout.flush()
                        if callback:
                            callback(line.rstrip("\r\n"), False)
                    break
                
                if char in ("\n", "\r"):
                    line = "".join(buffer)
                    buffer = []
                    sys.stdout.write(line + char)
                    sys.stdout.flush()
                    if callback:
                        callback(line.rstrip("\r\n"), char == "\r")
                else:
                    buffer.append(char)
                    
            process.wait()
        finally:
            if process:
                pid = process.pid
                if pid in ACTIVE_PROCESSES:
                    try:
                        del ACTIVE_PROCESSES[pid]
                    except KeyError:
                        pass
                if job_id and JOB_TO_PID.get(job_id) == pid:
                    try:
                        del JOB_TO_PID[job_id]
                    except KeyError:
                        pass
        
        if process.returncode == 0:
            msg = f"✓ {description} completed successfully."
            logger.info(f"[bold green]{msg}[/bold green]")
            if callback:
                callback(msg, False)
            return True
        else:
            msg = f"✗ {description} failed with exit code {process.returncode}."
            logger.error(f"[bold red]{msg}[/bold red]")
            if callback:
                callback(msg, False)
            return False
            
    except FileNotFoundError:
        msg = f"✗ Executable not found for: {cmd[0]}"
        logger.error(f"[bold red]{msg}[/bold red]")
        if callback:
            callback(msg, False)
        return False
    except Exception as e:
        msg = f"✗ Error running {description}: {str(e)}"
        logger.error(f"[bold red]{msg}[/bold red]")
        if callback:
            callback(msg, False)
        return False

def check_binary(binary_name: str) -> bool:
    """Check if a binary is available on the system PATH."""
    return shutil.which(binary_name) is not None

def get_ascli_config() -> dict:
    """Run ascli conf ascp info and parse standard key paths."""
    import subprocess
    import shutil
    import re
    import sys
    
    config = {}
    
    # Resolve ascli path
    ascli_path = shutil.which("ascli")
    if not ascli_path:
        py_dir = os.path.dirname(sys.executable)
        candidate = os.path.join(py_dir, "ascli")
        if os.path.exists(candidate):
            ascli_path = candidate
            
    if not ascli_path:
        # Check standard micromamba environment locations
        candidates = [
            "/root/micromamba/envs/kingfisher_2/bin/ascli",
            os.path.expanduser("~/.micromamba/envs/kingfisher_2/bin/ascli"),
            "/root/.micromamba/envs/kingfisher_2/bin/ascli",
        ]
        for cand in candidates:
            if os.path.exists(cand):
                ascli_path = cand
                break
            
    if not ascli_path:
        logger.warning(
            "\n[bold yellow]⚠️  Warning: 'ascli' command not found in the current environment.[/bold yellow]\n"
            "[bold yellow]If you are running in the micromamba environment 'kingfisher_2', please ensure 'ascli' is installed,[/bold yellow]\n"
            "[bold yellow]or run this tool in an environment that has 'ascli' installed.[/bold yellow]\n"
        )
        return config
        
    logger.info(f"Querying ascli for Aspera configuration ({ascli_path} conf ascp info)...")
    try:
        res = subprocess.run([ascli_path, "conf", "ascp", "info"], capture_output=True, text=True, check=True)
        # Strip ANSI escape sequences in case output is colorized
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        clean_stdout = ansi_escape.sub('', res.stdout)
        
        for line in clean_stdout.splitlines():
            if "│" in line or "|" in line:
                delimiter = "│" if "│" in line else "|"
                parts = [p.strip() for p in line.split(delimiter)]
                # Remove empty elements resulting from starting/ending delimiters
                parts = [p for p in parts if p]
                if len(parts) >= 2:
                    key = parts[0]
                    value = parts[1]
                    if key in ["ascp", "ssh_private_dsa", "ssh_private_rsa"]:
                        config[key] = value
    except Exception as e:
        logger.warning(f"Could not retrieve ascli configuration: {e}")
        
    return config
