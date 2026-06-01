# ani-cli-ru

`ani-cli-ru` is a terminal tool to search, stream, and download anime releases from AniLibria.

- POSIX shell version: `ani-cli-ru`
- Windows PowerShell version: `ani-cli-ru.ps1` (with `ani-cli-ru.cmd` launcher)
- **GUI version**: `main.py` (Tkinter-based with multi-language dubbing support)

## Features

- Search anime by Russian or English names
- Built-in home UI (Search / Recommendations / History / Clear)
- Personalized recommendations (history + fresh/latest + random picks)
- **Multi-language dubbing support** (RU, EN, UK, TR + subtitles)
- Stream episodes with `mpv`, `VLC`, or `IINA`
- Download episodes with `aria2c`, `wget`, or PowerShell built-in downloader
- Bilingual UI: Russian (`ru`) and English (`en`)
- Episode selection (`-e`) and episode ranges (`-r`)
- Quality selection: `best`, `worst`, `360p`, `480p`, `720p`, `1080p`
- Watch history view and cleanup
- Works on Linux, macOS, WSL, and Windows PowerShell

## Dependencies

For POSIX script (`ani-cli-ru`):

- `sh` (POSIX shell)
- `curl`
- `jq`
- `fzf` (or `rofi`) for interactive menu
- Player: `mpv` or `vlc` (`iina` on macOS)

For Windows PowerShell script (`ani-cli-ru.ps1`):

- Windows PowerShell 5.1+ or PowerShell 7+
- Player: `mpv.exe` or `vlc.exe`
- Optional: `fzf` for interactive fuzzy selection

## Installation

```sh
git clone https://github.com/botir07/ani-cli-ru.git
cd ani-cli-ru
chmod +x ani-cli-ru
```

Optional system-wide install on Linux/macOS:

```sh
sudo install -m 0755 ani-cli-ru /usr/local/bin/ani-cli-ru
```

## How To Run

Linux/macOS/WSL:

```sh
./ani-cli-ru "attack on titan"
./ani-cli-ru -q 720p "code geass"
./ani-cli-ru -e 5 "demon slayer"
```

Windows PowerShell:

```powershell
.\ani-cli-ru.ps1 "Наруто"
.\ani-cli-ru.ps1 -q 720p "demon slayer"
.\ani-cli-ru.ps1 -e 5 "one piece"
```

Windows CMD launcher:

```bat
ani-cli-ru.cmd "naruto"
```

## GUI Application

The Tkinter-based GUI application (`main.py`) provides a visual interface with:

- **Multi-language dubbing selection**: Choose from Russian, English, Ukrainian, Turkish dubbing or subtitles
- **Smart recommendations**: History-based + latest + random picks
- **Episode selector**: Easy episode navigation with visual feedback
- **Dark mode**: Toggle between light and dark themes
- **Watch history**: Track and manage your viewing history

### Running the GUI

```sh
# From project directory
python main.py

# Or install as application
pip install requests
python -m ani_cli_ru  # if installed as package
```

### Local web UI

Install Python dependencies and start the Delegation dashboard:

```sh
pip install -r requirements.txt
python server.py
```

Then open the dashboard in your browser:

- `http://localhost:8000/`

The new UI launches a live AI company simulator with agent workflows, a Kanban board, real-time logs, artifact preview, and local model status powered by the only supported endpoint:

- `http://localhost:7352`

This dashboard automatically uses the local AI backend and does not require any external provider configuration.

### PSP browser support

Open the lightweight PSP page from a PSP 2000 browser on the same Wi-Fi:

- `http://<your-computer-ip>:8000/psp`

This page is rendered as plain HTML without JavaScript to work better on older PSP browsers.

### GUI Features

1. **Search Bar**: Enter anime title in Russian or English
2. **Language Selector**: Choose UI language (ru/en)
3. **Dubbing Selector**: Choose audio track:
   - Русский (AniLibria) - Russian dub from AniLibria
   - English (AniQit) - English dub
   - Українська (AniQit) - Ukrainian dub
   - Türkçe (AniQit) - Turkish dub
   - Русские субтитры - Russian subtitles
   - English subtitles - English subtitles
4. **Watch Mode**: Select playback method based on dubbing
5. **Episode Control**: Select specific episode to watch

If script execution is blocked in PowerShell:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Usage Examples

```sh
ani-cli-ru "атака титанов"
ani-cli-ru -d -r 1-3 "naruto"
ani-cli-ru --sub "your lie in april"
ani-cli-ru --recommend
```

PowerShell equivalents:

```powershell
.\ani-cli-ru.ps1 "атака титанов"
.\ani-cli-ru.ps1 -d -r 1-3 "naruto"
.\ani-cli-ru.ps1 --sub "your lie in april"
.\ani-cli-ru.ps1 --recommend
```

Language control:

```sh
ANI_CLI_LANG=ru ./ani-cli-ru "query"
ANI_CLI_LANG=en ./ani-cli-ru "query"
```

PowerShell language control:

```powershell
$env:ANI_CLI_LANG = "ru"; .\ani-cli-ru.ps1 "query"
$env:ANI_CLI_LANG = "en"; .\ani-cli-ru.ps1 "query"
```

## CLI Options

- `-h`, `--help`: Show help
- `-v`, `--version`: Show version
- `-q`, `--quality Q`: Set quality (`best|worst|360p|480p|720p|1080p`)
- `-d`, `--download`: Download mode
- `-e`, `--episode N`: Play/download one episode
- `-r`, `--range N-M`: Play/download episode range
- `-l`, `--logview`: View history
- `-D`, `--delete`: Clear history
- `--recommend`: Open recommendations directly
- `--lang ru|en`: Set UI language
- `--sub`: Request subtitles stream when available
- `--vlc`: Use VLC player
- `--rofi`: Use rofi menu instead of fzf (POSIX script)

## Environment Variables

- `ANI_CLI_LANG`: `ru` or `en`
- `ANI_CLI_PLAYER`: `mpv`, `vlc`, `iina`, `mpv.exe`, or `vlc.exe`
- `ANI_CLI_QUALITY`: default quality
- `ANI_CLI_STREAM_TYPE`: `dub` or `sub`
- `ANI_CLI_DOWNLOAD_DIR`: download path
- `ANI_CLI_HIST_DIR`: history directory
- `ANI_CLI_LOG`: history logging (`1` or `0`)
- `ANI_CLI_EXTERNAL_MENU`: `fzf` or `rofi`
- `ANI_CLI_API_BASE`: AniLibria API base URL
- `ANI_CLI_API_MODE`: `auto`, `v1`, or `v3`

## API Notes

AniLibria `v3` is deprecated on the old endpoint. This project defaults to:

- `https://api.anilibria.app/api/v1`

You can still force v3-compatible mode manually:

```sh
ANI_CLI_API_BASE="https://api.anilibria.tv/v3" ANI_CLI_API_MODE=v3 ./ani-cli-ru "query"
```

PowerShell equivalent:

```powershell
$env:ANI_CLI_API_BASE="https://api.anilibria.tv/v3"; $env:ANI_CLI_API_MODE="v3"; .\ani-cli-ru.ps1 "query"
```

## Development

See `hacking.md` for implementation details and workflow.

## Contributing

See `CONTRIBUTING.md`.

## License

GPL-3.0. See `LICENSE`.
