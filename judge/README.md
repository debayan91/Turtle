# Judge Benchmark Suite

Judge is a deterministic, programmatic stress-testing and micro-benchmarking harness designed to measure the performance of Command Line Interface (CLI) AI agent architectures (such as `turtle` and `pi`).

Since traditional load-testing tools (e.g., K6, Locust) evaluate server performance under multi-client load, Judge inverts the architecture: the agent acts as the client under test, while Judge provides a deterministic mock LLM server and a headless driver to measure client-side I/O, parsing, execution latency, and resource consumption.

---

## Architectural Metrics Measured

1. **Cold Start Latency**: Time elapsed from binary execution to readiness for initial user input.
2. **Time-to-First-Render (TTFR) Overhead**: Time from the mock server emitting the first SSE chunk to stdout rendering.
3. **Stream Throughput (Tokens / Second)**: Parsing, decoding, and rendering throughput over continuous token streams (50,000+ tokens).
4. **Tool Dispatch & Subprocess Latency**: Latency from complete tool-call payload receipt to OS subprocess execution (`asyncio.create_subprocess_shell` vs Node.js `child_process.spawn`).
5. **State Serialization Overhead**: Duration required to process and write full session states to disk.
6. **Resource Footprint**: Peak Resident Set Size (RSS memory in MB) and maximum CPU utilization (%) sampled during execution.

---

## Project Structure

```
judge/
├── server.py        # Deterministic Mock LLM Server (FastAPI / SSE)
├── driver.py        # Subprocess Orchestrator, PTY Harness, and Telemetry Engine
├── requirements.txt # Python dependencies
└── scenarios/       # Standardized benchmark scenario configurations
    ├── firehose.json     # High-volume streaming benchmark (50,000 tokens)
    ├── ping_pong.json    # Rapid sequential tool call execution (100 iterations)
    └── fat_context.json  # Large context window history parsing benchmark
```

---

## Component Details

### 1. Mock Server (`server.py`)
A FastAPI application simulating an OpenAI-compliant Chat Completions endpoint (`/v1/chat/completions`). It supports two operational modes:
* **Zero-Latency Mode**: Transmits chunks at maximum TCP socket velocity.
* **Simulated Network Mode**: Introduces artificial latency (10ms interval per chunk) to simulate realistic network delivery.

### 2. Headless Driver (`driver.py`)
The primary benchmark orchestrator.
* Spawns `server.py` on port `8000`.
* Configures environment variables to redirect agent traffic to the local mock server (`OPENAI_BASE_URL`).
* Launches target harness processes within a pseudo-terminal (`pty`) to capture standard I/O streams.
* Samples target process RAM (RSS) and CPU percentage every 10ms via `psutil`.
* Computes nanosecond-accurate telemetry using `time.perf_counter()`.
* Formats benchmark metrics into structured output tables.

### 3. Benchmark Scenarios (`scenarios/*.json`)
* **`firehose.json`**: Evaluates stream parsing and terminal UI rendering capacity by delivering 50,000 text tokens in rapid succession.
* **`ping_pong.json`**: Evaluates context-switching speed between network payload parsing and OS subprocess execution by requesting 100 sequential tool invocations (`echo 'hello'`).
* **`fat_context.json`**: Tests state serialization and memory footprint when initializing large conversation histories.

---

## Installation & Setup

Ensure dependencies are installed within your Python environment:

```bash
pip install -r judge/requirements.txt
```

Or using an explicit virtual environment:

```bash
./venv/bin/pip install -r judge/requirements.txt
```

---

## Command Reference

### Default Benchmark Execution

Run the default benchmark (`turtle` agent with `firehose` scenario in `zero_latency` mode):

```bash
python judge/driver.py
```

### Command-Line Arguments

`driver.py` accepts the following options:

* `--target <agent>`: Target agent executable (`turtle`, `pi`, or custom shell command string). Default: `turtle`.
* `--scenario <name>`: Benchmark scenario name (`firehose`, `ping_pong`, `fat_context`). Default: `firehose`.
* `--mode <mode>`: Network timing mode (`zero_latency`, `simulated_network`). Default: `zero_latency`.

---

## Execution Examples

### 1. Firehose Benchmark (Stream Throughput & Memory)

#### Python Agent (`turtle`)
```bash
python judge/driver.py --target turtle --scenario firehose --mode zero_latency
```

#### TypeScript Agent (`pi`)
```bash
python judge/driver.py --target pi --scenario firehose --mode zero_latency
```

#### Simulated Network Conditions (10ms latency chunks)
```bash
python judge/driver.py --target turtle --scenario firehose --mode simulated_network
```

---

### 2. Ping-Pong Benchmark (Tool Dispatch & Subprocess Latency)

#### Python Agent (`turtle`)
```bash
python judge/driver.py --target turtle --scenario ping_pong --mode zero_latency
```

#### TypeScript Agent (`pi`)
```bash
python judge/driver.py --target pi --scenario ping_pong --mode zero_latency
```

---

### 3. Fat Context Benchmark (State Serialization Overhead)

#### Python Agent (`turtle`)
```bash
python judge/driver.py --target turtle --scenario fat_context --mode zero_latency
```

#### TypeScript Agent (`pi`)
```bash
python judge/driver.py --target pi --scenario fat_context --mode zero_latency
```

---

### 4. Running Benchmarks with Custom Binary Commands

To evaluate arbitrary executables or custom launch scripts, pass the complete command string to `--target`:

```bash
python judge/driver.py --target "python3 -m turtle_agent" --scenario firehose
```

```bash
python judge/driver.py --target "node pi/dist/index.js" --scenario ping_pong
```
