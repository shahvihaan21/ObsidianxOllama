"""Benchmark script for LLM performance."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.ollama_client import OllamaClient, ChatMessage

def main():
    print("Benchmarking qwen3:1.7b...")
    client = OllamaClient(model="qwen3:1.7b")
    
    if not client.is_available():
        print("Ollama server not available.")
        return
        
    print("Loading model...")
    t0 = time.time()
    try:
        client.preload()
    except Exception as e:
        print(f"Error loading model: {e}")
        return
    load_time = time.time() - t0
    print(f"Model loaded in {load_time:.2f}s")
    
    print("Testing response time and tokens/sec...")
    t0 = time.time()
    resp = client.chat([ChatMessage.user("Write a short paragraph about the history of computing.")])
    total_time = time.time() - t0
    
    print(f"Total time: {total_time:.2f}s")
    print(f"Tokens/sec: {resp.tokens_per_second:.2f}")
    
    print("\nBenchmark complete.")

if __name__ == "__main__":
    main()
