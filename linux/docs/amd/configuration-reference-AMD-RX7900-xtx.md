# Configuration Reference

Hardware: RX 7900 XTX (24 GB VRAM) · Ryzen 9 9900X · 128 GB DDR5 · Windows 11 Pro  
Build: llama.cpp b8407 · ROCm 7.2.1 (bundled DLLs)

---

## Model

| Field | Value |
|-------|-------|
| Name | Qwen3-Coder-30B-A3B-Instruct |
| Quantization | Q4_K_M |
| File | `Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf` |
| Path | `D:\opt\models\lmstudio\lmstudio-community\Qwen3-Coder-30B-A3B-Instruct-GGUF\` |
| Size on disk | ~17.35 GiB |
| Measured VRAM (weights only) | ~16.25 GB |
| Architecture | Qwen3 MoE (Mixture-of-Experts) |
| Layers | 28 transformer layers |
| KV heads (GQA) | 8 |
| Head dimension | 128 |

### KV Cache Formula

```
elements_per_token = 2 (K+V) × 8 (kv_heads) × 128 (head_dim) × 28 (layers) = 57,344
VRAM_KV = elements_per_token × bytes_per_element × context_tokens

bytes_per_element:
  f16  → 2.0 bytes  (default, lossless)
  q8_0 → 1.0 byte   (near-lossless, 2× context vs f16)
  q4_0 → 0.5 bytes  (4× context vs f16, small quality loss)
```

| KV type | 640 tok | 8K tok | 32K tok | 131K tok | 262K tok |
|---------|--------:|-------:|--------:|---------:|---------:|
| f16     | 0.07 GB | 0.86 GB | 3.4 GB  | 13.6 GB  | 27.2 GB  |
| q8_0    | 0.03 GB | 0.43 GB | 1.7 GB  |  6.8 GB  | 13.6 GB  |
| q4_0    | 0.02 GB | 0.21 GB | 0.85 GB |  3.4 GB  |  6.8 GB  |

**Total VRAM = 16.25 GB (weights) + KV cache**

---

## Environment Variables

| Variable | Value | Scope | Effect |
|----------|-------|-------|--------|
| `HSA_ENABLE_SDMA` | `0` | Process | Disables DMA engine on RDNA3, +5–15% throughput |
| `PATH` | prepended with llama dir | Process | Loads bundled ROCm 7.2.1 DLLs |

---

## llama.cpp Binary Paths

```
Binaries : C:\opt\llama-hip-amd721\llama-b8407-windows-rocm-7.2.1-gfx110X-gfx115X-gfx120X-x64\
Server   : llama-server.exe
Bench    : llama-bench.exe
```

---

## Launch Configurations

### `launch_baseline.ps1` — Full GPU, default KV, mmap off

```
Script: win\scripts\launch_baseline.ps1
```

| Parameter | Value | Notes |
|-----------|-------|-------|
| `--model` / `-m` | `...Q4_K_M.gguf` | Model path |
| `--n-gpu-layers` | `41` | All layers on GPU |
| `-c` (context) | `32768` | 32K tokens |
| `--port` | `8081` | HTTP API port |
| `--verbose` | on | Verbose logging |
| `--no-mmap` | off | mmap enabled (default) |
| `--flash-attn` | off | not set |
| KV type | f16 (default) | Lossless, ~3.4 GB at 32K ctx |
| **Est. VRAM** | **~19.7 GB** | weights 16.25 + KV 3.4 |
| **Best for** | Speed on 24 GB | 1228 pp t/s · 61.8 tg t/s |

CLI equivalent:
```powershell
llama-server.exe -m <model> --n-gpu-layers 41 -c 32768 --port 8081 --verbose
```

---

### `launch_optimized.ps1` — MoE CPU offload, f16 KV, 262K context

```
Script: win\scripts\launch_optimized.ps1
```

| Parameter | Value | Notes |
|-----------|-------|-------|
| `--model` / `-m` | `...Q4_K_M.gguf` | Model path |
| `--n-gpu-layers` | `41` | All transformer layers on GPU |
| `--n-cpu-moe` | `35` | Offload expert weights of first 35 MoE layers to CPU RAM |
| `--cache-type-k` | `f16` | Key cache type (lossless) |
| `--cache-type-v` | `f16` | Value cache type (lossless) |
| `--no-mmap` | on | Load entire model into RAM upfront |
| `--mlock` | on | Pin model in RAM, prevent OS paging |
| `-c` (context) | `262144` | 262K token context window |
| `--port` | `8081` | HTTP API port |
| `--verbose` | on | Verbose logging |
| **Est. VRAM** | **varies** | KV at 262K f16 = 27.2 GB — exceeds 24 GB; MoE offload reduces pressure |
| **Best for** | Max context on 24 GB | 843 pp t/s · 27.7 tg t/s (penalty for PCIe MoE traffic) |

> **Note:** `--n-cpu-moe` offloads MoE expert matrices to system RAM. Reduces VRAM by several GB at the cost of PCIe bandwidth per token. Only beneficial when model + KV does not fit in VRAM. At 262K context with f16 KV (~27 GB), this is required on a 24 GB card.

CLI equivalent:
```powershell
llama-server.exe -m <model> --n-gpu-layers 41 --n-cpu-moe 35 `
    --cache-type-k f16 --cache-type-v f16 --no-mmap --mlock `
    -c 262144 --port 8081 --verbose
```

---

### `launch_highctx.ps1` — Full GPU, q4_0 KV, 128K context

```
Script: win\scripts\launch_highctx.ps1
```

| Parameter | Value | Notes |
|-----------|-------|-------|
| `--model` / `-m` | `...Q4_K_M.gguf` | Model path |
| `--n-gpu-layers` | `41` | All layers on GPU — no CPU MoE offload |
| `--cache-type-k` | `q4_0` (or `turbo4`) | Key cache, 4× VRAM savings vs f16 |
| `--cache-type-v` | `q4_0` (or `turbo3`) | Value cache |
| `--flash-attn` | on | Flash Attention — required at long context |
| `--no-mmap` | on | Load model into RAM upfront |
| `--mlock` | on | Pin RAM, prevent paging |
| `-c` (context) | `131072` | 128K tokens |
| `--port` | `8081` | HTTP API port |
| `--verbose` | on | Verbose logging |
| `-TurboQuant` (flag) | optional | Use `turbo4`/`turbo3` KV if build supports it |
| **Est. VRAM** | **~19.7 GB** | weights 16.25 + q4_0 KV at 128K = 3.4 GB |
| **Best for** | Long sessions on 24 GB | Full VRAM speed + 128K context |

CLI equivalent:
```powershell
llama-server.exe -m <model> --n-gpu-layers 41 `
    --cache-type-k q4_0 --cache-type-v q4_0 --flash-attn `
    --no-mmap --mlock -c 131072 --port 8081 --verbose
```

---

## Parameter Reference

| Flag | Description |
|------|-------------|
| `-m` / `--model` | Path to GGUF model file |
| `--n-gpu-layers N` | Layers offloaded to GPU. Set to total layer count (41) for full GPU inference |
| `--n-cpu-moe N` | Offload MoE expert matrices of first N layers to CPU RAM. Reduces VRAM at PCIe bandwidth cost. Only use when VRAM insufficient |
| `--cache-type-k TYPE` | KV cache quantization for keys: `f16` (lossless), `q8_0` (near-lossless), `q4_0` (4× compression) |
| `--cache-type-v TYPE` | KV cache quantization for values: same options as above |
| `--flash-attn` / `-fa` | Enable Flash Attention. Required for stable long-context inference. Reduces VRAM for attention computation |
| `--no-mmap` | Load full model into RAM before serving. Eliminates page-fault latency during inference. Increases startup time |
| `--mlock` | Lock model pages in RAM. Prevents OS from swapping under memory pressure |
| `-c N` | Context window size in tokens. KV cache VRAM scales linearly with this value |
| `--port N` | HTTP server port (default 8080, scripts use 8081) |
| `--verbose` | Log per-layer load info and inference timings |
| `HSA_ENABLE_SDMA=0` | AMD env var. Disables SDMA (DMA engine) on RDNA3. Routes GPU memory ops through shader engine instead. Consistent +5–15% throughput |

---

## VRAM Budget by Config

| Config | Model | KV Cache | Total Est. | Headroom (24 GB) |
|--------|------:|--------:|----------:|----------------:|
| baseline (32K, f16 KV) | 16.25 GB | 3.40 GB | **19.65 GB** | 4.35 GB |
| highctx (128K, q4_0 KV) | 16.25 GB | 3.40 GB | **19.65 GB** | 4.35 GB |
| q8kv (640 tok, q8_0 KV) | 16.25 GB | 0.03 GB | **16.28 GB** | 7.72 GB |
| maxvram (32K, f16 KV) | 16.25 GB | 3.57 GB | **19.82 GB** | 4.18 GB |
| optimized (262K, f16 KV) | varies* | 27.2 GB | **>24 GB** | requires MoE offload |
| optimized (262K, q4_0 KV) | varies* | 6.80 GB | **~23.05 GB** | 0.95 GB |

*MoE offload moves expert matrices to RAM, freeing several GB of VRAM.

---

## Ollama Service (install_ollama_service.ps1)

Separate from llama.cpp — runs Ollama's own inference engine as a Windows background service via NSSM.

### Service Configuration

| Parameter | Value |
|-----------|-------|
| Service name | `Ollama` |
| Display name | `Ollama LLM Service` |
| Manager | NSSM (`C:\tools\nssm\nssm.exe`) |
| Startup type | `SERVICE_AUTO_START` |
| Binary | `ollama.exe serve` (auto-detected) |
| Log directory | `C:\ProgramData\Ollama\logs\` |
| Log rotation | Daily (86400 s), online rotation enabled |

### Ollama Environment Variables (set in service)

| Variable | Value | Scope |
|----------|-------|-------|
| `OLLAMA_HOST` | `0.0.0.0:11434` | Service env (all interfaces) |
| `OLLAMA_MODELS` | `D:\opt\models\ollama` | Machine-wide + service env |

> `OLLAMA_MODELS` is written to `HKLM` (machine-wide) so CLI commands (`ollama list`, `ollama run`) see the same model directory as the service.

### Ollama Endpoints

| Endpoint | URL |
|----------|-----|
| API base | `http://localhost:11434` |
| Model list | `http://localhost:11434/api/tags` |

### Service Log Files

```
C:\ProgramData\Ollama\logs\ollama.log       (stdout)
C:\ProgramData\Ollama\logs\ollama-err.log   (stderr)
```

---

## Ollama Tray App (win\tray-app\)

Tray icon manager for the Ollama Windows service — no separate inference; monitors and controls the service above.

### Autostart Registration

| Method | Location |
|--------|----------|
| HKCU Run key | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\OllamaTray` |
| Value | `"<python.exe>" "<path>\ollama_tray.py"` |
| Admin required | No |

### Tray App Constants

| Constant | Value | Notes |
|----------|-------|-------|
| `SERVICE_NAME` | `Ollama` | Windows SCM service controlled |
| `OLLAMA_URL` | `http://localhost:11434` | Health/API URL polled |
| `STATS_INTERVAL` | 1 s | Resource stats + menu refresh |
| `STATUS_INTERVAL` | 5 ticks (5 s) | Service status re-check |
| `TOGGLE_DEBOUNCE_S` | 0.6 s | Min gap between open/close resource dialog |
| `ICON_SIZE` | 64 px | Tray icon canvas |

### Icon Status Colors

| State | Color | RGB |
|-------|-------|-----|
| running | green | (72, 199, 116) |
| stopped | red | (220, 53, 69) |
| starting / stopping / unknown | amber | (255, 193, 7) |

### Python Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `pystray` | ≥ 0.19 | Tray icon + menu |
| `Pillow` | ≥ 10.0 | Icon rendering |
| `pywin32` | ≥ 306 | SCM service control |
| `psutil` | ≥ 5.9 | Process/resource stats |

---

## Benchmark Parameters

### `benchmark.ps1`

| Parameter | Default | Options |
|-----------|---------|---------|
| `-Config` | `both` | `baseline`, `optimized`, `kv-only`, `q8kv`, `highctx`, `largectx`, `maxvram`, `ubatch`, `all`, `server` |
| `-Repetitions` | 3 | — |
| `-NPrompt` | 512 tokens | — |
| `-NGen` | 128 tokens | — |

### `benchmark262k.ps1`

| Parameter | Default | Notes |
|-----------|---------|-------|
| `-Config` | `ladder` | `ladder`, `ubatch`, `stress`, `all` |
| `-Repetitions` | 2 | Auto-reduced to 1 for pp ≥ 128K |
| `-NGen` | 128 | Auto-reduced to 32 for pp ≥ 64K |
| `-Force` | off | Bypass VRAM guard (> 23.25 GB est.) |
| `-SkipPromptSizes` | — | e.g. `"262016","131072"` |
| `-SkipContextSizes` | — | e.g. `"131072","65536"` |

#### VRAM Guards (262k bench)

| Threshold | Action |
|-----------|--------|
| ≥ 23.25 GB est. | Warn + require `-Force` |
| ≥ 23.8 GB est. | Hard block (likely OOM) |

---

## Benchmark Results (RX 7900 XTX)

| Config | pp t/s | tg t/s | VRAM est. | Context |
|--------|-------:|-------:|----------:|--------:|
| Baseline (GPU full, f16 KV, mmap, FA) | **1228** | **61.8** | ~17.4 GB | 640 tok |
| KV-quant only (q4_0 KV, no-mmap, FA) | **1496** | **60.5** | ~17.4 GB | 640 tok |
| q8kv (q8_0 KV, no-mmap, FA) | **1508** | **63.3** | ~17.4 GB | 640 tok |
| Optimized (MoE CPU offload, q4_0 KV) | 843 | 27.7 | ~17.4 GB | 640 tok |

> `no-mmap + q4_0/q8_0 KV` consistently beats mmap baseline. `MoE CPU offload` hurts performance on 24 GB — only enables larger context, not speed.

---

*Generated: 2026-06-23 · Source: `win/scripts/` + `win/tray-app/`*
