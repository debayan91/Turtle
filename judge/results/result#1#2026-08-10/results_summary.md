# Benchmark Results Summary (`result#1#2026-08-10`)

## Side-by-Side Architectural Comparison (`turtle` vs `pi`)

| Scenario | Metric | Turtle (Python) | Pi (TypeScript) | Advantage / Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Firehose** | Stream Throughput (tokens/s) | **53,299** | 40,171 | **Turtle (+32.7% faster)** |
| | Cold Start Latency | **0.013 s** | 0.014 s | **Turtle (Slightly faster)** |
| | TTFR Overhead | 0.573 s | **0.000 s** | Pi |
| | Peak RAM (MB) | 227.0 MB | **184.8 MB** | Pi |
| | Peak CPU (%) | **115.4 %** | 322.6 % | **Turtle (2.8x less CPU usage)** |
| **Ping-Pong** | Tool Dispatch & Subprocess Latency | 6.368 s | **3.379 s** | Pi (1.88x faster subprocess throughput) |
| | Cold Start Latency | **0.013 s** | 0.014 s | **Turtle** |
| | Peak RAM (MB) | **103.3 MB** | 189.9 MB | **Turtle (1.84x lower RAM footprint)** |
| | Peak CPU (%) | **129.2 %** | 357.6 % | **Turtle (2.76x lower CPU utilization)** |
| **Fat Context** | State Serialization / Execution | **0.354 s** | 1.163 s | **Turtle (3.28x faster state parsing)** |
| | Cold Start Latency | 0.013 s | 0.013 s | Parity |
| | Peak RAM (MB) | **68.8 MB** | 190.2 MB | **Turtle (2.76x lower memory footprint)** |
| | Peak CPU (%) | **100.1 %** | 291.4 % | **Turtle (2.91x lower CPU utilization)** |

---

## Detailed Benchmark Logs

### Scenario: Firehose (`zero_latency`)
* **Turtle**: Throughput = 53,299 tokens/s | TTFR = 0.573 s | RAM = 227.0 MB | CPU = 115.4 %
* **Pi**: Throughput = 40,171 tokens/s | TTFR = 0.000 s | RAM = 184.8 MB | CPU = 322.6 %

### Scenario: Ping-Pong (`zero_latency`)
* **Turtle**: Tool Dispatch Latency = 6.368 s | RAM = 103.3 MB | CPU = 129.2 %
* **Pi**: Tool Dispatch Latency = 3.379 s | RAM = 189.9 MB | CPU = 357.6 %

### Scenario: Fat Context (`zero_latency`)
* **Turtle**: Parse & Serialization = 0.354 s | RAM = 68.8 MB | CPU = 100.1 %
* **Pi**: Parse & Serialization = 1.163 s | RAM = 190.2 MB | CPU = 291.4 %
