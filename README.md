<!-- back to top anchor -->
<a id="readme-top"></a>

<!-- PROJECT SHIELDS -->
[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![Apache License][license-shield]][license-url]

<!-- PROJECT LOGO -->
<br />
<div align="center">
  <a href="https://github.com/rodrigoazlima/ollama-tray">
    <img src="assets/ollama-icon.png" alt="Ollama Logo" width="120" height="120">
  </a>

  <h3 align="center">ollama-tray</h3>

  <p align="center">
    Windows system tray manager for the Ollama service — start, stop, and monitor without opening a terminal.
    <br />
    <a href="https://github.com/rodrigoazlima/ollama-tray"><strong>Explore the docs »</strong></a>
    <br />
    <br />
    <a href="https://github.com/rodrigoazlima/ollama-tray/issues/new?labels=bug&template=bug-report---.md">Report Bug</a>
    &middot;
    <a href="https://github.com/rodrigoazlima/ollama-tray/issues/new?labels=enhancement&template=feature-request---.md">Request Feature</a>
  </p>
</div>

<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#configuration">Configuration</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>

<!-- ABOUT THE PROJECT -->
## About The Project

**ollama-tray** puts Ollama service control in your Windows system tray. No terminal needed — right-click to start/stop/restart, double-click for a live resource monitor, and the icon tells you at a glance whether the service is up.

Why:
* The Ollama Windows service has no native tray UI
* Opening Services MMC or a terminal just to restart a model server is friction
* A colour-coded icon + one-second live stats removes all of that friction

**Platform:** Windows 10/11 only — uses `win32service` and `winreg` directly (zero subprocess/CMD flashes).

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Built With

[![Python][python-shield]][python-url]
[![pystray][pystray-shield]][pystray-url]
[![Pillow][pillow-shield]][pillow-url]
[![pywin32][pywin32-shield]][pywin32-url]
[![psutil][psutil-shield]][psutil-url]
[![PyInstaller][pyinstaller-shield]][pyinstaller-url]

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- GETTING STARTED -->
## Getting Started

### Prerequisites

* Windows 10/11
* Python 3.10 or newer
* [Ollama for Windows](https://ollama.com/download/windows) installed — the installer registers the `Ollama` Windows service automatically

### Installation

#### Option A — run from source

1. Clone the repo
   ```sh
   git clone https://github.com/rodrigoazlima/ollama-tray.git
   cd ollama-tray
   ```

2. Install dependencies and register autostart
   ```powershell
   .\windows\install.ps1
   ```

3. Start the tray immediately (no reboot needed)
   ```sh
   python -m ollama_tray
   ```

#### Option B — install as Python package

```sh
pip install .
ollama-tray
```

#### Option C — standalone exe (no Python required at runtime)

```powershell
pip install pyinstaller
.\windows\build.ps1
# output: dist\ollama-tray.exe

dist\ollama-tray.exe --install   # register autostart
dist\ollama-tray.exe             # run now
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- USAGE -->
## Usage

[![Tray App Preview][preview-screenshot]](https://github.com/rodrigoazlima/ollama-tray)

**Tray icon colours**

| Colour | Meaning |
|--------|---------|
| Green  | Service running |
| Red    | Service stopped |
| Amber  | Starting / stopping / unknown |

**Right-click menu** — shows live `CPU% · RAM` updated every second, plus Start / Stop / Restart / Open in Browser / Exit.

**Double-click** — opens the resource monitor dialog. Double-click again (or close the window) to dismiss.

**Resource monitor dialog**

| Field | Detail |
|-------|--------|
| Per-process table | name, PID, CPU%, RSS |
| Aggregate totals | CPU%, RSS, VMS, threads, handles, uptime |

Color coding: green < 30% CPU / < 2 GB RAM · amber < 70% / < 6 GB · red above. Refreshes every second.

**CLI flags**

```sh
python -m ollama_tray              # launch tray (default)
python -m ollama_tray --status     # print service status (exit 0 = running)
python -m ollama_tray --start      # start service  (UAC prompt if needed)
python -m ollama_tray --stop       # stop service   (UAC prompt if needed)
python -m ollama_tray --restart    # stop → 2 s delay → start
python -m ollama_tray --install    # register HKCU Run key autostart
python -m ollama_tray --uninstall  # remove HKCU Run key autostart
```

**Autostart options**

```powershell
.\windows\install.ps1                      # install deps + register autostart
.\windows\install.ps1 -NoDeps              # skip pip, just register
.\windows\install.ps1 -Python "python3"    # specify Python executable
.\windows\install.ps1 -Uninstall           # remove autostart
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- CONFIGURATION -->
## Configuration

`config.properties` is created automatically on first run. Location:

| Platform | Path |
|----------|------|
| Windows  | `%APPDATA%\OllamaTray\config.properties` |
| Linux    | `~/.config/ollama-tray/config.properties` |

Edit the file and restart the tray to apply changes. All keys are optional — omit any key to use the default.

**Key settings**

| Key | Default | Description |
|-----|---------|-------------|
| `ollama_url` | `http://localhost:11434` | Ollama HTTP API base URL |
| `ui_theme` | `dark` | Tray dialog theme: `dark` \| `light` \| `black` |
| `stats_interval` | `1` | Seconds between CPU/RAM stat refreshes |
| `ollama_num_gpu` | *(blank)* | GPU layers to offload — blank = Ollama auto-detects; `0` = CPU-only |
| `ollama_kv_cache_type` | `f16` | KV cache precision: `f16` \| `q8_0` \| `q4_0` |
| `ollama_flash_attention` | `0` | Flash Attention for long-context: `0` \| `1` |
| `ollama_num_parallel` | `1` | Concurrent inference requests |
| `ollama_max_loaded_models` | `1` | Models kept in VRAM simultaneously |
| `hsa_enable_sdma` | *(blank)* | AMD RDNA3 only — set to `0` to disable SDMA (+5–15% throughput) |

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- ROADMAP -->
## Roadmap

- [x] Service start / stop / restart from tray
- [x] Live CPU / RAM monitor dialog (1 s refresh)
- [x] UAC auto-elevation when admin access required
- [x] HKCU autostart registration (no admin needed)
- [x] Standalone exe build via PyInstaller
- [ ] Windows toast notifications on service state change
- [ ] Dark / light icon theme option
- [ ] Running model list via Ollama REST API
- [ ] GPU VRAM usage via NVML / ROCm

See the [open issues](https://github.com/rodrigoazlima/ollama-tray/issues) for proposed features and known issues.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- CONTRIBUTING -->
## Contributing

Contributions are welcome and greatly appreciated.

If you have a suggestion, fork the repo and open a pull request, or open an issue tagged `enhancement`.

1. Fork the project
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a pull request

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- LICENSE -->
## License

Distributed under the Apache 2.0 License. See [`LICENSE`](LICENSE) for more information.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- CONTACT -->
## Contact

Rodrigo Lima - [@rodrigoazlima](https://github.com/rodrigoazlima) - rodrigoazlima@gmail.com

Project Link: [https://github.com/rodrigoazlima/ollama-tray](https://github.com/rodrigoazlima/ollama-tray)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- ACKNOWLEDGMENTS -->
## Acknowledgments

* [Ollama](https://ollama.com) — the service this tool wraps
* [pystray](https://github.com/moses-palmer/pystray) — system tray icon and menu
* [Pillow](https://python-pillow.org) — icon rendering
* [pywin32](https://github.com/mhammond/pywin32) — Windows SCM service control
* [psutil](https://github.com/giampaolo/psutil) — cross-platform process/resource stats
* [PyInstaller](https://pyinstaller.org) — standalone exe bundler
* [Best-README-Template](https://github.com/othneildrew/Best-README-Template) — README structure

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- MARKDOWN LINKS & IMAGES -->
[contributors-shield]: https://img.shields.io/github/contributors/rodrigoazlima/ollama-tray.svg?style=for-the-badge
[contributors-url]: https://github.com/rodrigoazlima/ollama-tray/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/rodrigoazlima/ollama-tray.svg?style=for-the-badge
[forks-url]: https://github.com/rodrigoazlima/ollama-tray/network/members
[stars-shield]: https://img.shields.io/github/stars/rodrigoazlima/ollama-tray.svg?style=for-the-badge
[stars-url]: https://github.com/rodrigoazlima/ollama-tray/stargazers
[issues-shield]: https://img.shields.io/github/issues/rodrigoazlima/ollama-tray.svg?style=for-the-badge
[issues-url]: https://github.com/rodrigoazlima/ollama-tray/issues
[license-shield]: https://img.shields.io/github/license/rodrigoazlima/ollama-tray.svg?style=for-the-badge
[license-url]: https://github.com/rodrigoazlima/ollama-tray/blob/master/LICENSE

[preview-screenshot]: assets/preview.png

[python-shield]: https://img.shields.io/badge/Python_3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white
[python-url]: https://python.org
[pystray-shield]: https://img.shields.io/badge/pystray-0.19+-grey?style=for-the-badge
[pystray-url]: https://github.com/moses-palmer/pystray
[pillow-shield]: https://img.shields.io/badge/Pillow-10+-grey?style=for-the-badge
[pillow-url]: https://python-pillow.org
[pywin32-shield]: https://img.shields.io/badge/pywin32-306+-0078D4?style=for-the-badge&logo=windows&logoColor=white
[pywin32-url]: https://github.com/mhammond/pywin32
[psutil-shield]: https://img.shields.io/badge/psutil-5.9+-grey?style=for-the-badge
[psutil-url]: https://github.com/giampaolo/psutil
[pyinstaller-shield]: https://img.shields.io/badge/PyInstaller-grey?style=for-the-badge
[pyinstaller-url]: https://pyinstaller.org
