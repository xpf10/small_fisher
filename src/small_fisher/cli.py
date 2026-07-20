import os
import sys
import argparse
import multiprocessing
from typing import List, Dict, Any

from small_fisher.utils import logger, console, get_ascli_config
from small_fisher.downloader import (
    query_metadata,
    download_ena_ascp,
    download_ena_ftp,
    download_prefetch,
    check_already_downloaded
)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="small_fisher",
        description="small_fisher: A lightweight, optimized Sequence Read Archive/European Nucleotide Archive downloader."
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommands")
    
    # 'get' command
    get_parser = subparsers.add_parser("get", help="Download runs by accession")
    
    get_parser.add_argument(
        "-r", "--run-identifiers",
        nargs="+",
        required=False,
        help="One or more SRA/ENA run identifiers (e.g. SRR23641780) or study accessions"
    )
    
    get_parser.add_argument(
        "-f", "--run-file",
        default=None,
        help="Path to a text file containing run identifiers (one per line)"
    )
    
    get_parser.add_argument(
        "-m", "--download-methods",
        nargs="+",
        default=["ena-ascp", "prefetch", "ena-ftp"],
        choices=["ena-ascp", "prefetch", "ena-ftp"],
        help="Download methods to attempt in sequence (default: ena-ascp prefetch ena-ftp)"
    )
    
    get_parser.add_argument(
        "-o", "--output-dir",
        default=".",
        help="Output directory for downloaded files (default: current directory)"
    )
    
    # Aspera configuration
    get_parser.add_argument(
        "--ascp-bin",
        default=None,
        help="Path to the Aspera (ascp) binary (default: auto-detect via 'ascli conf ascp info', fallback to ~/.aspera/sdk/ascp)"
    )
    
    get_parser.add_argument(
        "--ascp-key",
        default=None,
        help="Path to the Aspera private key (default: auto-detect via 'ascli conf ascp info' (ssh_private_rsa), fallback to ~/.aspera/sdk/aspera_bypass_rsa.pem)"
    )
    
    get_parser.add_argument(
        "--ascp-port",
        default="33001",
        help="TCP port for Aspera connection (default: 33001)"
    )
    
    get_parser.add_argument(
        "--ascp-options",
        default="-vv -T -k 2",
        help="Aspera options string (default: '-vv -T -k 2')"
    )
    
    # Decompression / parallel configuration
    get_parser.add_argument(
        "-t", "--threads",
        type=int,
        default=multiprocessing.cpu_count(),
        help="Number of threads for parallel-fastq-dump (default: all available CPU cores)"
    )
    
    get_parser.add_argument(
        "--keep-sra",
        action="store_true",
        help="Keep SRA file after decompression when using prefetch (default: False)"
    )
    
    get_parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Number of auto-retries when all download methods fail for a run (default: 2)"
    )
    
    get_parser.add_argument(
        "--verify",
        action="store_true",
        help="Perform MD5 checksum verification of FASTQ files after download or for existing files (default: False)"
    )
    
    # 'ui' command
    ui_parser = subparsers.add_parser("ui", help="Launch the web UI dashboard interface")
    ui_parser.add_argument("--host", default="127.0.0.1", help="Host address to bind to (default: 127.0.0.1)")
    ui_parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    
    return parser.parse_args()



def write_download_report(output_dir: str, overall_success: List[str], failed_runs_errors: Dict[str, str]) -> None:
    """Write a summary report of the download execution to a file in output_dir."""
    from datetime import datetime
    report_path = os.path.join(output_dir, "small_fisher_report.txt")
    try:
        with open(report_path, "w") as f:
            f.write("==================================================\n")
            f.write("             SMALL_FISHER DOWNLOAD REPORT         \n")
            f.write("==================================================\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Success: {len(overall_success)}\n")
            f.write(f"Total Failure: {len(failed_runs_errors)}\n")
            f.write("==================================================\n\n")
            
            f.write("--- SUCCESSFUL RUNS ---\n")
            if overall_success:
                for run in overall_success:
                    f.write(f"{run}\n")
            else:
                f.write("None\n")
            f.write("\n")
            
            f.write("--- FAILED RUNS & ERRORS ---\n")
            if failed_runs_errors:
                for run, err in failed_runs_errors.items():
                    f.write(f"{run}: {err}\n")
            else:
                f.write("None\n")
        logger.info(f"Summary report written to: {report_path}")
    except Exception as e:
        logger.warning(f"Could not write download report: {e}")

def handle_get(args: argparse.Namespace) -> int:
    from small_fisher.utils import CURRENT_LOG_CALLBACK
    
    def cli_log_callback(line: str, is_progress: bool):
        if is_progress:
            # Print in-place cyan progress line and reset cursor to start of line
            sys.stdout.write(f"\r\033[K\033[36m⚡ {line}\033[0m\r")
            sys.stdout.flush()
        else:
            # Clear carriage return line and print normal log line
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()
            logger.info(line)
            
    CURRENT_LOG_CALLBACK.set(cli_log_callback)
    
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)
    
    ascp_options = [opt for opt in args.ascp_options.split() if opt]
    
    ascp_bin = args.ascp_bin
    ascp_key = args.ascp_key
    
    if "ena-ascp" in args.download_methods:
        ascli_config = get_ascli_config()
        
        if not ascp_bin:
            ascp_bin = ascli_config.get("ascp")
            if ascp_bin and os.path.exists(ascp_bin):
                logger.info(f"Auto-detected ascp binary: {ascp_bin}")
            else:
                ascp_bin = os.path.expanduser("~/.aspera/sdk/ascp")
                logger.info(f"Fallback to default ascp binary path: {ascp_bin}")
                
        if not ascp_key:
            ascp_key = ascli_config.get("ssh_private_rsa")
            if ascp_key and os.path.exists(ascp_key):
                logger.info(f"Auto-detected ssh_private_rsa key: {ascp_key}")
            else:
                ascp_key = ascli_config.get("ssh_private_dsa")
                if ascp_key and os.path.exists(ascp_key):
                    logger.info(f"Auto-detected ssh_private_dsa key: {ascp_key}")
                else:
                    ascp_key = os.path.expanduser("~/.aspera/sdk/aspera_bypass_rsa.pem")
                    logger.info(f"Fallback to default ascp key path: {ascp_key}")
    # Resolve run identifiers from CLI arguments and/or run file
    run_identifiers = []
    if args.run_identifiers:
        run_identifiers.extend(args.run_identifiers)
        
    if args.run_file:
        if not os.path.exists(args.run_file):
            logger.error(f"[bold red]✗ Run list file not found: {args.run_file}[/bold red]")
            return 1
        try:
            with open(args.run_file, "r") as f:
                for line in f:
                    line_clean = line.strip()
                    # Skip empty lines and comments
                    if line_clean and not line_clean.startswith("#"):
                        run_identifiers.append(line_clean)
        except Exception as e:
            logger.error(f"[bold red]✗ Error reading run list file {args.run_file}: {e}[/bold red]")
            return 1

    if not run_identifiers:
        logger.error("[bold red]✗ No run identifiers provided. Please specify runs via -r/--run-identifiers or a file via -f/--run-file.[/bold red]")
        return 1
    
    BANNER = """[bold cyan]
  ____                  _ _   _____ _     _               
 / ___| _ __ ___   __ _| | | |  ___(_)___| |__   ___ _ __ 
 \___ \| '_ ` _ \ / _` | | | | |_  | / __| '_ \ / _ \ '__|
  ___) | | | | | | (_| | | | |  _| | \__ \ | | |  __/ |   
 |____/|_| |_| |_|\__,_|_|_| |_|   |_|___/_| |_|\___|_|   
[/bold cyan]"""
    console.print(BANNER)
    
    from rich.panel import Panel
    from rich.table import Table
    
    config_table = Table(show_header=False, box=None)
    config_table.add_row("[bold cyan]Output Directory:[/bold cyan]", output_dir)
    config_table.add_row("[bold cyan]Download Methods:[/bold cyan]", ", ".join(args.download_methods))
    config_table.add_row("[bold cyan]CPU Threads:[/bold cyan]", str(args.threads))
    if "ena-ascp" in args.download_methods:
        config_table.add_row("[bold cyan]Aspera Binary:[/bold cyan]", ascp_bin)
        config_table.add_row("[bold cyan]Aspera RSA Key:[/bold cyan]", ascp_key)
        
    console.print(Panel(config_table, title="[bold magenta]Download Configuration[/bold magenta]", border_style="cyan", expand=False))
    console.print()

    overall_success = []
    overall_failure = []
    failed_runs_errors = {}
    
    # Process each resolved accession
    for accession in run_identifiers:
        logger.info(f"\n[bold magenta]► Processing accession: {accession}[/bold magenta]")
        
        # Query ENA or GSA API to resolve accession to runs
        run_records = query_metadata(accession)
            
        for run_record in run_records:
            run_id = run_record["run_accession"]
            logger.info(f"Resolving run: {run_id}")
            
            # Check if this run is already downloaded and complete
            if check_already_downloaded(run_id, run_records, output_dir, getattr(args, "verify", False)):
                logger.info(f"[bold green]✓ Run {run_id} is already fully downloaded. Skipping.[/bold green]")
                overall_success.append(run_id)
                continue
            
            downloaded = False
            for attempt in range(args.retries + 1):
                if attempt > 0:
                    logger.info(f"\n[bold yellow]↻ Retrying download for {run_id} (Attempt {attempt}/{args.retries})...[/bold yellow]")
                    # Wait before retry (exponential backoff)
                    import time
                    time.sleep(min(2 ** attempt, 30))
                    
                errors = []
                for method in args.download_methods:
                    logger.info(f"Attempting download method: [yellow]{method}[/yellow] for {run_id}...")
                    
                    if method == "ena-ascp":
                        # Check if ascp bin exists first before attempting
                        if not os.path.exists(ascp_bin):
                            err_msg = f"Aspera binary not found at '{ascp_bin}'"
                            logger.warning(f"{err_msg}. Skipping ena-ascp.")
                            errors.append(f"ena-ascp: {err_msg}")
                            continue
                        downloaded = download_ena_ascp(
                            run_record=run_record,
                            output_dir=output_dir,
                            ascp_bin=ascp_bin,
                            ascp_key=ascp_key,
                            ascp_port=args.ascp_port,
                            ascp_options=ascp_options
                        )
                        if not downloaded:
                            errors.append("ena-ascp: Transfer failed (check network/key/SSH)")
                    elif method == "prefetch":
                        downloaded = download_prefetch(
                            accession=run_id,
                            output_dir=output_dir,
                            threads=args.threads,
                            keep_sra=args.keep_sra
                        )
                        if not downloaded:
                            errors.append("prefetch: Download or parallel-fastq-dump decompression failed")
                    elif method == "ena-ftp":
                        downloaded = download_ena_ftp(
                            run_record=run_record,
                            output_dir=output_dir
                        )
                        if not downloaded:
                            errors.append("ena-ftp: HTTP/FTP transfer failed")
                        
                    if downloaded:
                        if getattr(args, "verify", False):
                            from small_fisher.downloader import verify_file_integrity
                            md5_list = [m.strip() for m in run_record.get("fastq_md5", "").split(";") if m.strip()]
                            files = []
                            if "fastq_ftp" in run_record and run_record["fastq_ftp"]:
                                files = [os.path.basename(u) for u in run_record["fastq_ftp"].split(";") if u.strip()]
                            elif "fastq_aspera" in run_record and run_record["fastq_aspera"]:
                                files = [os.path.basename(u) for u in run_record["fastq_aspera"].split(";") if u.strip()]
                            
                            if md5_list and len(md5_list) == len(files):
                                logger.info(f"Verifying MD5 checksums for {run_id}...")
                                is_valid = True
                                for f, expected_md5 in zip(files, md5_list):
                                    filepath = os.path.join(output_dir, f)
                                    logger.info(f"Verifying {f} against MD5 {expected_md5}...")
                                    if not verify_file_integrity(filepath, expected_md5):
                                        logger.error(f"[bold red]✗ MD5 mismatch for {f}[/bold red]")
                                        is_valid = False
                                        break
                                    else:
                                        logger.info(f"[bold green]✓ MD5 verified for {f}[/bold green]")
                                if not is_valid:
                                    logger.warning(f"Integrity check failed for method {method}. Proceeding to fallback...")
                                    downloaded = False
                                    errors.append(f"{method}: MD5 verification failed")
                                    
                        if downloaded:
                            logger.info(f"[bold green]✓ Successfully downloaded {run_id} using {method}.[/bold green]")
                            overall_success.append(run_id)
                            break
                    else:
                        logger.warning(f"Method {method} failed for {run_id}.")
                
                if downloaded:
                    break
            
            if not downloaded:
                err_summary = "; ".join(errors) if errors else "Unknown failure"
                logger.error(f"[bold red]✗ Failed to download {run_id} with all attempted methods. Reason: {err_summary}[/bold red]")
                overall_failure.append(run_id)
                failed_runs_errors[run_id] = err_summary
                
    # Write a summary log file to output_dir
    write_download_report(output_dir, overall_success, failed_runs_errors)
                
    logger.info("\n[bold cyan]==================================================[/bold cyan]")
    logger.info("[bold cyan]                DOWNLOAD SUMMARY                  [/bold cyan]")
    logger.info("[bold cyan]==================================================[/bold cyan]")
    logger.info(f"Successful runs: {len(overall_success)} ({', '.join(overall_success) if overall_success else 'None'})")
    logger.info(f"Failed runs:     {len(overall_failure)} ({', '.join(overall_failure) if overall_failure else 'None'})")
    logger.info("[bold cyan]==================================================[/bold cyan]")
    
    return 0 if len(overall_failure) == 0 else 1

def main() -> None:
    import signal
    
    def signal_handler(sig, frame):
        logger.warning("\n[bold red]Received interrupt signal. Terminating all downloads...[/bold red]")
        from small_fisher.utils import kill_all_active_processes
        kill_all_active_processes()
        sys.exit(1)
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        args = parse_args()
        if args.command == "get":
            sys.exit(handle_get(args))
        elif args.command == "ui":
            import uvicorn
            logger.info(f"🚀 Starting small_fisher Web UI at: [bold cyan]http://{args.host}:{args.port}[/bold cyan]")
            logger.info("Press Ctrl+C to stop the server.")
            uvicorn.run("small_fisher.web:app", host=args.host, port=args.port, reload=False, log_level="warning")
        else:
            logger.error(f"Unknown command: {args.command}")
            sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("\n[bold red]Interrupted by user. Terminating all downloads...[/bold red]")
        from small_fisher.utils import kill_all_active_processes
        kill_all_active_processes()
        sys.exit(1)

if __name__ == "__main__":
    main()
