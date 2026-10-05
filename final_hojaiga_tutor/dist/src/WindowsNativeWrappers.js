"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.WindowsActiveWindowDetector = exports.WindowsNativeTTSProvider = exports.WindowsSpeechTranscriptionProvider = exports.WindowsPCMConverter = void 0;
const child_process_1 = require("child_process");
const util_1 = require("util");
const execFileAsync = (0, util_1.promisify)(child_process_1.execFile);
/**
 * 1. Windows equivalent of PCMConverter.swift
 * Downsamples Float32/Int16 audio buffers to 16kHz, 16-bit mono PCM (or WAV)
 * for streaming transcription providers (AssemblyAI / Whisper / Deepgram).
 */
class WindowsPCMConverter {
    static convertFloat32ToPCM16(float32Buffer, inputSampleRate, targetSampleRate = 16000) {
        const ratio = inputSampleRate / targetSampleRate;
        const outputLength = Math.round(float32Buffer.length / ratio);
        const pcm16 = new Int16Array(outputLength);
        for (let i = 0; i < outputLength; i++) {
            const srcIndex = Math.min(float32Buffer.length - 1, Math.floor(i * ratio));
            const sample = Math.max(-1, Math.min(1, float32Buffer[srcIndex]));
            pcm16[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
        }
        return Buffer.from(pcm16.buffer);
    }
    static wrapPCM16InWavHeader(pcmBuffer, sampleRate = 16000) {
        const header = Buffer.alloc(44);
        const dataLength = pcmBuffer.length;
        header.write('RIFF', 0);
        header.writeUInt32LE(36 + dataLength, 4);
        header.write('WAVE', 8);
        header.write('fmt ', 12);
        header.writeUInt32LE(16, 16);
        header.writeUInt16LE(1, 20);
        header.writeUInt16LE(1, 22);
        header.writeUInt32LE(sampleRate, 24);
        header.writeUInt32LE(sampleRate * 2, 28);
        header.writeUInt16LE(2, 32);
        header.writeUInt16LE(16, 34);
        header.write('data', 36);
        header.writeUInt32LE(dataLength, 40);
        return Buffer.concat([header, pcmBuffer]);
    }
}
exports.WindowsPCMConverter = WindowsPCMConverter;
/**
 * 2. Windows equivalent of SFSpeechTranscriptionProvider.swift
 * Native Windows System.Speech.Recognition via PowerShell - free, no STT key.
 */
class WindowsSpeechTranscriptionProvider {
    static async recognizeOnceFromMic(timeoutSeconds = 6) {
        const psScript = `
      Add-Type -AssemblyName System.Speech
      $rec = New-Object System.Speech.Recognition.SpeechRecognitionEngine
      $rec.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
      $rec.SetInputToDefaultAudioDevice()
      $result = $rec.Recognize([TimeSpan]::FromSeconds(${timeoutSeconds}))
      if ($null -ne $result) { Write-Output $result.Text }
    `;
        try {
            const { stdout } = await execFileAsync('powershell.exe', [
                '-NoProfile',
                '-NonInteractive',
                '-Command',
                psScript,
            ]);
            return (stdout || '').trim();
        }
        catch {
            return '';
        }
    }
}
exports.WindowsSpeechTranscriptionProvider = WindowsSpeechTranscriptionProvider;
/**
 * 3. Windows Native SAPI5 Voice Synthesizer (fallback when Edge neural TTS fails).
 * Free, offline, no key.
 */
class WindowsNativeTTSProvider {
    static async speak(text, rate = 1) {
        const clean = text.replace(/["`$]/g, ' ').replace(/\s+/g, ' ').trim();
        if (!clean)
            return;
        const psScript = `
      Add-Type -AssemblyName System.Speech
      $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
      $synth.Rate = ${Math.max(-2, Math.min(4, rate))}
      $synth.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::NotSet)
      $synth.Speak("${clean}")
    `;
        try {
            await execFileAsync('powershell.exe', [
                '-NoProfile',
                '-NonInteractive',
                '-Command',
                psScript,
            ]);
        }
        catch {
            // Ignore if the audio device is busy
        }
    }
}
exports.WindowsNativeTTSProvider = WindowsNativeTTSProvider;
/**
 * 4. Windows equivalent of macOS CGWindowList / NSScreen inspector.
 * Detects the foreground window bounds so drawings avoid the Clicky panel.
 */
class WindowsActiveWindowDetector {
    static async getForegroundWindowBounds() {
        const psScript = `
      Add-Type @"
      using System;
      using System.Runtime.InteropServices;
      using System.Text;
      public class Win32Window {
        [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
        [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
        [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
      }
"@
      $h = [Win32Window]::GetForegroundWindow()
      $sb = New-Object System.Text.StringBuilder 256
      [void][Win32Window]::GetWindowText($h, $sb, 256)
      $r = New-Object Win32Window+RECT
      [void][Win32Window]::GetWindowRect($h, [ref]$r)
      $w = $r.Right - $r.Left
      $ht = $r.Bottom - $r.Top
      Write-Output "$($sb.ToString())|$($r.Left)|$($r.Top)|$w|$ht"
    `;
        try {
            const { stdout } = await execFileAsync('powershell.exe', [
                '-NoProfile',
                '-NonInteractive',
                '-Command',
                psScript,
            ]);
            const parts = (stdout || '').trim().split('|');
            if (parts.length >= 5) {
                return {
                    title: parts[0] || 'Desktop',
                    x: Math.max(0, parseInt(parts[1], 10) || 0),
                    y: Math.max(0, parseInt(parts[2], 10) || 0),
                    width: Math.max(600, parseInt(parts[3], 10) || 1280),
                    height: Math.max(400, parseInt(parts[4], 10) || 800),
                };
            }
        }
        catch {
            // Fallback to a standard 1080p safe canvas
        }
        return { title: 'Screen', x: 60, y: 60, width: 1200, height: 780 };
    }
}
exports.WindowsActiveWindowDetector = WindowsActiveWindowDetector;
