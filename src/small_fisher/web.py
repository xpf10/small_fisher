import os
import sys
import uuid
import time
import threading
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from small_fisher.utils import (
    logger,
    get_ascli_config,
    CURRENT_LOG_CALLBACK,
    CURRENT_JOB_ID,
    cancel_job_process
)
from small_fisher.downloader import (
    query_metadata,
    download_ena_ascp,
    download_ena_ftp,
    download_prefetch,
    check_already_downloaded
)

app = FastAPI(title="small_fisher UI")

# Global state
JOBS: Dict[str, Dict[str, Any]] = {}
CONFIG = {
    "output_dir": os.path.abspath("."),
    "threads": os.cpu_count() or 4,
    "ascp_bin": None,
    "ascp_key": None,
    "ascp_port": "33001",
    "ascp_options": "-vv -T -k 2",
    "keep_sra": False,
    "retries": 2
}

class ConfigModel(BaseModel):
    output_dir: str
    threads: int
    ascp_bin: Optional[str] = None
    ascp_key: Optional[str] = None
    ascp_port: str
    ascp_options: str
    keep_sra: bool
    retries: int = 2

class NewJobModel(BaseModel):
    accession: str
    methods: List[str]

import re

PCT_PATTERN = re.compile(r'(\d+)%')
SPEED_PATTERN = re.compile(r'(\d+(?:\.\d+)?\s*(?:[KMG]b/s|[KMG]B/s|Kbps|Mbps|Gbps))')

def add_job_log(job_id: str, line: str, is_progress: bool = False):
    """Add a log entry to a job's log list, parsing progress and speed metrics."""
    if job_id not in JOBS:
        return
        
    line_clean = line.strip()
    
    # Parse metrics
    pct_match = PCT_PATTERN.search(line_clean)
    if pct_match:
        JOBS[job_id]["progress"] = int(pct_match.group(1))
        
    speed_match = SPEED_PATTERN.search(line_clean)
    if speed_match:
        JOBS[job_id]["speed"] = speed_match.group(1)
        
    if is_progress:
        JOBS[job_id]["last_progress_line"] = line_clean
        # Throttle progress logs to once every 3 seconds to avoid bloating
        now = time.time()
        last_log = JOBS[job_id].get("_last_progress_log_time", 0.0)
        if now - last_log >= 3.0:
            timestamp = time.strftime("[%X]")
            JOBS[job_id]["logs"].append(f"{timestamp} {line_clean}")
            JOBS[job_id]["_last_progress_log_time"] = now
    else:
        timestamp = time.strftime("[%X]")
        JOBS[job_id]["logs"].append(f"{timestamp} {line_clean}")

def run_job_thread(job_id: str, accession: str, methods: List[str], current_config: Dict[str, Any]):
    """Background thread runner for download jobs."""
    # Set context variables for this thread
    CURRENT_LOG_CALLBACK.set(lambda line, is_progress: add_job_log(job_id, line, is_progress))
    CURRENT_JOB_ID.set(job_id)
    
    JOBS[job_id]["status"] = "running"
    add_job_log(job_id, f"Initializing download for accession: {accession}...")
    add_job_log(job_id, f"Download methods: {', '.join(methods)}")
    
    try:
        # Step 1: Query API
        run_records = query_metadata(accession)
            
        success = True
        for run_record in run_records:
            run_id = run_record["run_accession"]
            add_job_log(job_id, f"--------------------------------------------------")
            add_job_log(job_id, f"Processing Run: {run_id}")
            add_job_log(job_id, f"--------------------------------------------------")
            
            # Check if this run is already downloaded and complete
            if check_already_downloaded(run_id, run_records, current_config["output_dir"], current_config.get("verify", False)):
                add_job_log(job_id, f"Run {run_id} is already fully downloaded. Skipping.")
                continue
                
            retries = current_config.get("retries", 2)
            downloaded = False
            for attempt in range(retries + 1):
                if JOBS[job_id]["status"] == "cancelled":
                    break
                if attempt > 0:
                    add_job_log(job_id, f"↻ Retrying run {run_id} (Attempt {attempt}/{retries})...")
                    time.sleep(min(2 ** attempt, 30))
                    
                for method in methods:
                    if JOBS[job_id]["status"] == "cancelled":
                        break
                        
                    add_job_log(job_id, f"Trying download method: {method}...")
                    
                    if method == "ena-ascp":
                        ascp_bin = current_config.get("ascp_bin")
                        ascp_key = current_config.get("ascp_key")
                        
                        # Auto-detect using ascli if not specified
                        if not ascp_bin or not ascp_key:
                            add_job_log(job_id, "Aspera path or key not specified. Detecting via ascli...")
                            ascli_config = get_ascli_config()
                            if not ascp_bin:
                                ascp_bin = ascli_config.get("ascp") or os.path.expanduser("~/.aspera/sdk/ascp")
                            if not ascp_key:
                                ascp_key = ascli_config.get("ssh_private_rsa") or ascli_config.get("ssh_private_dsa") or os.path.expanduser("~/.aspera/sdk/aspera_bypass_rsa.pem")
                                
                        add_job_log(job_id, f"Resolved Ascp Binary: {ascp_bin}")
                        add_job_log(job_id, f"Resolved Ascp Key:    {ascp_key}")
                        
                        downloaded = download_ena_ascp(
                            run_record=run_record,
                            output_dir=current_config["output_dir"],
                            ascp_bin=ascp_bin,
                            ascp_key=ascp_key,
                            ascp_port=current_config["ascp_port"],
                            ascp_options=[opt for opt in current_config["ascp_options"].split() if opt]
                        )
                    elif method == "prefetch":
                        downloaded = download_prefetch(
                            accession=run_id,
                            output_dir=current_config["output_dir"],
                            threads=current_config["threads"],
                            keep_sra=current_config["keep_sra"]
                        )
                    elif method == "ena-ftp":
                        downloaded = download_ena_ftp(
                            run_record=run_record,
                            output_dir=current_config["output_dir"]
                        )
                        
                    if downloaded:
                        if current_config.get("verify", False):
                            from small_fisher.downloader import verify_file_integrity
                            md5_list = [m.strip() for m in run_record.get("fastq_md5", "").split(";") if m.strip()]
                            files = []
                            if "fastq_ftp" in run_record and run_record["fastq_ftp"]:
                                files = [os.path.basename(u) for u in run_record["fastq_ftp"].split(";") if u.strip()]
                            elif "fastq_aspera" in run_record and run_record["fastq_aspera"]:
                                files = [os.path.basename(u) for u in run_record["fastq_aspera"].split(";") if u.strip()]
                            
                            if md5_list and len(md5_list) == len(files):
                                add_job_log(job_id, f"Verifying MD5 checksums for {run_id}...")
                                is_valid = True
                                for f, expected_md5 in zip(files, md5_list):
                                    filepath = os.path.join(current_config["output_dir"], f)
                                    add_job_log(job_id, f"Verifying {f} against MD5 {expected_md5}...")
                                    if not verify_file_integrity(filepath, expected_md5):
                                        add_job_log(job_id, f"✗ MD5 mismatch for {f}")
                                        is_valid = False
                                        break
                                    else:
                                        add_job_log(job_id, f"✓ MD5 verified for {f}")
                                if not is_valid:
                                    add_job_log(job_id, f"Integrity check failed for method {method}. Proceeding to fallback...")
                                    downloaded = False
                                    
                        if downloaded:
                            add_job_log(job_id, f"✓ Successfully downloaded {run_id} using {method}.")
                            break
                
                if downloaded:
                    break
                    
            if JOBS[job_id]["status"] == "cancelled":
                add_job_log(job_id, "Job cancellation requested by user.")
                success = False
                break
                
            if not downloaded:
                success = False
                add_job_log(job_id, f"✗ Failed to download run {run_id} using all specified methods.")
                break
                
        if JOBS[job_id]["status"] != "cancelled":
            if success:
                JOBS[job_id]["status"] = "completed"
                add_job_log(job_id, "✓ Download and processing completed successfully!")
            else:
                JOBS[job_id]["status"] = "failed"
                add_job_log(job_id, "✗ Download job failed.")
                
    except Exception as e:
        if JOBS[job_id]["status"] != "cancelled":
            JOBS[job_id]["status"] = "failed"
            add_job_log(job_id, f"✗ Critical Error: {str(e)}")
    finally:
        JOBS[job_id]["completed_at"] = time.time()

@app.get("/", response_class=HTMLResponse)
def index():
    dist_index = os.path.join(os.path.dirname(__file__), "dist", "index.html")
    if os.path.exists(dist_index):
        try:
            with open(dist_index, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
        except Exception as e:
            logger.error(f"Error reading React index.html: {e}")
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>small_fisher 🎣 UI Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #060913;
            --card-bg: rgba(13, 20, 38, 0.45);
            --card-border: rgba(255, 255, 255, 0.08);
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #8b5cf6; /* Neon Purple */
            --primary-hover: #7c3aed;
            --accent: #06b6d4; /* Neon Blue */
            --accent-hover: #0891b2;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --glow: rgba(139, 92, 246, 0.25);
            --accent-glow: rgba(6, 182, 212, 0.25);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow-x: hidden;
            background-image: 
                radial-gradient(circle at 5% 5%, rgba(139, 92, 246, 0.12) 0%, transparent 45%),
                radial-gradient(circle at 95% 95%, rgba(6, 182, 212, 0.12) 0%, transparent 45%),
                radial-gradient(circle at 50% 50%, rgba(15, 23, 42, 0.3) 0%, var(--bg-color) 100%);
            background-attachment: fixed;
        }

        header {
            background: rgba(6, 9, 19, 0.7);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border-bottom: 1px solid var(--card-border);
            padding: 1.25rem 2.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 10;
        }

        .logo-area {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .logo-icon {
            font-size: 1.85rem;
            filter: drop-shadow(0 0 10px rgba(6, 182, 212, 0.5));
            animation: float 3.5s ease-in-out infinite;
        }

        @keyframes float {
            0%, 100% { transform: translateY(0) rotate(0deg); }
            50% { transform: translateY(-5px) rotate(5deg); }
        }

        .logo-title {
            font-size: 1.65rem;
            font-weight: 800;
            background: linear-gradient(135deg, #ffffff 10%, #d8b4fe 50%, var(--accent) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.03em;
            text-shadow: 0 0 20px rgba(139, 92, 246, 0.15);
        }

        .status-badge {
            display: flex;
            align-items: center;
            gap: 0.625rem;
            font-size: 0.875rem;
            background: rgba(6, 182, 212, 0.08);
            color: var(--accent);
            padding: 0.5rem 1.15rem;
            border-radius: 9999px;
            border: 1px solid rgba(6, 182, 212, 0.2);
            font-weight: 600;
            box-shadow: 0 0 15px rgba(6, 182, 212, 0.08);
        }

        .pulse-dot {
            width: 8px;
            height: 8px;
            background-color: var(--accent);
            border-radius: 50%;
            animation: pulse 1.8s infinite;
            box-shadow: 0 0 8px var(--accent);
        }

        @keyframes pulse {
            0% { transform: scale(0.85); opacity: 0.5; box-shadow: 0 0 0 0 rgba(6, 182, 212, 0.7); }
            70% { transform: scale(1.2); opacity: 1; box-shadow: 0 0 0 8px rgba(6, 182, 212, 0); }
            100% { transform: scale(0.85); opacity: 0.5; box-shadow: 0 0 0 0 rgba(6, 182, 212, 0); }
        }

        main {
            flex: 1;
            padding: 2.5rem;
            max-width: 1650px;
            width: 100%;
            margin: 0 auto;
            display: grid;
            grid-template-columns: 370px 1fr;
            gap: 2.5rem;
        }

        @media (max-width: 1100px) {
            main {
                grid-template-columns: 1fr;
                padding: 1.5rem;
            }
        }

        .sidebar {
            display: flex;
            flex-direction: column;
            gap: 2rem;
        }

        .card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 20px;
            padding: 1.75rem;
            backdrop-filter: blur(20px) saturate(180%);
            -webkit-backdrop-filter: blur(20px) saturate(180%);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.4);
            transition: border-color 0.3s, box-shadow 0.3s;
            position: relative;
            overflow: hidden;
        }

        .card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: linear-gradient(135deg, rgba(255,255,255,0.02) 0%, transparent 100%);
            pointer-events: none;
        }

        .card:hover {
            border-color: rgba(255, 255, 255, 0.12);
            box-shadow: 0 12px 40px 0 rgba(0, 0, 0, 0.45);
        }

        .card-title {
            font-size: 1.15rem;
            font-weight: 700;
            margin-bottom: 1.5rem;
            color: #fff;
            display: flex;
            justify-content: space-between;
            align-items: center;
            letter-spacing: -0.01em;
        }

        .form-group {
            margin-bottom: 1.25rem;
        }

        .form-group label {
            display: block;
            font-size: 0.825rem;
            font-weight: 600;
            margin-bottom: 0.6rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .form-control {
            width: 100%;
            background: rgba(10, 14, 28, 0.7);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 10px;
            padding: 0.75rem 1rem;
            color: #fff;
            font-family: inherit;
            font-size: 0.9375rem;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .form-control:focus {
            outline: none;
            border-color: var(--accent);
            box-shadow: 0 0 15px rgba(6, 182, 212, 0.2);
            background: rgba(10, 14, 28, 0.85);
        }

        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
        }

        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            width: 100%;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
            color: #fff;
            border: none;
            border-radius: 10px;
            padding: 0.75rem 1.25rem;
            font-size: 0.9375rem;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 4px 15px var(--glow);
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(139, 92, 246, 0.45);
        }

        .btn:active {
            transform: translateY(0);
        }

        .btn-secondary {
            background: rgba(255, 255, 255, 0.05);
            color: #fff;
            border: 1px solid rgba(255, 255, 255, 0.08);
            box-shadow: none;
        }

        .btn-secondary:hover {
            background: rgba(255, 255, 255, 0.1);
            box-shadow: 0 4px 12px rgba(255, 255, 255, 0.05);
            border-color: rgba(255,255,255,0.15);
            transform: translateY(-1px);
        }

        .btn-danger {
            background: linear-gradient(135deg, var(--danger) 0%, #dc2626 100%);
            box-shadow: 0 4px 12px rgba(239, 68, 68, 0.25);
        }

        .btn-danger:hover {
            background: #dc2626;
            box-shadow: 0 6px 16px rgba(239, 68, 68, 0.45);
        }

        .checkbox-group {
            display: flex;
            flex-direction: column;
            gap: 0.65rem;
            margin-top: 0.5rem;
        }

        .checkbox-label {
            display: flex;
            align-items: center;
            gap: 0.65rem;
            font-size: 0.9375rem;
            color: var(--text-main);
            cursor: pointer;
            user-select: none;
        }

        .checkbox-label input {
            cursor: pointer;
            accent-color: var(--primary);
            width: 16px;
            height: 16px;
        }

        .content-area {
            display: flex;
            flex-direction: column;
            gap: 2.5rem;
        }

        .jobs-container {
            display: flex;
            flex-direction: column;
            gap: 1.15rem;
            max-height: 420px;
            overflow-y: auto;
            padding-right: 0.65rem;
        }

        .jobs-container::-webkit-scrollbar {
            width: 6px;
        }

        .jobs-container::-webkit-scrollbar-track {
            background: rgba(255, 255, 255, 0.01);
            border-radius: 3px;
        }

        .jobs-container::-webkit-scrollbar-thumb {
            background-color: rgba(255, 255, 255, 0.1);
            border-radius: 3px;
        }

        .job-item {
            background: rgba(15, 22, 42, 0.35);
            border: 1px solid var(--card-border);
            border-radius: 14px;
            padding: 1.25rem;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            cursor: pointer;
        }

        .job-item:hover {
            border-color: rgba(6, 182, 212, 0.4);
            background: rgba(15, 22, 42, 0.55);
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.25);
        }

        .job-item.active {
            border-color: var(--primary);
            background: rgba(139, 92, 246, 0.08);
            box-shadow: 0 0 20px rgba(139, 92, 246, 0.15);
        }

        .job-info {
            display: flex;
            flex-direction: column;
            gap: 0.35rem;
        }

        .job-accession {
            font-size: 1.075rem;
            font-weight: 700;
            color: #fff;
            letter-spacing: -0.01em;
        }

        .job-meta {
            font-size: 0.825rem;
            color: var(--text-muted);
            display: flex;
            gap: 0.85rem;
            align-items: center;
        }

        .job-status-badge {
            font-size: 0.725rem;
            font-weight: 700;
            padding: 0.2rem 0.6rem;
            border-radius: 9999px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .status-pending { background: rgba(148, 163, 184, 0.12); border: 1px solid rgba(148, 163, 184, 0.2); color: #94a3b8; }
        .status-running { background: rgba(139, 92, 246, 0.15); border: 1px solid rgba(139, 92, 246, 0.3); color: #a78bfa; animation: pulse-running 1.8s infinite; }
        .status-completed { background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.25); color: #34d399; }
        .status-failed { background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.25); color: #f87171; }
        .status-cancelled { background: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.25); color: #fbbf24; }

        @keyframes pulse-running {
            0% { opacity: 0.8; }
            50% { opacity: 1; }
            100% { opacity: 0.8; }
        }

        .progress-bar-container {
            width: 100%;
            background: rgba(255,255,255,0.03);
            height: 8px;
            border-radius: 4px;
            overflow: hidden;
            border: 1px solid rgba(255,255,255,0.04);
            position: relative;
            margin-top: 0.4rem;
            box-shadow: inset 0 1px 3px rgba(0,0,0,0.5);
        }

        .progress-bar-active {
            height: 100%;
            background: linear-gradient(90deg, var(--primary) 0%, var(--accent) 100%);
            border-radius: 4px;
            transition: width 0.3s ease;
            box-shadow: 0 0 10px rgba(6, 182, 212, 0.5);
        }

        .terminal-card {
            display: flex;
            flex-direction: column;
            flex: 1;
            min-height: 440px;
        }

        .terminal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.15rem;
        }

        .terminal-console {
            background-color: rgba(5, 7, 12, 0.85);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
            padding: 1.25rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.875rem;
            line-height: 1.6;
            color: #38bdf8; /* Sleek sky blue color */
            overflow-y: auto;
            flex: 1;
            height: 320px;
            white-space: pre-wrap;
            box-shadow: inset 0 4px 15px rgba(0,0,0,0.6);
            backdrop-filter: blur(5px);
        }

        .terminal-console::-webkit-scrollbar {
            width: 6px;
        }

        .terminal-console::-webkit-scrollbar-thumb {
            background-color: rgba(255, 255, 255, 0.1);
            border-radius: 3px;
        }

        .no-jobs {
            text-align: center;
            padding: 4rem;
            color: var(--text-muted);
            font-size: 0.95rem;
        }

        .notify {
            position: fixed;
            bottom: 2rem;
            right: 2rem;
            background: rgba(13, 20, 38, 0.95);
            border: 1px solid var(--primary);
            color: #fff;
            padding: 1rem 1.5rem;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.6);
            display: none;
            z-index: 100;
            animation: slideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            backdrop-filter: blur(10px);
            font-weight: 500;
        }

        @keyframes slideIn {
            from { transform: translateY(20px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }
    </style>
</head>
<body>

    <header>
        <div class="logo-area">
            <span class="logo-icon">🎣</span>
            <span class="logo-title">small_fisher</span>
        </div>
        <div class="status-badge">
            <span class="pulse-dot"></span>
            Dashboard Connected
        </div>
    </header>

    <main>
        <div class="sidebar">
            <!-- System Status Card -->
            <div class="card">
                <div class="card-title">
                    <span>System Engine</span>
                    <span class="job-status-badge status-running" style="font-size: 0.7rem; text-transform:none;">Active</span>
                </div>
                <div style="display:flex; flex-direction:column; gap:0.85rem;">
                    <div>
                        <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-bottom:0.35rem; color:var(--text-muted);">
                            <span>CPU Parallel Cores</span>
                            <span style="color:var(--accent); font-weight:600;">Max Utilization</span>
                        </div>
                        <div style="width: 100%; background: rgba(255,255,255,0.03); height: 8px; border-radius: 4px; overflow: hidden; border: 1px solid rgba(255,255,255,0.04);">
                            <div style="width: 100%; background: linear-gradient(90deg, var(--primary) 0%, var(--accent) 100%); height: 100%; box-shadow: 0 0 8px rgba(6,182,212,0.3);"></div>
                        </div>
                    </div>
                    <div style="display:flex; justify-content:space-between; font-size:0.8rem; color:var(--text-muted); border-top:1px solid rgba(255,255,255,0.04); padding-top:0.6rem;">
                        <span>Decompression</span>
                        <span style="color:var(--success); font-weight:600;">parallel-fastq-dump 🚀</span>
                    </div>
                    <div style="display:flex; justify-content:space-between; font-size:0.8rem; color:var(--text-muted);">
                        <span>SRA Fallback</span>
                        <span style="color:var(--accent); font-weight:600;">Active</span>
                    </div>
                </div>
            </div>

            <!-- Configuration Card -->
            <div class="card">
                <div class="card-title">
                    <span>Settings</span>
                    <button class="btn btn-secondary" style="width: auto; padding: 0.35rem 0.75rem; font-size: 0.75rem; font-weight:600;" onclick="detectAspera()">Scan via ascli</button>
                </div>
                <div class="form-group">
                    <label for="output_dir">Output Directory</label>
                    <input type="text" id="output_dir" class="form-control">
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label for="threads">Threads</label>
                        <input type="number" id="threads" class="form-control" min="1">
                    </div>
                    <div class="form-group">
                        <label for="ascp_port">Aspera Port</label>
                        <input type="text" id="ascp_port" class="form-control">
                    </div>
                </div>
                <div class="form-group">
                    <label for="ascp_bin">Ascp Binary Path</label>
                    <input type="text" id="ascp_bin" class="form-control" placeholder="Auto-detected if blank">
                </div>
                <div class="form-group">
                    <label for="ascp_key">Ascp Key Path (.pem)</label>
                    <input type="text" id="ascp_key" class="form-control" placeholder="Auto-detected if blank">
                </div>
                <div class="form-group">
                    <label for="ascp_options">Ascp Options</label>
                    <input type="text" id="ascp_options" class="form-control">
                </div>
                <div class="form-group">
                    <label for="retries">Auto-Retries</label>
                    <input type="number" id="retries" class="form-control" min="0" max="10" placeholder="2">
                </div>
                <div class="form-group">
                    <label class="checkbox-label">
                         <input type="checkbox" id="keep_sra"> Keep SRA Files
                    </label>
                    <label class="checkbox-label" style="margin-top: 0.5rem;">
                         <input type="checkbox" id="verify"> Verify MD5 Checksums
                    </label>
                </div>
                <button class="btn" onclick="saveConfig()">Save Settings</button>
            </div>

            <!-- New Download Card -->
            <div class="card">
                <div class="card-title">New Download</div>
                <div class="form-group">
                    <label for="accession">Accession ID(s)</label>
                    <input type="text" id="accession" class="form-control" placeholder="e.g. SRR23641780">
                </div>
                <div class="form-group">
                    <label>Download Methods</label>
                    <div class="checkbox-group">
                        <label class="checkbox-label"><input type="checkbox" id="method_ascp" checked value="ena-ascp"> ENA via Aspera (ena-ascp)</label>
                        <label class="checkbox-label"><input type="checkbox" id="method_prefetch" checked value="prefetch"> SRA prefetch (prefetch)</label>
                        <label class="checkbox-label"><input type="checkbox" id="method_ftp" checked value="ena-ftp"> ENA via FTP (ena-ftp)</label>
                    </div>
                </div>
                <button class="btn" onclick="startDownload()">Start Download</button>
            </div>
        </div>

        <div class="content-area">
            <!-- Jobs List Card -->
            <div class="card">
                <div class="card-title">Download Queue</div>
                <div class="jobs-container" id="jobs_list">
                    <div class="no-jobs">No download jobs submitted yet.</div>
                </div>
            </div>

            <!-- Terminal Card -->
            <div class="card terminal-card">
                <div class="terminal-header" style="display:flex; flex-direction:column; gap:0.75rem; align-items:stretch;">
                    <div style="display:flex; justify-content:space-between; align-items:center; width:100%;">
                        <div class="card-title" id="terminal_title" style="margin-bottom:0; color:#fff; display:flex; align-items:center; gap:0.5rem;">
                            <span style="width:10px; height:10px; border-radius:50%; background:var(--accent); display:inline-block;"></span>
                            Live Console Logs
                        </div>
                        <button class="btn btn-secondary" style="width: auto; padding: 0.35rem 0.75rem; font-size:0.75rem; font-weight:600;" onclick="clearActiveLogs()">Clear View</button>
                    </div>
                    <div id="live_progress_banner" style="font-family:'JetBrains Mono', monospace; font-size:0.875rem; color:var(--accent); min-height:1.25rem; white-space:pre-wrap; border-left: 2px solid var(--accent); padding-left: 0.75rem; display:none;"></div>
                </div>
                <div class="terminal-console" id="terminal_console">Select a job from the queue to view its download progress...</div>
            </div>
        </div>
    </main>

    <div class="notify" id="notification">Settings saved successfully!</div>

    <script>
        let selectedJobId = null;
        let configData = {};
        
        // Fetch configuration
        async function fetchConfig() {
            try {
                const response = await fetch('/api/config');
                configData = await response.json();
                document.getElementById('output_dir').value = configData.output_dir;
                document.getElementById('threads').value = configData.threads;
                document.getElementById('ascp_port').value = configData.ascp_port;
                document.getElementById('ascp_bin').value = configData.ascp_bin || '';
                document.getElementById('ascp_key').value = configData.ascp_key || '';
                document.getElementById('ascp_options').value = configData.ascp_options;
                document.getElementById('keep_sra').checked = configData.keep_sra;
                document.getElementById('verify').checked = configData.verify || false;
                document.getElementById('retries').value = configData.retries !== undefined ? configData.retries : 2;
            } catch (e) {
                showNotification("Error loading configuration", true);
            }
        }

        // Save configuration
        async function saveConfig() {
            const data = {
                output_dir: document.getElementById('output_dir').value,
                threads: parseInt(document.getElementById('threads').value),
                ascp_port: document.getElementById('ascp_port').value,
                ascp_bin: document.getElementById('ascp_bin').value || null,
                ascp_key: document.getElementById('ascp_key').value || null,
                ascp_options: document.getElementById('ascp_options').value,
                keep_sra: document.getElementById('keep_sra').checked,
                verify: document.getElementById('verify').checked,
                retries: parseInt(document.getElementById('retries').value || 0)
            };

            try {
                const response = await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                if (response.ok) {
                    showNotification("Settings saved successfully!");
                    fetchConfig();
                } else {
                    showNotification("Failed to save settings", true);
                }
            } catch (e) {
                showNotification("Connection error", true);
            }
        }

        // Detect Aspera
        async function detectAspera() {
            showNotification("Running ascli conf ascp info...");
            try {
                const response = await fetch('/api/config?detect=true');
                const data = await response.json();
                document.getElementById('ascp_bin').value = data.ascp_bin || '';
                document.getElementById('ascp_key').value = data.ascp_key || '';
                showNotification("Aspera config loaded from system!");
            } catch (e) {
                showNotification("Could not auto-detect configuration", true);
            }
        }

        // Load and update download jobs
        async function fetchJobs() {
            try {
                const response = await fetch('/api/jobs');
                const jobs = await response.json();
                const container = document.getElementById('jobs_list');
                
                if (Object.keys(jobs).length === 0) {
                    container.innerHTML = '<div class="no-jobs">No download jobs submitted yet.</div>';
                    return;
                }

                let html = '';
                const sortedJobs = Object.values(jobs).sort((a, b) => b.created_at - a.created_at);
                
                for (let job of sortedJobs) {
                    const isActive = job.id === selectedJobId ? 'active' : '';
                    let actionButton = '';
                    if (job.status === 'running' || job.status === 'pending') {
                        actionButton = `<button class="btn btn-danger" style="width:auto; padding: 0.35rem 0.75rem; font-size: 0.75rem; font-weight:700;" onclick="event.stopPropagation(); cancelJob('${job.id}')">Cancel</button>`;
                    }
                    
                    html += `
                        <div class="job-item ${isActive}" onclick="selectJob('${job.id}')">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <div class="job-info">
                                    <div class="job-accession">${job.accession}</div>
                                    <div class="job-meta">
                                        <span class="job-status-badge status-${job.status}">${job.status}</span>
                                        <span>Methods: ${job.methods.join(', ')}</span>
                                        ${job.status === 'running' && job.speed ? `<span style="color:var(--accent); font-weight:600;">⚡ ${job.speed} (${job.progress || 0}%)</span>` : ''}
                                    </div>
                                </div>
                                <div>
                                    ${actionButton}
                                </div>
                            </div>
                            ${job.status === 'running' ? `
                            <div class="progress-bar-container">
                                <div class="progress-bar-active" style="width: ${job.progress || 0}%;"></div>
                            </div>
                            ` : ''}
                        </div>
                    `;
                }
                container.innerHTML = html;
                
                if (selectedJobId && jobs[selectedJobId]) {
                    updateConsole(jobs[selectedJobId]);
                }
            } catch (e) {
                // Keep polling quietly
            }
        }

        function selectJob(jobId) {
            selectedJobId = jobId;
            fetchJobs();
        }

        function updateConsole(job) {
            document.getElementById('terminal_title').innerHTML = `<span style="width:10px; height:10px; border-radius:50%; background:var(--accent); display:inline-block; box-shadow:0 0 8px var(--accent);"></span> Console Logs: ${job.accession} (${job.id})`;
            const consoleBox = document.getElementById('terminal_console');
            const progressBanner = document.getElementById('live_progress_banner');
            
            if (job.status === 'running' && job.last_progress_line) {
                progressBanner.innerText = `⏳ Active Progress: ${job.last_progress_line}`;
                progressBanner.style.display = 'block';
            } else {
                progressBanner.style.display = 'none';
            }
            
            if (job.logs.length === 0) {
                consoleBox.innerHTML = '<span style="color:var(--text-muted)">Starting up job. Waiting for logs...</span>';
            } else {
                const previousScrollHeight = consoleBox.scrollHeight;
                const previousScrollTop = consoleBox.scrollTop;
                const previousClientHeight = consoleBox.clientHeight;
                
                // Colorize logs
                const formattedLogs = job.logs.map(line => {
                    let style = '';
                    if (line.includes('✓') || line.includes('completed') || line.includes('SUCCESS')) {
                        style = 'color: #34d399; font-weight: 500;'; // Success green
                    } else if (line.includes('✗') || line.includes('failed') || line.includes('Error') || line.includes('Critical')) {
                        style = 'color: #f87171;'; // Danger red
                    } else if (line.includes('↻') || line.includes('Retrying') || line.includes('⚠️') || line.includes('Warning')) {
                        style = 'color: #fbbf24;'; // Warning yellow
                    } else if (line.includes('Trying download method') || line.includes('Resolved')) {
                        style = 'color: #a78bfa;'; // Lavender for info
                    } else if (line.includes('Processing Run:')) {
                        style = 'color: #22d3ee; font-weight: 700; text-shadow: 0 0 8px rgba(34,211,238,0.3);'; // Cyan run accessions
                    }
                    return style ? `<div style="${style}">${escapeHtml(line)}</div>` : `<div>${escapeHtml(line)}</div>`;
                }).join('');
                
                consoleBox.innerHTML = formattedLogs;
                
                // Auto-scroll if user is already at the bottom
                if (previousScrollHeight - previousScrollTop <= previousClientHeight + 50) {
                    consoleBox.scrollTop = consoleBox.scrollHeight;
                }
            }
        }

        function escapeHtml(text) {
            return text
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }

        function clearActiveLogs() {
            const consoleBox = document.getElementById('terminal_console');
            consoleBox.innerHTML = '';
        }

        // Cancel job
        async function cancelJob(jobId) {
            try {
                const response = await fetch(`/api/jobs/${jobId}/cancel`, { method: 'POST' });
                if (response.ok) {
                    showNotification("Job cancellation requested.");
                    fetchJobs();
                }
            } catch (e) {
                showNotification("Failed to cancel job", true);
            }
        }

        // Start a download job
        async function startDownload() {
            const accession = document.getElementById('accession').value.trim();
            if (!accession) {
                showNotification("Please enter an accession ID", true);
                return;
            }

            const methods = [];
            if (document.getElementById('method_ascp').checked) methods.push('ena-ascp');
            if (document.getElementById('method_prefetch').checked) methods.push('prefetch');
            if (document.getElementById('method_ftp').checked) methods.push('ena-ftp');

            if (methods.length === 0) {
                showNotification("Please select at least one download method", true);
                return;
            }

            try {
                const response = await fetch('/api/jobs', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ accession, methods })
                });
                
                if (response.ok) {
                    const newJob = await response.json();
                    showNotification(`Job started for ${accession}!`);
                    document.getElementById('accession').value = '';
                    selectedJobId = newJob.id;
                    fetchJobs();
                } else {
                    showNotification("Failed to start job", true);
                }
            } catch (e) {
                showNotification("Connection error", true);
            }
        }

        function showNotification(msg, isError = false) {
            const notif = document.getElementById('notification');
            notif.innerText = msg;
            notif.style.background = isError ? 'rgba(239, 68, 68, 0.95)' : 'rgba(13, 20, 38, 0.95)';
            notif.style.borderColor = isError ? varColor('--danger') : varColor('--primary');
            notif.style.display = 'block';
            setTimeout(() => {
                notif.style.display = 'none';
            }, 3000);
        }

        function varColor(variableName) {
            return getComputedStyle(document.documentElement).getPropertyValue(variableName).trim();
        }

        // Initialize and poll
        fetchConfig();
        setInterval(fetchJobs, 1000);
    </script>
</body>
</html>
    """
    return html_content

@app.get("/api/config")
def get_config(detect: bool = False):
    if detect:
        ascli_config = get_ascli_config()
        if "ascp" in ascli_config:
            CONFIG["ascp_bin"] = ascli_config["ascp"]
        if "ssh_private_rsa" in ascli_config:
            CONFIG["ascp_key"] = ascli_config["ssh_private_rsa"]
        elif "ssh_private_dsa" in ascli_config:
            CONFIG["ascp_key"] = ascli_config["ssh_private_dsa"]
    return CONFIG

@app.post("/api/config")
def update_config(config: ConfigModel):
    CONFIG["output_dir"] = os.path.abspath(config.output_dir)
    CONFIG["threads"] = config.threads
    CONFIG["ascp_bin"] = config.ascp_bin
    CONFIG["ascp_key"] = config.ascp_key
    CONFIG["ascp_port"] = config.ascp_port
    CONFIG["ascp_options"] = config.ascp_options
    CONFIG["keep_sra"] = config.keep_sra
    CONFIG["retries"] = config.retries
    return {"status": "ok"}

@app.get("/api/jobs")
def get_jobs():
    # Return jobs copy but exclude logs from standard list to keep response lightweight
    result = {}
    for job_id, job in JOBS.items():
        result[job_id] = {
            "id": job["id"],
            "accession": job["accession"],
            "methods": job["methods"],
            "status": job["status"],
            "progress": job.get("progress", 0),
            "speed": job.get("speed", "0 KB/s"),
            "last_progress_line": job.get("last_progress_line", ""),
            "created_at": job["created_at"],
            "completed_at": job["completed_at"],
            "logs": job["logs"] # We can return logs because UI requests it directly
        }
    return result

@app.post("/api/jobs")
def create_job(new_job: NewJobModel):
    job_id = str(uuid.uuid4())[:8]
    JOBS[job_id] = {
        "id": job_id,
        "accession": new_job.accession,
        "methods": new_job.methods,
        "status": "pending",
        "progress": 0,
        "speed": "0 KB/s",
        "last_progress_line": "",
        "created_at": time.time(),
        "completed_at": None,
        "logs": [],
        "_last_progress_log_time": 0.0
    }
    
    # Run the job thread
    thread = threading.Thread(
        target=run_job_thread,
        args=(job_id, new_job.accession, new_job.methods, CONFIG.copy()),
        daemon=True
    )
    thread.start()
    
    return JOBS[job_id]

@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if JOBS[job_id]["status"] in ["running", "pending"]:
        JOBS[job_id]["status"] = "cancelled"
        add_job_log(job_id, "⚠️ Job cancellation requested by user. Terminating processes...")
        
        # Kill active processes associated with this job ID
        cancel_job_process(job_id)
        
        return {"status": "ok"}
    else:
        return {"status": "error", "message": "Job is not active"}

@app.get("/api/disk_usage")
def get_disk_usage():
    import shutil
    output_dir = CONFIG.get("output_dir", ".")
    try:
        total, used, free = shutil.disk_usage(output_dir)
        return {
            "total": total,
            "used": used,
            "free": free,
            "percent_used": round((used / total) * 100, 1),
            "percent_free": round((free / total) * 100, 1)
        }
    except Exception:
        try:
            total, used, free = shutil.disk_usage(".")
            return {
                "total": total,
                "used": used,
                "free": free,
                "percent_used": round((used / total) * 100, 1),
                "percent_free": round((free / total) * 100, 1)
            }
        except Exception:
            return {
                "total": 4 * 1024 * 1024 * 1024 * 1024,
                "used": 3 * 1024 * 1024 * 1024 * 1024,
                "free": 1024 * 1024 * 1024 * 1024,
                "percent_used": 75.0,
                "percent_free": 25.0
            }

# Mount static assets for built React app
dist_assets = os.path.join(os.path.dirname(__file__), "dist", "assets")
if os.path.exists(dist_assets):
    from fastapi.staticfiles import StaticFiles
    app.mount("/assets", StaticFiles(directory=dist_assets), name="assets")

