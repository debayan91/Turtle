import argparse
import subprocess
import time
import os
import pty
import sys
import json
import threading
import psutil
from rich.console import Console
from rich.table import Table
import select

def write_state(scenario, mode):
    with open("/tmp/judge_state.json", "w") as f:
        json.dump({"scenario": scenario, "mode": mode}, f)

def monitor_process(pid, stop_event, results):
    results["max_rss"] = 0
    results["max_cpu"] = 0
    
    try:
        process = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return

    while not stop_event.is_set():
        try:
            with process.oneshot():
                rss = process.memory_info().rss / (1024 * 1024)
                cpu = process.cpu_percent(interval=None)
                
                if rss > results["max_rss"]:
                    results["max_rss"] = rss
                if cpu > results["max_cpu"]:
                    results["max_cpu"] = cpu
                    
            for child in process.children(recursive=True):
                with child.oneshot():
                    child_rss = child.memory_info().rss / (1024 * 1024)
                    child_cpu = child.cpu_percent(interval=None)
                    if child_rss > results["max_rss"]:
                        results["max_rss"] = child_rss
                    if child_cpu > results["max_cpu"]:
                        results["max_cpu"] = child_cpu

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        
        time.sleep(0.01)

def run_benchmark(target, scenario, mode, output_dir=None):
    console = Console()
    write_state(scenario, mode)
    
    server_env = os.environ.copy()
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server:app", "--port", "8000"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=server_env
    )
    
    console.print("Waiting for mock server to start...")
    time.sleep(2) 
    
    if os.path.exists("/tmp/judge_ttfr_start.txt"):
        os.remove("/tmp/judge_ttfr_start.txt")

    # Target executable path resolution
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    commands = {
        "turtle": [sys.executable, "-m", "turtle_agent"],
        "pi": ["node", "pi/packages/coding-agent/dist/cli.js"] 
    }
    
    if target not in commands:
        cmd = target.split()
    else:
        cmd = commands[target]
        
    env = os.environ.copy()
    env["OPENAI_BASE_URL"] = "http://localhost:8000/v1"
    env["OPENAI_API_KEY"] = "mock_key"
    
    master, slave = pty.openpty()
    
    start_time = time.perf_counter()
    
    harness = subprocess.Popen(
        cmd,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=env,
        cwd=repo_root
    )
    
    os.close(slave)
    
    stop_event = threading.Event()
    mon_results = {"max_rss": 0, "max_cpu": 0}
    mon_thread = threading.Thread(target=monitor_process, args=(harness.pid, stop_event, mon_results))
    mon_thread.start()
    
    output = b""
    first_output_time = None
    ttfr_rendered_time = None
    
    prompt = f"run {scenario} test\n"
    os.write(master, prompt.encode())
    
    # To detect when it finishes, we will use a timeout of 1 second of silence, 
    # except we need to wait for the first output to appear.
    last_output_time = time.perf_counter()
    while True:
        r, _, _ = select.select([master], [], [], 0.1)
        if master in r:
            try:
                data = os.read(master, 1024)
            except OSError:
                break
            if not data:
                break
            
            current_time = time.perf_counter()
            if not first_output_time:
                first_output_time = current_time
            
            # If server wrote the ttfr start time, the next output might be the stream chunk rendering
            if os.path.exists("/tmp/judge_ttfr_start.txt") and not ttfr_rendered_time:
                ttfr_rendered_time = current_time
                
            output += data
            last_output_time = current_time
        else:
            # 2 seconds of silence -> assume done
            if output and (time.perf_counter() - last_output_time > 2.0):
                break
            # If it takes > 20s overall, also break to avoid hanging
            if time.perf_counter() - start_time > 20.0:
                break
            
    end_time = last_output_time # The time of the last chunk received
    
    ttfr_start = None
    if os.path.exists("/tmp/judge_ttfr_start.txt"):
        with open("/tmp/judge_ttfr_start.txt", "r") as f:
            try:
                ttfr_start = float(f.read().strip())
            except ValueError:
                pass
                
    harness.terminate()
    stop_event.set()
    mon_thread.join()
    server_process.terminate()
    
    cold_start = (first_output_time - start_time) if first_output_time else 0
    total_time = end_time - start_time
    ttfr = (ttfr_rendered_time - ttfr_start) if (ttfr_start and ttfr_rendered_time and ttfr_rendered_time > ttfr_start) else 0
    throughput = 50000 / total_time if scenario == "firehose" and total_time > 0 else 0
    
    metrics = {
        "target": target,
        "scenario": scenario,
        "mode": mode,
        "cold_start_latency_s": round(cold_start, 3),
        "ttfr_overhead_s": round(ttfr, 3),
        "stream_throughput_tokens_per_sec": round(throughput, 0),
        "tool_dispatch_subprocess_latency_s": round(total_time, 3),
        "state_serialization_overhead_s": round(total_time, 3),
        "peak_ram_mb": round(mon_results['max_rss'], 1),
        "peak_cpu_percent": round(mon_results['max_cpu'], 1)
    }
    
    table = Table(title=f"Judge Results: {target} ({scenario}) - Mode: {mode}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="magenta")
    
    table.add_row("Cold Start Latency (s)", f"{cold_start:.3f}")
    if scenario in ["firehose", "ping_pong"]:
        table.add_row("TTFR Overhead (s)", f"{ttfr:.3f}")
    if scenario == "firehose":
        table.add_row("Stream Throughput (tokens/s)", f"{throughput:.0f}")
    table.add_row("Tool Dispatch & Subprocess Latency (s)", f"{total_time:.3f}")
    table.add_row("State Serialization Overhead (s)", f"{total_time:.3f}")
    table.add_row("Peak RAM (MB)", f"{mon_results['max_rss']:.1f}")
    table.add_row("Peak CPU (%)", f"{mon_results['max_cpu']:.1f}")

    console.print(table)

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        json_path = os.path.join(output_dir, f"{target}_{scenario}_{mode}.json")
        with open(json_path, "w") as f:
            json.dump(metrics, f, indent=2)
            
        md_path = os.path.join(output_dir, "results_summary.md")
        with open(md_path, "a") as f:
            f.write(f"### Benchmark: {target} | Scenario: {scenario} | Mode: {mode}\n\n")
            f.write(f"- Cold Start Latency: {cold_start:.3f} s\n")
            f.write(f"- TTFR Overhead: {ttfr:.3f} s\n")
            if scenario == "firehose":
                f.write(f"- Stream Throughput: {throughput:.0f} tokens/s\n")
            f.write(f"- Peak RAM: {mon_results['max_rss']:.1f} MB\n")
            f.write(f"- Peak CPU: {mon_results['max_cpu']:.1f} %\n\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="turtle")
    parser.add_argument("--scenario", default="firehose")
    parser.add_argument("--mode", default="zero_latency")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()
    
    run_benchmark(args.target, args.scenario, args.mode, output_dir=args.output_dir)
