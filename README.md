<div align="center">

<!-- ══════════════════════════════════════════════════════════════════════════ -->
<!-- HERO BANNER -->
<!-- ══════════════════════════════════════════════════════════════════════════ -->

<img src="readme_assets/header-hero.svg" width="100%" alt="Security System Hero Banner"/>

<br/>

<!-- Quick Badges -->
<img src="https://img.shields.io/badge/Python-3.10+-00f0ff?style=for-the-badge&logo=python&logoColor=white"/>
<img src="https://img.shields.io/badge/YOLOv8-Detection-ff0080?style=for-the-badge&logo=yolo&logoColor=white"/>
<img src="https://img.shields.io/badge/PyQt6-GUI-6e40c9?style=for-the-badge&logo=qt&logoColor=white"/>
<img src="https://img.shields.io/badge/License-AGPL--3.0-00ff80?style=for-the-badge"/>

<br/><br/>

</div>

<img src="readme_assets/divider-cyber.svg" width="100%"/>

<br/>

<!-- ══════════════════════════════════════════════════════════════════════════ -->
<!-- OVERVIEW -->
<!-- ══════════════════════════════════════════════════════════════════════════ -->

<div align="center">
<img src="readme_assets/header-overview.svg" width="700" alt="Overview"/>
</div>

<br/>

> **Smart Security System** is an AI-powered surveillance solution built for real-time intrusion detection.  
> It combines **YOLOv8** object detection, **MediaPipe** skeleton tracking, **face recognition**, and **Telegram** remote control into a sleek PyQt6 dashboard.

<br/>

<table width="100%">
<tr>
<td width="50%" valign="top">

### ⚡ Core Capabilities
- Real-time **YOLOv8** person detection
- **Skeleton & partial-body** tracking via MediaPipe
- **Face recognition** with trusted-person allow-list
- **Multi-zone** breach detection with 3-D visualisation
- **Motion heat-map** overlay
- **Telegram bot** with inline-button controls
- **Text-to-speech** alerts & continuous alarm

</td>
<td width="50%" valign="top">

### 🎯 Use Cases
- Home & office surveillance
- Restricted-area monitoring
- Retail loss-prevention
- Research & prototyping
- Educational demonstrations

</td>
</tr>
</table>

<br/>

<img src="readme_assets/divider-cyber.svg" width="100%"/>

<br/>

<!-- ══════════════════════════════════════════════════════════════════════════ -->
<!-- FEATURES -->
<!-- ══════════════════════════════════════════════════════════════════════════ -->

<div align="center">
<img src="readme_assets/header-features.svg" width="700" alt="Features"/>
</div>

<br/>

<table width="100%">
<tr>
<td align="center" width="25%"><img src="readme_assets/icon-detection.svg" width="64"/><br/><strong>YOLOv8 Detection</strong><br/><sub>Accurate person tracking</sub></td>
<td align="center" width="25%"><img src="readme_assets/icon-zones.svg" width="64"/><br/><strong>Multi-Zone</strong><br/><sub>Draw custom polygons</sub></td>
<td align="center" width="25%"><img src="readme_assets/icon-alarm.svg" width="64"/><br/><strong>Continuous Alarm</strong><br/><sub>Audio + Telegram alerts</sub></td>
<td align="center" width="25%"><img src="readme_assets/icon-telegram.svg" width="64"/><br/><strong>Telegram Control</strong><br/><sub>Arm/disarm remotely</sub></td>
</tr>
<tr>
<td align="center"><img src="readme_assets/icon-face.svg" width="64"/><br/><strong>Face Recognition</strong><br/><sub>Trusted-person bypass</sub></td>
<td align="center"><img src="readme_assets/icon-motion.svg" width="64"/><br/><strong>Motion Heat-Map</strong><br/><sub>Visualise activity</sub></td>
<td align="center"><img src="readme_assets/icon-night.svg" width="64"/><br/><strong>Night Vision</strong><br/><sub>Low-light enhancement</sub></td>
<td align="center"><img src="readme_assets/icon-record.svg" width="64"/><br/><strong>Recording</strong><br/><sub>Manual & auto-record</sub></td>
</tr>
<tr>
<td align="center"><img src="readme_assets/icon-snapshot.svg" width="64"/><br/><strong>Snapshots</strong><br/><sub>Instant captures</sub></td>
<td align="center"><img src="readme_assets/icon-sensitivity.svg" width="64"/><br/><strong>Sensitivity</strong><br/><sub>Low / Med / High</sub></td>
<td align="center"><img src="readme_assets/icon-tts.svg" width="64"/><br/><strong>TTS Alerts</strong><br/><sub>Voice announcements</sub></td>
<td align="center"><img src="readme_assets/icon-video.svg" width="64"/><br/><strong>Video Playback</strong><br/><sub>Review recordings</sub></td>
</tr>
</table>

<br/>

<img src="readme_assets/divider-cyber.svg" width="100%"/>

<br/>

<!-- ══════════════════════════════════════════════════════════════════════════ -->
<!-- HOW IT WORKS -->
<!-- ══════════════════════════════════════════════════════════════════════════ -->

<div align="center">
<img src="readme_assets/header-howitworks.svg" width="700" alt="How It Works"/>
</div>

<br/>

<div align="center">
<img src="readme_assets/diagram-flow.svg" width="95%" alt="System Flow Diagram"/>
</div>

<br/>

| Step | Component | Description |
|:----:|-----------|-------------|
| 1 | **Camera / Video** | Captures frames at 30 FPS |
| 2 | **Detection Thread** | Runs YOLOv8 + MediaPipe in background |
| 3 | **Zone Check** | Tests skeleton landmarks against polygons |
| 4 | **Face Recognition** | Identifies trusted persons |
| 5 | **Alert Engine** | Triggers alarm, TTS, Telegram, snapshot |
| 6 | **GUI Render** | Overlays zones, heat-map, status |

<br/>

<img src="readme_assets/divider-cyber.svg" width="100%"/>

<br/>

<!-- ══════════════════════════════════════════════════════════════════════════ -->
<!-- INSTALLATION -->
<!-- ══════════════════════════════════════════════════════════════════════════ -->

<div align="center">
<img src="readme_assets/header-installation.svg" width="700" alt="Installation"/>
</div>

<br/>

```bash
# 1. Clone the repository
git clone https://github.com/Binivert/security-system.git
cd security-system

# 2. Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) Configure Telegram credentials in config.py
#    TELEGRAM_BOT_TOKEN = "your_token"
#    TELEGRAM_CHAT_ID   = "your_chat_id"
```

<br/>

<img src="readme_assets/divider-cyber.svg" width="100%"/>

<br/>

<!-- ══════════════════════════════════════════════════════════════════════════ -->
<!-- USAGE -->
<!-- ══════════════════════════════════════════════════════════════════════════ -->

<div align="center">
<img src="readme_assets/header-usage.svg" width="700" alt="Usage"/>
</div>

<br/>

```bash
python main.py
```

| Hotkey | Action |
|--------|--------|
| `A` | Toggle Arm / Disarm |
| `R` | Toggle Recording |
| `Space` | Take Snapshot |
| `F11` | Fullscreen |
| `Esc` | Exit Fullscreen |

**Telegram Commands** (inline buttons or text):

`/arm` · `/disarm` · `/snap` · `/record` · `/stoprecord` · `/mute` · `/unmute` · `/status` · `/stats` · `/log` · `/reload_faces` · `/sensitivity low|medium|high` · `/nightmode on|off`

<br/>

<img src="readme_assets/divider-cyber.svg" width="100%"/>

<br/>

<!-- ══════════════════════════════════════════════════════════════════════════ -->
<!-- FILE STRUCTURE -->
<!-- ══════════════════════════════════════════════════════════════════════════ -->

<div align="center">
<img src="readme_assets/header-filestructure.svg" width="700" alt="File Structure"/>
</div>

<br/>

<div align="center">
<img src="readme_assets/panel-filetree.svg" width="600" alt="File Tree"/>
</div>

<br/>

<details>
<summary><strong>📂 Expand full tree</strong></summary>

```
security-system/
├── main.py              # Entry point
├── gui.py               # PyQt6 main window
├── detectors.py         # YOLO, MediaPipe, face recognition
├── utils.py             # Zone & corner utilities
├── config.py            # Settings & paths
├── database.py          # SQLite event logging
├── telegram_bot.py      # Telegram integration
├── audio.py             # TTS & alarm
├── requirements.txt     # Python dependencies
├── LICENSE              # AGPL-3.0
├── README.md            # This file
└── readme_assets/       # SVG assets for README
```

</details>

<br/>

<img src="readme_assets/divider-cyber.svg" width="100%"/>

<br/>

<!-- ══════════════════════════════════════════════════════════════════════════ -->
<!-- DEMO -->
<!-- ══════════════════════════════════════════════════════════════════════════ -->

<div align="center">
<img src="readme_assets/header-demo.svg" width="700" alt="Demo"/>
</div>

<br/>

<div align="center">

<!-- Screenshot Placeholder -->
<img src="readme_assets/frame-demo.svg" width="80%" alt="Demo Placeholder"/>

<br/><br/>

*Replace the placeholder above with an actual screenshot or GIF.*

</div>

<br/>

<img src="readme_assets/divider-cyber.svg" width="100%"/>

<br/>

<!-- ══════════════════════════════════════════════════════════════════════════ -->
<!-- GITHUB STATS -->
<!-- ══════════════════════════════════════════════════════════════════════════ -->

<div align="center">
<img src="readme_assets/header-stats.svg" width="700" alt="Stats"/>
</div>

<br/>

<div align="center">
<img src="readme_assets/frame-stats.svg" width="90%" alt="Stats Frame"/>
</div>

<br/>

<div align="center">

<img src="https://github-readme-stats.vercel.app/api?username=Binivert&show_icons=true&theme=github_dark&hide_border=true&bg_color=0d1117&title_color=00f0ff&icon_color=ff0080&text_color=c9d1d9" height="160"/>
&nbsp;&nbsp;
<img src="https://github-readme-stats.vercel.app/api/top-langs/?username=Binivert&layout=compact&theme=github_dark&hide_border=true&bg_color=0d1117&title_color=00f0ff&text_color=c9d1d9" height="160"/>

</div>

<br/>

<img src="readme_assets/divider-cyber.svg" width="100%"/>

<br/>

<!-- ══════════════════════════════════════════════════════════════════════════ -->
<!-- LICENSE -->
<!-- ══════════════════════════════════════════════════════════════════════════ -->

<div align="center">
<img src="readme_assets/header-license.svg" width="700" alt="License"/>
</div>

<br/>

```
Copyright © 2024 Binivert

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
```

<br/>

<img src="readme_assets/divider-cyber.svg" width="100%"/>

<br/>

<div align="center">
<img src="readme_assets/footer.svg" width="100%" alt="Footer"/>
</div>
