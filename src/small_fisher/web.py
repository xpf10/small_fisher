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
    query_ena_api,
    construct_fallback_metadata,
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
    "keep_sra": False
}

class ConfigModel(BaseModel):
    output_dir: str
    threads: int
    ascp_bin: Optional[str] = None
    ascp_key: Optional[str] = None
    ascp_port: str
    ascp_options: str
    keep_sra: bool

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
        run_records = query_ena_api(accession)
        if not run_records:
            add_job_log(job_id, "API query returned no records. Attempting fallback URL construction...")
            run_records = construct_fallback_metadata(accession)
            
        success = True
        for run_record in run_records:
            run_id = run_record["run_accession"]
            add_job_log(job_id, f"--------------------------------------------------")
            add_job_log(job_id, f"Processing Run: {run_id}")
            add_job_log(job_id, f"--------------------------------------------------")
            
            # Check if this run is already downloaded and complete
            if check_already_downloaded(run_id, run_records, current_config["output_dir"]):
                add_job_log(job_id, f"Run {run_id} is already fully downloaded. Skipping.")
                continue
                
            downloaded = False
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
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>small_fisher UI Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0f19;
            --card-bg: rgba(22, 28, 45, 0.7);
            --card-border: rgba(255, 255, 255, 0.08);
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
            --primary: #6366f1;
            --primary-hover: #4f46e5;
            --accent: #22d3ee;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
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
                radial-gradient(circle at 10% 20%, rgba(99, 102, 241, 0.05) 0%, transparent 40%),
                radial-gradient(circle at 90% 80%, rgba(34, 211, 238, 0.05) 0%, transparent 40%);
        }

        header {
            background: rgba(11, 15, 25, 0.8);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--card-border);
            padding: 1.25rem 2rem;
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
            font-size: 1.75rem;
            animation: float 3s ease-in-out infinite;
        }

        @keyframes float {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-4px); }
        }

        .logo-title {
            font-size: 1.5rem;
            font-weight: 700;
            background: linear-gradient(135deg, #fff 30%, var(--accent) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.025em;
        }

        .status-badge {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.875rem;
            background: rgba(16, 185, 129, 0.1);
            color: var(--success);
            padding: 0.375rem 0.75rem;
            border-radius: 9999px;
            border: 1px solid rgba(16, 185, 129, 0.2);
            font-weight: 500;
        }

        .pulse-dot {
            width: 8px;
            height: 8px;
            background-color: var(--success);
            border-radius: 50%;
            animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(0.9); opacity: 0.6; }
            50% { transform: scale(1.2); opacity: 1; }
            100% { transform: scale(0.9); opacity: 0.6; }
        }

        main {
            flex: 1;
            padding: 2rem;
            max-width: 1600px;
            width: 100%;
            margin: 0 auto;
            display: grid;
            grid-template-columns: 350px 1fr;
            gap: 2rem;
        }

        @media (max-width: 1024px) {
            main {
                grid-template-columns: 1fr;
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
            border-radius: 16px;
            padding: 1.5rem;
            backdrop-filter: blur(8px);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
        }

        .card-title {
            font-size: 1.125rem;
            font-weight: 600;
            margin-bottom: 1.25rem;
            color: #fff;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .form-group {
            margin-bottom: 1.25rem;
        }

        .form-group label {
            display: block;
            font-size: 0.875rem;
            font-weight: 500;
            margin-bottom: 0.5rem;
            color: var(--text-muted);
        }

        .form-control {
            width: 100%;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 0.625rem 0.75rem;
            color: #fff;
            font-family: inherit;
            font-size: 0.9375rem;
            transition: all 0.2s;
        }

        .form-control:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2);
        }

        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.75rem;
        }

        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            width: 100%;
            background-color: var(--primary);
            color: #fff;
            border: none;
            border-radius: 8px;
            padding: 0.625rem 1rem;
            font-size: 0.9375rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }

        .btn:hover {
            background-color: var(--primary-hover);
        }

        .btn-secondary {
            background-color: rgba(255, 255, 255, 0.08);
            color: #fff;
            border: 1px solid var(--card-border);
        }

        .btn-secondary:hover {
            background-color: rgba(255, 255, 255, 0.12);
        }

        .btn-danger {
            background-color: var(--danger);
        }
        .btn-danger:hover {
            background-color: #dc2626;
        }

        .checkbox-group {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            margin-top: 0.5rem;
        }

        .checkbox-label {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.9375rem;
            color: var(--text-main);
            cursor: pointer;
        }

        .checkbox-label input {
            cursor: pointer;
            accent-color: var(--primary);
        }

        .content-area {
            display: flex;
            flex-direction: column;
            gap: 2rem;
        }

        .jobs-container {
            display: flex;
            flex-direction: column;
            gap: 1rem;
            max-height: 400px;
            overflow-y: auto;
            padding-right: 0.5rem;
        }

        .jobs-container::-webkit-scrollbar {
            width: 6px;
        }

        .jobs-container::-webkit-scrollbar-thumb {
            background-color: rgba(255, 255, 255, 0.1);
            border-radius: 3px;
        }

        .job-item {
            background: rgba(15, 23, 42, 0.4);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: all 0.2s;
            cursor: pointer;
        }

        .job-item:hover, .job-item.active {
            border-color: rgba(99, 102, 241, 0.4);
            background: rgba(15, 23, 42, 0.6);
        }

        .job-item.active {
            box-shadow: 0 0 12px rgba(99, 102, 241, 0.15);
        }

        .job-info {
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
        }

        .job-accession {
            font-size: 1.0625rem;
            font-weight: 600;
            color: #fff;
        }

        .job-meta {
            font-size: 0.8125rem;
            color: var(--text-muted);
            display: flex;
            gap: 0.75rem;
        }

        .job-status-badge {
            font-size: 0.75rem;
            font-weight: 600;
            padding: 0.125rem 0.5rem;
            border-radius: 9999px;
            text-transform: uppercase;
        }

        .status-pending { background: rgba(156, 163, 175, 0.15); color: #9ca3af; }
        .status-running { background: rgba(99, 102, 241, 0.15); color: #818cf8; animation: pulse 1.5s infinite; }
        .status-completed { background: rgba(16, 185, 129, 0.15); color: #34d399; }
        .status-failed { background: rgba(239, 68, 68, 0.15); color: #f87171; }
        .status-cancelled { background: rgba(245, 158, 11, 0.15); color: #fbbf24; }

        .terminal-card {
            display: flex;
            flex-direction: column;
            flex: 1;
            min-height: 400px;
        }

        .terminal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }

        .terminal-console {
            background-color: #05070c;
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 1rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.875rem;
            line-height: 1.5;
            color: #a7f3d0;
            overflow-y: auto;
            flex: 1;
            height: 300px;
            white-space: pre-wrap;
            box-shadow: inset 0 2px 8px rgba(0,0,0,0.8);
        }

        .no-jobs {
            text-align: center;
            padding: 3rem;
            color: var(--text-muted);
            font-size: 0.9375rem;
        }

        .notify {
            position: fixed;
            bottom: 2rem;
            right: 2rem;
            background: rgba(22, 28, 45, 0.9);
            border: 1px solid var(--primary);
            color: #fff;
            padding: 1rem 1.5rem;
            border-radius: 8px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
            display: none;
            z-index: 100;
            animation: slideIn 0.3s ease-out;
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
            <!-- Configuration Card -->
            <div class="card">
                <div class="card-title">
                    <span>Settings</span>
                    <button class="btn btn-secondary" style="width: auto; padding: 0.25rem 0.5rem; font-size: 0.75rem;" onclick="detectAspera()">Detect via ascli</button>
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
                    <label class="checkbox-label">
                        <input type="checkbox" id="keep_sra"> Keep SRA Files
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
                <div class="terminal-header" style="display:flex; flex-direction:column; gap:0.5rem; align-items:stretch;">
                    <div style="display:flex; justify-content:space-between; align-items:center; width:100%;">
                        <div class="card-title" id="terminal_title" style="margin-bottom:0;">Live Console Logs</div>
                        <button class="btn btn-secondary" style="width: auto;" onclick="clearActiveLogs()">Clear View</button>
                    </div>
                    <div id="live_progress_banner" style="font-family:'JetBrains Mono', monospace; font-size:0.875rem; color:var(--accent); min-height:1.25rem; white-space:pre-wrap; border-left: 2px solid var(--accent); padding-left: 0.5rem; display:none;"></div>
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
                keep_sra: document.getElementById('keep_sra').checked
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
                        actionButton = `<button class="btn btn-danger" style="width:auto; padding: 0.25rem 0.5rem; font-size: 0.75rem;" onclick="event.stopPropagation(); cancelJob('${job.id}')">Cancel</button>`;
                    }
                    
                    html += `
                        <div class="job-item ${isActive}" onclick="selectJob('${job.id}')" style="display:flex; flex-direction:column; gap:0.5rem; align-items:stretch;">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <div class="job-info">
                                    <div class="job-accession">${job.accession}</div>
                                    <div class="job-meta" style="flex-wrap:wrap;">
                                        <span class="job-status-badge status-${job.status}">${job.status}</span>
                                        <span>Methods: ${job.methods.join(', ')}</span>
                                        ${job.status === 'running' && job.speed ? `<span style="color:var(--accent); font-weight:500;">⚡ ${job.speed} (${job.progress || 0}%)</span>` : ''}
                                    </div>
                                </div>
                                <div>
                                    ${actionButton}
                                </div>
                            </div>
                            ${job.status === 'running' ? `
                            <div style="width: 100%; background: rgba(255,255,255,0.05); height: 6px; border-radius: 3px; overflow: hidden; border: 1px solid rgba(255,255,255,0.05); position:relative; margin-top:0.25rem;">
                                <div style="width: ${job.progress || 0}%; background: linear-gradient(90deg, var(--primary) 0%, var(--accent) 100%); height: 100%; transition: width 0.3s ease;"></div>
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
            document.getElementById('terminal_title').innerText = `Console Logs: ${job.accession} (${job.id})`;
            const consoleBox = document.getElementById('terminal_console');
            const progressBanner = document.getElementById('live_progress_banner');
            
            if (job.status === 'running' && job.last_progress_line) {
                progressBanner.innerText = `⏳ Active Progress: ${job.last_progress_line}`;
                progressBanner.style.display = 'block';
            } else {
                progressBanner.style.display = 'none';
            }
            
            if (job.logs.length === 0) {
                consoleBox.innerText = 'Starting up job. Waiting for logs...';
            } else {
                const previousScrollHeight = consoleBox.scrollHeight;
                const previousScrollTop = consoleBox.scrollTop;
                const previousClientHeight = consoleBox.clientHeight;
                
                consoleBox.innerText = job.logs.join('\\n');
                
                // Auto-scroll if user is already at the bottom
                if (previousScrollHeight - previousScrollTop <= previousClientHeight + 50) {
                    consoleBox.scrollTop = consoleBox.scrollHeight;
                }
            }
        }

        function clearActiveLogs() {
            const consoleBox = document.getElementById('terminal_console');
            consoleBox.innerText = '';
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
            notif.style.background = isError ? 'rgba(239, 68, 68, 0.9)' : 'rgba(22, 28, 45, 0.9)';
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
