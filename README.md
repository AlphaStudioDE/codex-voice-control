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

## Getting started

1. Download the **Windows x64 installer** from [Beta 1](https://github.com/AlphaStudioDE/codex-voice-control/releases/tag/v0.1.0-beta.1). You need a microphone and the Codex desktop app with voice chat available on your account.
2. Open **Codex Voice Control** from the desktop shortcut. In the system tray, open **Settings**, choose your phrases and enable listening.
3. Say your start phrase and wait for the connection cue. Say your stop phrase when you finish. For the Polish defaults, use **“Friday, jesteś?”** and **“bez odbioru”**.

The installer includes the local speech model. The panel opens after installation and starts again at Windows sign-in.

## Beta status

We verified that a Windows scheduled task can open the selected Codex chat without a Codex entry in `PATH`. The desktop app must expose voice chat in that conversation for the spoken start phrase to connect.

Codex Voice Control is an independent AlphaStudioDE project. This repository hosts documentation and binary releases.

[Beta terms](BETA-TERMS.md) · [Third-party notices and source](THIRD_PARTY_NOTICES.md)
