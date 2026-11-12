# Codex Voice Control

[Polski](README.pl.md)

![Layered blue and violet voice waveform](assets/voice-wave.png)

**Keep Codex voice within reach without keeping a voice chat open all day.**

Codex Voice Control is an independent Windows companion built to help you conserve your Codex usage allowance. It listens locally for your chosen phrases, so you can open a voice chat when you need it and close it with a spoken command. Desktop voice is billed by time from the same usage budget as Codex tasks. Keeping the connection closed between conversations reduces the time spent in voice. The model that handles your work has its own token rates. [OpenAI usage and pricing](https://learn.chatgpt.com/docs/pricing#how-much-does-voice-cost)

## Talk when you need to

- **Your phrases, your language.** Set several phrases to start and end a voice chat. Choose the interface language and speech recognition language separately.
- **The chat you want.** Use your most recently opened chat or pick a specific conversation.
- **A waveform you can click through.** The thin overlay responds to voice activity and leaves the controls underneath accessible.
- **Distinct sound cues.** Choose sounds for connection, disconnection and finished replies. Optional MCP notifications can tell you when a background task is ready.

## Automatic readback

**Automatic readback is enabled by default.** When Codex starts working on a spoken request, Codex Voice Control disconnects voice while Codex continues the task. When the answer is ready, the app reconnects in the same chat and asks Codex to read the answer aloud again.

Turn it off in **Settings → Target chat**. Your stop phrase also cancels a pending reconnection. Automatic readback supports the English and Polish Codex desktop interfaces.

## Getting started

1. Download the **Windows x64 installer** from [Beta 2](https://github.com/AlphaStudioDE/codex-voice-control/releases/tag/v0.1.0-beta.2). You need a microphone and the Codex desktop app with voice chat available on your account.
2. Open **Codex Voice Control** from the desktop shortcut. In the system tray, open **Settings**, choose your phrases and enable listening.
3. Say your start phrase and wait for the connection cue. Say your stop phrase when you finish. For the Polish defaults, use **“Friday, jesteś?”** and **“bez odbioru”**.

The installer includes the local speech model. The panel opens after installation and starts again at Windows sign-in.

## Beta status

We verified that a Windows scheduled task can open the selected Codex chat without a Codex entry in `PATH`. The desktop app must expose voice chat in that conversation for the spoken start phrase to connect.

Codex Voice Control is an independent AlphaStudioDE project.

[MIT License](LICENSE) · [Third-party notices and source](THIRD_PARTY_NOTICES.md)

## Develop from source

The application code is in [app/](app/) and is available under the [MIT License](LICENSE). Issues and pull requests are welcome. For bug reports, include the Windows and Codex versions, reproduction steps and any relevant logs with private details removed.

On Windows x64 with `uv` installed, open PowerShell in the repository and run:

```powershell
cd app
.\Przygotuj.cmd
.\.venv\Scripts\pythonw.exe .\windowed.pyw panel
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Setup installs the Python dependencies and downloads the local speech model. The panel opens in the Windows system tray. For packaging prerequisites and commands, see [Building the installer](BUILD.md).
