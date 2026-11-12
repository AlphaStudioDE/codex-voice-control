# Codex Voice Control

[English](README.md)

![Wielowarstwowa fala głosu w odcieniach błękitu i fioletu](assets/voice-wave.png)

**Miej głos Codexa pod ręką bez zostawiania otwartej rozmowy przez cały dzień.**

Aplikacja powstała, żeby oszczędzać limit użycia Codexa. Czeka lokalnie na Twoją frazę, więc możesz otworzyć połączenie na czas rozmowy i zakończyć je poleceniem głosowym. Głos w aplikacji desktopowej jest rozliczany za czas z tej samej puli co zadania Codexa. Zamykając połączenie między rozmowami, skracasz czas w trybie głosowym. Model wykonujący zadanie ma osobną stawkę za tokeny. [Rozliczanie głosu w dokumentacji OpenAI](https://learn.chatgpt.com/docs/pricing#how-much-does-voice-cost)

Codex Voice Control to niezależna aplikacja dla Windows. Ustaw własne komendy głosowe, wybierz czat i używaj Codexa głosem, gdy masz ręce zajęte. Wąska nakładka u góry ekranu pokazuje stan rozmowy i reaguje na głos. Kliknięcia przechodzą przez nią do aplikacji pod spodem.

## Co możesz ustawić

- **Frazy startu i zakończenia.** Dodaj po kilka fraz i wybierz język rozpoznawania niezależnie od języka menu. Rozpoznawanie komend odbywa się lokalnie.
- **Czat docelowy.** Użyj ostatnio otwartego czatu albo wskaż konkretną rozmowę w ustawieniach. Zobacz ograniczenie wersji testowej poniżej.
- **Nakładkę i dźwięki.** Fala zmienia kolor w zależności od stanu rozmowy. Dźwięki połączenia, rozłączenia i gotowej odpowiedzi ustawisz osobno.
- **Powiadomienia MCP.** Opcjonalna integracja pozwala Codexowi zasygnalizować zakończenie zadania, również gdy rozmowa głosowa jest zamknięta.

## Automatyczny odczyt

**Automatyczny odczyt jest domyślnie włączony.** Gdy Codex zaczyna pracować nad poleceniem głosowym, Codex Voice Control rozłącza głos, a Codex pracuje dalej. Kiedy odpowiedź jest gotowa, aplikacja wznawia głos w tym samym czacie i prosi Codexa o ponowne przeczytanie odpowiedzi na głos.

Opcję wyłączysz w **Ustawienia → Czat docelowy**. Fraza kończąca anuluje również oczekujące ponowne połączenie. Automatyczny odczyt obsługuje angielski i polski interfejs desktopowego Codexa.

## Pierwsze uruchomienie

1. Pobierz instalator z wydania [Beta 2](https://github.com/AlphaStudioDE/codex-voice-control/releases/tag/v0.1.0-beta.2). Potrzebujesz 64-bitowego Windowsa, mikrofonu i aplikacji Codex z dostępem do rozmów głosowych.
2. Otwórz Codex Voice Control ze skrótu na pulpicie. W menu ikony obok zegara wybierz **Ustawienia**, ustaw język oraz frazy i włącz nasłuch.
3. Wybierz czat w Codexie. W polskiej konfiguracji powiedz **„Friday, jesteś?”**. Po połączeniu mów normalnie. Rozmowę zakończ słowami **„bez odbioru”**.

Instalator zawiera lokalny model mowy i środowisko uruchomieniowe. Panel uruchamia się po instalacji i przy logowaniu do Windows. Połączenia głosowe obsługuje Codex zgodnie z dostępnością funkcji na Twoim koncie.

## Status wersji testowej

Sprawdziliśmy, że zadanie uruchomione przez Harmonogram Windows otwiera wybrany czat także bez wpisu Codexa w `PATH`. Żeby fraza połączyła głos, aplikacja desktopowa Codex musi udostępniać rozmowę głosową w danym czacie.

To repozytorium zawiera opis, instrukcje i wydania binarne. Codex Voice Control jest niezależnym projektem AlphaStudioDE. Nazwa Codex określa aplikację, z którą współpracuje.

[Warunki bety](BETA-TERMS.md) · [Licencje i źródła bibliotek](THIRD_PARTY_NOTICES.md)
