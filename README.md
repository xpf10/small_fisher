# small_fisher 🎣

`small_fisher` is a lightweight, high-performance, and optimized alternative to Kingfisher for downloading sequence data and metadata from public databases (ENA/SRA).

Built with [uv](https://github.com/astral-sh/uv), it optimizes and simplifies retrieval using ENA's official API with robust protocol fallback, and introduces key speedups for SRA decompression and Aspera transfers.

---

## 🌟 Key Features

1. **Optimized `prefetch` Decompression**: Uses `parallel-fastq-dump` instead of standard `fastq-dump` or `fasterq-dump` to split decompression workloads across multiple CPU cores, automatically gzipping the outputs.
2. **ENA Aspera Command Redirection**: Automatically translates standard `kingfisher get -r SRR23641780 -m ena-ascp` commands to use the optimized `ascp` parameters requested:
   ```bash
   ~/.aspera/sdk/ascp -vv -T -P 33001 -k 2 -i ~/.aspera/sdk/aspera_bypass_rsa.pem era-fasp@fasp.sra.ebi.ac.uk:/vol1/fastq/SRR236/080/SRR23641780/SRR23641780_1.fastq.gz .
   ```
3. **Smart ENA API Queries**: Resolves accessions (including sample/study accessions) using ENA's File Report API to find exact FASTQ links, with a deterministic path construction fallback if the API is down.
4. **Enhanced FTP Downloads**: Converts FTP URLs to HTTPS for faster downloads using `wget`, `curl`, or Python `requests` depending on availability.

---

## ⚙️ Installation

### Option A: Using `uv` (Fastest, Recommended)

Initialize and install `small_fisher` directly using `uv`:

```bash
# Clone the repository and navigate into it
git clone https://github.com/xpf10/small_fisher.git
cd small_fisher

# Install and compile the tool using uv
uv pip install -e .
```

### Option B: In a Conda / Micromamba Environment

If you want to install it into an existing Conda environment (like `kingfisher_2`):

```bash
# 1. Activate your conda environment
conda activate kingfisher_2

# 2. Ensure pip is installed in the environment
conda install pip -y

# 3. Clone and navigate to the project directory
git clone https://github.com/xpf10/small_fisher.git
cd small_fisher

# 4. Install the package in editable (development) mode
pip install -e .
```

---

## 🚀 Usage

### 1. Download via Aspera (ena-ascp)

By default, running `small_fisher get` with the `ena-ascp` method:

```bash
small_fisher get -r SRR23641780 -m ena-ascp
```

Translates under the hood to the optimized command:

```bash
~/.aspera/sdk/ascp -vv -T -P 33001 -k 2 -i ~/.aspera/sdk/aspera_bypass_rsa.pem era-fasp@fasp.sra.ebi.ac.uk:/vol1/fastq/SRR236/080/SRR23641780/SRR23641780_1.fastq.gz .
```

You can customize the Aspera binary, private key, port, and flags:

```bash
small_fisher get -r SRR23641780 -m ena-ascp \
  --ascp-bin /path/to/ascp \
  --ascp-key /path/to/key.pem \
  --ascp-port 33001 \
  --ascp-options "-vv -T -k 2"
```

### 2. Download via Prefetch and Parallel Fastq Dump

To download the SRA run format via NCBI `prefetch` and decompress it using `parallel-fastq-dump`:

```bash
small_fisher get -r SRR23641780 -m prefetch -t 8
```

This will:
1. Run `prefetch SRR23641780 -O <output_dir>`.
2. Locate the downloaded `.sra` file.
3. Run `parallel-fastq-dump -s /path/to/SRR23641780.sra -t 8 --outdir <output_dir> --split-files --gzip`.
4. Delete the intermediate `.sra` file to save disk space (unless `--keep-sra` is specified).

### 3. Fallback / Multi-Method Download

If you want `small_fisher` to automatically fall back to another method when your primary method fails (like Kingfisher does), list them in order:

```bash
small_fisher get -r SRR23641780 -m ena-ascp prefetch ena-ftp -o ./data -t 12
```

### 4. Web UI Dashboard Interface

`small_fisher` includes a premium, glassmorphic dark-mode web interface to manage your downloads visually.

To launch the web UI, run:
```bash
small_fisher ui --host 127.0.0.1 --port 8000
```
Open `http://127.0.0.1:8000` in your web browser. You will be able to:
- Configure output directories, threads, and Aspera parameters.
- Trigger real-time, automatic configuration scans using the `Detect via ascli` button.
- Monitor active downloads, view live console logs, and cancel running tasks instantly.

### 5. Batch Download via File List

If you have a list of run identifiers in a text file (one per line, ignoring comments starting with `#`), you can specify it using `-f` or `--run-file`:

```bash
small_fisher get -f /path/to/runs.txt -m ena-ascp
```

---

## 🛠️ CLI Options

Run `small_fisher get --help` to view all options:

```text
usage: small-fisher get [-h] [-r RUN_IDENTIFIERS [RUN_IDENTIFIERS ...]]
                        [-f RUN_FILE]
                        [-m {ena-ascp,prefetch,ena-ftp} [{ena-ascp,prefetch,ena-ftp} ...]]
                        [-o OUTPUT_DIR] [--ascp-bin ASCP_BIN]
                        [--ascp-key ASCP_KEY] [--ascp-port ASCP_PORT]
                        [--ascp-options ASCP_OPTIONS] [-t THREADS]
                        [--keep-sra]

options:
  -h, --help            show this help message and exit
  -r RUN_IDENTIFIERS [RUN_IDENTIFIERS ...], --run-identifiers RUN_IDENTIFIERS [RUN_IDENTIFIERS ...]
                        One or more SRA/ENA run identifiers (e.g. SRR23641780)
                        or study accessions
  -f RUN_FILE, --run-file RUN_FILE
                        Path to a text file containing run identifiers (one
                        per line)
  -m {ena-ascp,prefetch,ena-ftp} [{ena-ascp,prefetch,ena-ftp} ...], --download-methods {ena-ascp,prefetch,ena-ftp} [{ena-ascp,prefetch,ena-ftp} ...]
                        Download methods to attempt in sequence (default: ena-
                        ascp prefetch ena-ftp)
  -o OUTPUT_DIR, --output-dir OUTPUT_DIR
                        Output directory for downloaded files (default:
                        current directory)
  --ascp-bin ASCP_BIN   Path to the Aspera (ascp) binary (default: auto-detect
                        via 'ascli conf ascp info', fallback to
                        ~/.aspera/sdk/ascp)
  --ascp-key ASCP_KEY   Path to the Aspera private key (default: auto-detect
                        via 'ascli conf ascp info' (ssh_private_rsa), fallback
                        to ~/.aspera/sdk/aspera_bypass_rsa.pem)
  --ascp-port ASCP_PORT
                        TCP port for Aspera connection (default: 33001)
  --ascp-options ASCP_OPTIONS
                        Aspera options string (default: '-vv -T -k 2')
  -t THREADS, --threads THREADS
                        Number of threads for parallel-fastq-dump (default:
                        all available CPU cores)
  --keep-sra            Keep SRA file after decompression when using prefetch
                        (default: False)
```
