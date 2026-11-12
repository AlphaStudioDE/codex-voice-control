# Third-party software

Codex Voice Control is distributed separately from the third-party components listed below. Their licenses and notices apply independently. The Windows installer includes the applicable upstream notices in the `licenses` directory.

| Component | Version and license | Corresponding source |
| --- | --- | --- |
| Python-SoXR and libsoxr | Python-SoXR 1.0.0, LGPL-2.1-or-later. The packaged Windows extension includes libsoxr at commit `a66f3eeeeb62a32403ff143b756eed92b1ec6b62`. | [Source archive including libsoxr](https://github.com/AlphaStudioDE/codex-voice-control/releases/download/v0.1.0-beta.1/soxr-1.0.0.tar.gz), [wheel build configuration](https://github.com/dofuuz/python-soxr/tree/v1.0.0/.github/workflows) |
| certifi | 2026.10.23, MPL-2.0 | [Source archive](https://github.com/AlphaStudioDE/codex-voice-control/releases/download/v0.1.0-beta.1/certifi-2026.10.23.tar.gz) |
| tqdm | 4.70.1, MIT and MPL-2.0 | [Source archive](https://github.com/AlphaStudioDE/codex-voice-control/releases/download/v0.1.0-beta.1/tqdm-4.70.1.tar.gz) |
| faster-whisper | 1.2.1, MIT | [Upstream source](https://github.com/SYSTRAN/faster-whisper/tree/v1.2.1). The installer uses the NumPy input path and disables the optional PyAV file decoder at build time. |
| Whisper base model | Systran conversion of OpenAI Whisper base, MIT | [Packaged model revision](https://huggingface.co/Systran/faster-whisper-base/tree/ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66) |

The SoXR extension is a separate file at `app/soxr/soxr_ext.pyd`. It may be replaced with a compatible build. The terms for the application do not restrict modification of LGPL components or reverse engineering for debugging such modifications.
