# Codex Voice Control

[English](README.md)

![Wielowarstwowa fala głosu w odcieniach błękitu i fioletu](assets/voice-wave.png)

**Miej głos Codexa pod ręką bez zostawiania otwartej rozmowy przez cały dzień.**

Aplikacja powstała, żeby oszczędzać limit użycia Codexa. Czeka lokalnie na Twoją frazę, więc możesz otworzyć połączenie na czas rozmowy i zakończyć je poleceniem głosowym. Chodzi o ograniczenie zużycia związanego z pozostawianiem otwartego połączenia między rozmowami. Faktyczne zużycie zależy od sposobu rozliczania głosu przez Codexa i czasu trwania sesji.

Codex Voice Control to niezależna aplikacja dla Windows. Ustaw własne komendy głosowe, wybierz czat i używaj Codexa głosem, gdy masz ręce zajęte. Wąska nakładka u góry ekranu pokazuje stan rozmowy i reaguje na głos. Kliknięcia przechodzą przez nią do aplikacji pod spodem.

## Co możesz ustawić

- **Frazy startu i zakończenia.** Dodaj po kilka fraz i wybierz język rozpoznawania niezależnie od języka menu. Rozpoznawanie komend odbywa się lokalnie.
- **Czat docelowy.** Użyj ostatnio otwartego czatu albo wskaż konkretną rozmowę w ustawieniach. Zobacz ograniczenie wersji testowej poniżej.
- **Nakładkę i dźwięki.** Fala zmienia kolor w zależności od stanu rozmowy. Dźwięki połączenia, rozłączenia i gotowej odpowiedzi ustawisz osobno.
- **Powiadomienia MCP.** Opcjonalna integracja pozwala Codexowi zasygnalizować zakończenie zadania, również gdy rozmowa głosowa jest zamknięta.

## Pierwsze uruchomienie

1. Pobierz instalator z [GitHub Releases](https://github.com/AlphaStudioDE/codex-voice-control/releases), gdy wydanie testowe będzie dostępne. Potrzebujesz 64-bitowego Windowsa, mikrofonu i aplikacji Codex z dostępem do rozmów głosowych.
2. Otwórz Codex Voice Control ze skrótu na pulpicie. W menu ikony obok zegara wybierz **Ustawienia**, ustaw język oraz frazy i włącz nasłuch.
3. Wybierz czat w Codexie. W polskiej konfiguracji powiedz **„Friday, jesteś?”**. Po połączeniu mów normalnie. Rozmowę zakończ słowami **„bez odbioru”**.

Instalator zawiera lokalny model mowy i środowisko uruchomieniowe. Panel uruchamia się po instalacji i przy logowaniu do Windows. Połączenia głosowe obsługuje Codex zgodnie z dostępnością funkcji na Twoim koncie.

## Status wersji testowej

Wybór konkretnego czatu w tle zależy od tego, czy nasłuch może odnaleźć lokalną instalację Codexa. W testach na Windows nasłuch uruchamiany przez autostart rozpoznał frazę startową, ale w jednej konfiguracji nie znalazł Codexa. Opis błędu powinien zawierać wersję Windowsa, wersję Codexa oraz kilka istotnych linii logu z pominięciem prywatnych danych.

To repozytorium zawiera opis, instrukcje i wydania binarne. Codex Voice Control jest niezależnym projektem AlphaStudioDE. Nazwa Codex określa aplikację, z którą współpracuje.
