import os
import sys
import argparse
import multiprocessing
from typing import List, Dict, Any

from small_fisher.utils import logger, console, get_ascli_config
from small_fisher.downloader import (
    query_ena_api,
    construct_fallback_metadata,
    download_ena_ascp,
    download_ena_ftp,
    download_prefetch
)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
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
    
    # 'ui' command
    ui_parser = subparsers.add_parser("ui", help="Launch the web UI dashboard interface")
    ui_parser.add_argument("--host", default="127.0.0.1", help="Host address to bind to (default: 127.0.0.1)")
    ui_parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    
    return parser.parse_args()

def is_run_downloaded(run_record: Dict[str, Any], output_dir: str) -> bool:
    """Check if all expected FASTQ files for the ENA run exist and match expected size."""
    fastq_aspera = run_record.get("fastq_aspera", "")
    fastq_ftp = run_record.get("fastq_ftp", "")
    
    # Use whichever URL metadata is populated
    urls_str = fastq_aspera if fastq_aspera else fastq_ftp
    if not urls_str:
        return False
        
    urls = [u.strip() for u in urls_str.split(";") if u.strip()]
    if not urls:
        return False
        
    bytes_list = []
    try:
        bytes_list = [int(x) for x in run_record.get("fastq_bytes", "").split(";") if x.strip()]
    except Exception:
        pass
        
    for i, url in enumerate(urls):
        filename = os.path.basename(url)
        expected_size = bytes_list[i] if i < len(bytes_list) else 0
        local_path = os.path.join(output_dir, filename)
        
        if not os.path.exists(local_path):
            return False
            
        if expected_size > 0:
            if os.path.getsize(local_path) != expected_size:
                return False
        else:
            if os.path.getsize(local_path) == 0:
                return False
                
    return True

def check_already_downloaded(run_id: str, run_records: List[Dict[str, Any]], output_dir: str) -> bool:
    """Check if the run has already been fully downloaded (FASTQ files exist and are complete)."""
    # 1. Check ENA file reports metadata
    if run_records:
        for record in run_records:
            if is_run_downloaded(record, output_dir):
                return True
                
    # 2. Check standard paired-end/single-end FASTQ filename patterns as a fallback
    paired_1 = os.path.join(output_dir, f"{run_id}_1.fastq.gz")
    paired_2 = os.path.join(output_dir, f"{run_id}_2.fastq.gz")
    single = os.path.join(output_dir, f"{run_id}.fastq.gz")
    
    if os.path.exists(paired_1) and os.path.exists(paired_2):
        if os.path.getsize(paired_1) > 0 and os.path.getsize(paired_2) > 0:
            return True
            
    if os.path.exists(single):
        if os.path.getsize(single) > 0:
            return True
            
    return False

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
    
    logger.info("[bold cyan]==================================================[/bold cyan]")
    logger.info("[bold cyan]             SMALL_FISHER DOWNLOADER             [/bold cyan]")
    logger.info("[bold cyan]==================================================[/bold cyan]")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Download methods: {', '.join(args.download_methods)}")
    logger.info(f"Threads:          {args.threads}")
    if "ena-ascp" in args.download_methods:
        logger.info(f"Ascp Binary:      {ascp_bin}")
        logger.info(f"Ascp Key:         {ascp_key}")
    logger.info("[bold cyan]--------------------------------------------------[/bold cyan]")

    overall_success = []
    overall_failure = []
    failed_runs_errors = {}
    
    # Process each resolved accession
    for accession in run_identifiers:
        logger.info(f"\n[bold magenta]► Processing accession: {accession}[/bold magenta]")
        
        # Query ENA API to resolve accession to runs
        run_records = query_ena_api(accession)
        if not run_records:
            # Try to build fallback metadata if the API query returned nothing
            run_records = construct_fallback_metadata(accession)
            
        for run_record in run_records:
            run_id = run_record["run_accession"]
            logger.info(f"Resolving run: {run_id}")
            
            # Check if this run is already downloaded and complete
            if check_already_downloaded(run_id, run_records, output_dir):
                logger.info(f"[bold green]✓ Run {run_id} is already fully downloaded. Skipping.[/bold green]")
                overall_success.append(run_id)
                continue
            
            downloaded = False
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
                    logger.info(f"[bold green]✓ Successfully downloaded {run_id} using {method}.[/bold green]")
                    overall_success.append(run_id)
                    break
                else:
                    logger.warning(f"Method {method} failed for {run_id}.")
            
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
