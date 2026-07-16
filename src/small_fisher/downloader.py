import os
import glob
import subprocess
import threading
import time
from typing import List, Optional, Dict, Any
import requests
from small_fisher.utils import logger, run_command, check_binary

def get_ena_subdir(accession: str) -> str:
    """Calculate ENA 3-digit subdirectory based on accession length."""
    if len(accession) <= 9:
        return ""
    elif len(accession) == 10:
        return f"00{accession[-1]}"
    elif len(accession) == 11:
        return f"0{accession[-2:]}"
    elif len(accession) == 12:
        return accession[-3:]
    else:
        return accession[-3:]

def query_ena_api(accession: str) -> List[Dict[str, Any]]:
    """Query the ENA Portal API to get run metadata (FASTQ FTP/Aspera links)."""
    import re
    is_gse = bool(re.match(r"^GSE\d+$", accession, re.IGNORECASE))
    
    if is_gse:
        url = "https://www.ebi.ac.uk/ena/portal/api/search"
        params = {
            "result": "read_run",
            "query": f'study_alias="{accession}" OR secondary_study_accession="{accession}"',
            "fields": "run_accession,fastq_ftp,fastq_aspera,fastq_md5,fastq_bytes",
            "format": "json"
        }
    else:
        url = "https://www.ebi.ac.uk/ena/portal/api/filereport"
        params = {
            "accession": accession,
            "result": "read_run",
            "fields": "run_accession,fastq_ftp,fastq_aspera,fastq_md5,fastq_bytes",
            "format": "json"
        }
        
    try:
        logger.info(f"Querying ENA Portal API for accession: {accession}...")
        response = requests.get(url, params=params, timeout=20)
        if response.status_code == 200:
            if not response.text.strip():
                logger.warning(f"No run records found in ENA response for {accession}")
                return []
            try:
                data = response.json()
            except Exception:
                logger.warning(f"Could not parse JSON response from ENA: {response.text}")
                return []
                
            if isinstance(data, list) and len(data) > 0:
                logger.info(f"[bold green]✓ Found {len(data)} runs in ENA database.[/bold green]")
                return data
            else:
                logger.warning(f"No run records found in response for {accession}")
        else:
            logger.warning(f"ENA Portal API returned status code {response.status_code}")
    except Exception as e:
        logger.warning(f"ENA Portal API request failed: {e}")
    return []

def construct_fallback_metadata(accession: str) -> List[Dict[str, Any]]:
    """Construct fallback metadata based on accession prefix when ENA API is down."""
    import re
    if re.match(r"^GSE\d+$", accession, re.IGNORECASE):
        logger.warning(f"Fallback metadata construction is not supported for GEO GSE accessions ({accession}).")
        return []
        
    logger.info(f"Constructing fallback metadata URLs for {accession}...")
    prefix = accession[:6]
    subdir = get_ena_subdir(accession)
    path_part = f"{prefix}/{subdir}/{accession}" if subdir else f"{prefix}/{accession}"
    
    # We construct the standard paired-end paths
    fastq_ftp_paired = f"ftp.sra.ebi.ac.uk/vol1/fastq/{path_part}/{accession}_1.fastq.gz;ftp.sra.ebi.ac.uk/vol1/fastq/{path_part}/{accession}_2.fastq.gz"
    fastq_aspera_paired = f"fasp.sra.ebi.ac.uk:/vol1/fastq/{path_part}/{accession}_1.fastq.gz;fasp.sra.ebi.ac.uk:/vol1/fastq/{path_part}/{accession}_2.fastq.gz"
    
    return [{
        "run_accession": accession,
        "fastq_ftp": fastq_ftp_paired,
        "fastq_aspera": fastq_aspera_paired,
        "fastq_md5": "",
        "fastq_bytes": "",
        "is_fallback": True
    }]

def monitor_file_progress_thread(
    output_dir: str,
    filename: str,
    expected_size: int,
    stop_event: threading.Event,
    callback,
    file_index: int = 1,
    total_files: int = 1
) -> None:
    """Monitor a single file in output_dir and calculate progress and speed for the UI/CLI."""
    if expected_size <= 0:
        return
        
    last_size = 0
    last_time = time.time()
    
    # Label single-end vs paired-end
    if total_files > 1:
        prefix_label = f"({file_index}/{total_files})"
    else:
        prefix_label = ""
        
    while not stop_event.is_set():
        current_size = 0
        finished_path = os.path.join(output_dir, filename)
        partial_path = os.path.join(output_dir, filename + ".partial")
        tmp_path = os.path.join(output_dir, filename + ".tmp")
        
        # Check size of completed or active partial files
        if os.path.exists(finished_path):
            current_size = os.path.getsize(finished_path)
        elif os.path.exists(partial_path):
            current_size = os.path.getsize(partial_path)
        elif os.path.exists(tmp_path):
            current_size = os.path.getsize(tmp_path)
            
        now = time.time()
        elapsed = now - last_time
        if elapsed >= 1.0:
            speed_val = (current_size - last_size) / elapsed
            # Format speed string
            if speed_val >= 1024 * 1024:
                speed_str = f"{speed_val / (1024 * 1024):.1f} Mb/s"
            elif speed_val >= 1024:
                speed_str = f"{speed_val / 1024:.1f} Kb/s"
            else:
                speed_str = f"{speed_val:.1f} b/s"
                
            pct = int((current_size / expected_size) * 100)
            pct = min(pct, 100)
            
            # Format progress line matching (\d+)% and speed patterns
            progress_line = f"Downloading {filename} {prefix_label}... {pct}% | Speed: {speed_str} | {current_size}/{expected_size} bytes"
            callback(progress_line, True)
            
            last_size = current_size
            last_time = now
            
        time.sleep(0.5)

def download_ena_ascp(
    run_record: Dict[str, Any],
    output_dir: str,
    ascp_bin: str,
    ascp_key: str,
    ascp_port: str,
    ascp_options: List[str]
) -> bool:
    """Download FASTQ files using Aspera (ascp)."""
    accession = run_record["run_accession"]
    aspera_urls_str = run_record.get("fastq_aspera", "")
    
    if not aspera_urls_str:
        logger.warning(f"No Aspera URLs in metadata for run {accession}")
        return False
        
    urls = [u.strip() for u in aspera_urls_str.split(";") if u.strip()]
    success_count = 0
    
    # Ensure ascp bin and key exist
    if not os.path.exists(ascp_bin):
        logger.error(f"[bold red]✗ Aspera binary not found at: {ascp_bin}[/bold red]")
        return False
    if not os.path.exists(ascp_key):
        logger.error(f"[bold red]✗ Aspera private key file not found at: {ascp_key}[/bold red]")
        return False

    # Parse expected sizes from metadata
    from small_fisher.utils import CURRENT_LOG_CALLBACK
    callback = CURRENT_LOG_CALLBACK.get()
    
    bytes_list = []
    try:
        bytes_list = [int(x) for x in run_record.get("fastq_bytes", "").split(";") if x.strip()]
    except Exception:
        pass
        
    expected_sizes = {}
    for i, url in enumerate(urls):
        filename = os.path.basename(url)
        expected_sizes[filename] = bytes_list[i] if i < len(bytes_list) else 0

    # We will try the given key first. If it is a DSA key and fails, we'll try the RSA key.
    keys_to_try = [ascp_key]
    if "dsa" in ascp_key.lower():
        rsa_key = ascp_key.replace("dsa", "rsa").replace("DSA", "RSA")
        if os.path.exists(rsa_key) and rsa_key != ascp_key:
            keys_to_try.append(rsa_key)

    # Copy current environment and set standard password bypass
    env = os.environ.copy()
    env["ASPERA_SCP_PASS"] = "SRA"

    downloaded_successfully = False
    
    for key in keys_to_try:
        # Ensure private key has secure permissions (0600) required by SSH/ascp
        try:
            os.chmod(key, 0o600)
        except Exception as e:
            logger.warning(f"Could not change permissions of private key {key} to 0600: {e}")

        success_count = 0
        for i, url in enumerate(urls):
            filename = os.path.basename(url)
            expected_size = expected_sizes.get(filename, 0)
            
            # Ensure era-fasp@ prefix is present for ENA download
            if "fasp.sra.ebi.ac.uk" in url and "era-fasp@" not in url:
                url = url.replace("fasp.sra.ebi.ac.uk", "era-fasp@fasp.sra.ebi.ac.uk")
                
            cmd = [
                ascp_bin,
                *ascp_options,
                "-P", ascp_port,
                "-i", key,
                url,
                output_dir
            ]
            
            # Start file progress monitor
            stop_event = threading.Event()
            monitor_thread = None
            if callback and expected_size > 0:
                monitor_thread = threading.Thread(
                    target=monitor_file_progress_thread,
                    args=(output_dir, filename, expected_size, stop_event, callback, i + 1, len(urls)),
                    daemon=True
                )
                monitor_thread.start()
                
            try:
                ok = run_command(cmd, f"Aspera download of {filename} using {os.path.basename(key)}", env=env)
                if ok:
                    success_count += 1
            finally:
                stop_event.set()
                if monitor_thread:
                    monitor_thread.join(timeout=1.0)

        if success_count == len(urls) and len(urls) > 0:
            downloaded_successfully = True
            break
        elif success_count > 0:
            # Partial success, we still consider it success for this run
            downloaded_successfully = True
            break
        else:
            logger.warning(f"Aspera transfer failed using key: {key}")

    # Handle single-end fallback if it was a constructed fallback and the paired download failed
    if not downloaded_successfully and run_record.get("is_fallback"):
        for key in keys_to_try:
            logger.info(f"Paired-end download failed. Trying single-end fallback for {accession} using {os.path.basename(key)}...")
            prefix = accession[:6]
            subdir = get_ena_subdir(accession)
            path_part = f"{prefix}/{subdir}/{accession}" if subdir else f"{prefix}/{accession}"
            single_url = f"era-fasp@fasp.sra.ebi.ac.uk:/vol1/fastq/{path_part}/{accession}.fastq.gz"
            
            cmd = [
                ascp_bin,
                *ascp_options,
                "-P", ascp_port,
                "-i", key,
                single_url,
                output_dir
            ]
            
            ok = run_command(cmd, f"Aspera download of single-end {accession}.fastq.gz", env=env)
            if ok:
                downloaded_successfully = True
                break
            
    return downloaded_successfully

def download_url(url: str, output_path: str) -> bool:
    """Download a file via HTTP/HTTPS using wget, curl, or requests."""
    # Convert ftp.sra.ebi.ac.uk to HTTPS URL for speed and reliability
    if url.startswith("ftp.sra.ebi.ac.uk"):
        http_url = "https://" + url
    elif url.startswith("ftp://"):
        http_url = url.replace("ftp://", "https://")
    else:
        http_url = url
        
    if check_binary("wget"):
        cmd = ["wget", "-c", "-O", output_path, http_url]
        return run_command(cmd, f"wget download of {os.path.basename(output_path)}")
    elif check_binary("curl"):
        cmd = ["curl", "-L", "-o", output_path, "-C", "-", http_url]
        return run_command(cmd, f"curl download of {os.path.basename(output_path)}")
    else:
        logger.info(f"Downloading {http_url} via Python requests...")
        try:
            response = requests.get(http_url, stream=True, timeout=30)
            response.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info(f"[bold green]✓ Downloaded {os.path.basename(output_path)}.[/bold green]")
            return True
        except Exception as e:
            logger.error(f"[bold red]✗ Failed to download {http_url}: {e}[/bold red]")
            return False

def download_ena_ftp(run_record: Dict[str, Any], output_dir: str) -> bool:
    """Download FASTQ files using ENA FTP (converted to HTTP)."""
    accession = run_record["run_accession"]
    ftp_urls_str = run_record.get("fastq_ftp", "")
    
    if not ftp_urls_str:
        logger.warning(f"No FTP URLs in metadata for run {accession}")
        return False
        
    urls = [u.strip() for u in ftp_urls_str.split(";") if u.strip()]
    success_count = 0
    
    # Parse expected sizes from metadata
    from small_fisher.utils import CURRENT_LOG_CALLBACK
    callback = CURRENT_LOG_CALLBACK.get()
    
    bytes_list = []
    try:
        bytes_list = [int(x) for x in run_record.get("fastq_bytes", "").split(";") if x.strip()]
    except Exception:
        pass
        
    expected_sizes = {}
    for i, url in enumerate(urls):
        filename = os.path.basename(url)
        expected_sizes[filename] = bytes_list[i] if i < len(bytes_list) else 0

    for i, url in enumerate(urls):
        filename = os.path.basename(url)
        expected_size = expected_sizes.get(filename, 0)
        output_path = os.path.join(output_dir, filename)
        
        # Start file progress monitor
        stop_event = threading.Event()
        monitor_thread = None
        if callback and expected_size > 0:
            monitor_thread = threading.Thread(
                target=monitor_file_progress_thread,
                args=(output_dir, filename, expected_size, stop_event, callback, i + 1, len(urls)),
                daemon=True
            )
            monitor_thread.start()
            
        try:
            ok = download_url(url, output_path)
            if ok:
                success_count += 1
        finally:
            stop_event.set()
            if monitor_thread:
                monitor_thread.join(timeout=1.0)
                
    # Handle single-end fallback if it was a constructed fallback and the paired download failed
    if success_count == 0 and run_record.get("is_fallback"):
        logger.info(f"Paired-end FTP download failed. Trying single-end fallback for {accession}...")
        prefix = accession[:6]
        subdir = get_ena_subdir(accession)
        path_part = f"{prefix}/{subdir}/{accession}" if subdir else f"{prefix}/{accession}"
        single_url = f"ftp.sra.ebi.ac.uk/vol1/fastq/{path_part}/{accession}.fastq.gz"
        output_path = os.path.join(output_dir, f"{accession}.fastq.gz")
        ok = download_url(single_url, output_path)
        return ok
        
    return success_count > 0

def decompress_sra_parallel(
    sra_path: str,
    accession: str,
    output_dir: str,
    threads: int,
    keep_sra: bool = False
) -> bool:
    """Decompress a local SRA file using parallel-fastq-dump (or fallback to fasterq-dump)."""
    if check_binary("parallel-fastq-dump"):
        cmd = [
            "parallel-fastq-dump",
            "-s", sra_path,
            "-t", str(threads),
            "--outdir", output_dir,
            "--split-files",
            "--gzip"
        ]
        ok = run_command(cmd, f"parallel-fastq-dump decompression of {accession}")
        if ok:
            if not keep_sra:
                logger.info(f"Cleaning up SRA file: {sra_path}")
                try:
                    os.remove(sra_path)
                    # Try to remove containing directory if it is empty and inside output_dir
                    parent_dir = os.path.dirname(sra_path)
                    if parent_dir != output_dir and not os.listdir(parent_dir):
                        os.rmdir(parent_dir)
                except Exception as e:
                    logger.warning(f"Could not remove SRA file or folder: {e}")
            return True
    else:
        logger.warning("[bold yellow]parallel-fastq-dump not found in PATH.[/bold yellow]")
        if check_binary("fasterq-dump"):
            logger.info("Falling back to fasterq-dump...")
            cmd = [
                "fasterq-dump",
                sra_path,
                "-e", str(threads),
                "-O", output_dir,
                "--split-files"
            ]
            ok = run_command(cmd, f"fasterq-dump decompression of {accession}")
            if ok:
                # Gzip the output fastq files
                logger.info("Compressing extracted FASTQ files...")
                fastqs = glob.glob(os.path.join(output_dir, f"{accession}*.fastq"))
                for fq in fastqs:
                    if check_binary("pigz"):
                        run_command(["pigz", "-p", str(threads), fq], f"pigz compression of {os.path.basename(fq)}")
                    else:
                        run_command(["gzip", fq], f"gzip compression of {os.path.basename(fq)}")
                
                if not keep_sra:
                    try:
                        os.remove(sra_path)
                        parent_dir = os.path.dirname(sra_path)
                        if parent_dir != output_dir and not os.listdir(parent_dir):
                            os.rmdir(parent_dir)
                    except Exception as e:
                        pass
                return True
        else:
            logger.error("[bold red]Neither parallel-fastq-dump nor fasterq-dump was found in PATH. Extraction failed.[/bold red]")
    return False

def find_downloaded_sra(accession: str, search_dir: str) -> Optional[str]:
    """Search for the downloaded SRA file locally."""
    # Check expected path format from prefetch: search_dir/accession/accession.sra
    path1 = os.path.join(search_dir, accession, f"{accession}.sra")
    if os.path.exists(path1):
        return path1
        
    # Check direct path search_dir/accession.sra
    path2 = os.path.join(search_dir, f"{accession}.sra")
    if os.path.exists(path2):
        return path2
        
    # Try using srapath
    if check_binary("srapath"):
        try:
            res = subprocess.run(["srapath", accession], capture_output=True, text=True, check=True)
            path = res.stdout.strip()
            if path and os.path.exists(path) and path.endswith(".sra"):
                return path
        except Exception:
            pass
            
    # Recursive search in search_dir as a final resort
    for root, _, files in os.walk(search_dir):
        for f in files:
            if f == f"{accession}.sra":
                return os.path.join(root, f)
                
    return None

def download_prefetch(
    accession: str,
    output_dir: str,
    threads: int,
    keep_sra: bool = False
) -> bool:
    """Download SRA file using prefetch, then decompress using parallel-fastq-dump."""
    if not check_binary("prefetch"):
        logger.error("[bold red]✗ prefetch (SRA Toolkit) is not found in PATH.[/bold red]")
        return False
        
    cmd = ["prefetch", accession, "-O", output_dir]
    ok = run_command(cmd, f"prefetch download of {accession}")
    if not ok:
        return False
        
    # Locate the downloaded SRA file
    sra_path = find_downloaded_sra(accession, output_dir)
    if not sra_path:
        logger.error(f"[bold red]✗ SRA file for {accession} could not be located after prefetch.[/bold red]")
        return False
        
    logger.info(f"[bold green]✓ SRA file located at: {sra_path}[/bold green]")
    
    # Decompress using parallel-fastq-dump
    return decompress_sra_parallel(sra_path, accession, output_dir, threads, keep_sra)

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
