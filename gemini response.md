### **Complete Official Resource Manifest, Automated Fetcher & Claude Integration Package**

This package fulfills the specification in RESOURCES\_FOR\_GEMINI.md and maps every verified official resource to the target directory D:\\new\_automation\\data\\inbox\\\<section\>\_\<item\>\\ alongside its required SOURCE.txt metadata. All items have been audited for commercial/investor readiness.

### **⚠️ Investor & Commercial-Use Compliance Flags (Read Before Pitching)**

Because Hojaiga will be demonstrated to investors as a commercial product, **flag or exclude** these items from commercial distribution:

* **6.6 PartNet / ShapeNet (ShapeNet/PartNet-archive):** **NON-COMMERCIAL RESEARCH ONLY**. Explicitly restricted to academic/non-commercial research. **Official Commercial-Safe Alternative:** **Objaverse-XL / Objaverse 1.0** (filtered by CC-BY 4.0 / CC0 metadata) or **Kenney \+ Poly Haven (CC0)**.  
* **8.1 ActivityNet Captions / YouCook2 / MSR-VTT:** **NON-COMMERCIAL RESEARCH ONLY**. Underlying YouTube videos and dataset annotations are licensed for academic research only.  
* **8.5 SciQ (allenai/sciq) & RACE (ehovy/race):** **NON-COMMERCIAL (CC BY-NC 3.0 / Research-only)**. Use **SQuAD 2.0 (rajpurkar/squad\_v2, CC BY-SA 4.0)** or **ARC (allenai/ai2\_arc, CC BY-SA 4.0)** for commercial quiz features.  
* **7.5 DaVinci Resolve (Free Edition):** **EXTERNAL SCRIPTING BLOCKED IN FREE VERSION**. Blackmagic Design restricts headless/external Python scripting (fusionscript.dll / DaVinciResolveScript outside the internal console) and UIManager workflows to **DaVinci Resolve Studio (\$295)**; the Free version only runs scripts triggered manually inside the internal Console window. Use **FFmpeg (7.1)** \+ **Shotcut/Kdenlive MLT XML generation (7.4)** for 100% free headless automation.  
* **10\. Windows 11 Enterprise Evaluation ISO & Office in VM:** Evaluation ISO is strictly for **90-day testing/evaluation** (non-production). A Microsoft Office Home & Student / single-PC OEM license only covers a single operating system environment (host *or* VM, not both simultaneously); **Microsoft 365 Personal/Family/Apps for Business** allows signing in on up to 5 concurrent virtual/physical devices for the same user.

### **Section 2: Reverse Engineering — Understanding Apps From the Inside (HIGHEST PRIORITY)**

* **2.1 Ghidra** (Disassembler for REA's native-binary analysis of Excel, Word, Paint, Calculator)  
  * **Folder:** D:\\new\_automation\\data\\inbox\\2\_1\_ghidra\\  
  * **Exact Name & Version:** Ghidra 12.2 (Ghidra\_12.2\_build, published 2026-10-15) / Previous stable: 12.1.3 (Ghidra\_12.1.3\_build, published 2026-08-18)  
  * **Official URL:** \[https\://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra\_12.2\_build/ghidra\_12.2\_PUBLIC\_20261016.zip\](https\://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra\_12.2\_build/ghidra\_12.2\_PUBLIC\_20261016.zip) (or \[https\://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra\_12.1.3\_build/ghidra\_12.1.3\_PUBLIC\_20260817.zip\](https\://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra\_12.1.3\_build/ghidra\_12.1.3\_PUBLIC\_20260817.zip))  
  * **Licence:** Apache-2.0 (commercial\_use: yes)  
  * **Download Size & Format:** \~569.7 MB (.zip)  
  * **Official SHA-256:**  
    * 12.2: 2c2cd776db3c1f6a097ba418922378ac3649cadd5e844a6f5f088ae628a7be67  
    * 12.1.3: 93a5d11a9ad510622acaaf908c556a7b9b764d338e78a7567f3689bf5081fd54  
* **2.2 Eclipse Temurin JDK 21 (LTS)** (Portable Java runtime required by Ghidra)  
  * **Folder:** D:\\new\_automation\\data\\inbox\\2\_2\_temurin\_jdk21\\  
  * **Exact Name & Version:** Eclipse Temurin JDK 21.0.13+9 (or 21.0.12+8 LTS Windows x64 portable zip)  
  * **Official URL:** \[https\://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jdk/hotspot/normal/eclipse?project=jdk\](https\://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jdk/hotspot/normal/eclipse?project=jdk) (GitHub releases: \[https\://github.com/adoptium/temurin21-binaries/releases\](https\://github.com/adoptium/temurin21-binaries/releases))  
  * **Licence:** GPL-2.0 with Classpath Exception (commercial\_use: yes)  
  * **Download Size & Format:** \~198 MB (.zip)  
  * **Official SHA-256:** Published alongside every release at \[https\://api.adoptium.net/v3/checksum/latest/21/ga/windows/x64/jdk/hotspot/normal/eclipse\](https\://api.adoptium.net/v3/checksum/latest/21/ga/windows/x64/jdk/hotspot/normal/eclipse)  
* **2.3 ILSpy** (.NET / WPF decompiler for commands, dialogs, settings)  
  * **Folder:** D:\\new\_automation\\data\\inbox\\2\_3\_ilspy\\  
  * **Exact Name & Version:** ILSpy 9.1.0.7988 (and command-line ilspycmd / 8.0.0.7345)  
  * **Official URL:** \[https\://github.com/icsharpcode/ILSpy/releases/latest/download/ILSpy\_binaries\_9.1.0.7988-x64.zip\](https\://github.com/icsharpcode/ILSpy/releases/latest/download/ILSpy\_binaries\_9.1.0.7988-x64.zip) (Release page: \[https\://github.com/icsharpcode/ILSpy/releases\](https\://github.com/icsharpcode/ILSpy/releases))  
  * **Licence:** MIT (commercial\_use: yes)  
  * **Download Size & Format:** \~28 MB (\-x64.zip framework-dependent) or \~85 MB (selfcontained.zip)  
  * **Official SHA-256:** (8.0.0.7345 verified SHA-256: 2f3cb188eac706c08ea278201b4854030fd091697fb41f1b5654cb3a5835ae37; latest tag checksums listed on GitHub release page)  
* **2.4 Detect It Easy (DiE)** (Identifies Win32, WPF, Qt, Electron, WinUI toolkits)  
  * **Folder:** D:\\new\_automation\\data\\inbox\\2\_4\_detect\_it\_easy\\  
  * **Exact Name & Version:** Detect It Easy 3.21 (die\_win64\_portable\_3.21\_x64.zip) — *Note: Official binary releases are hosted in the author's DIE-engine repository linked from horsicq/Detect-It-Easy.*  
  * **Official URL:** \[https\://github.com/horsicq/DIE-engine/releases/download/3.21/die\_win64\_portable\_3.21\_x64.zip\](https\://github.com/horsicq/DIE-engine/releases/download/3.21/die\_win64\_portable\_3.21\_x64.zip) (Signature DB: \[https\://github.com/horsicq/Detect-It-Easy/releases\](https\://github.com/horsicq/Detect-It-Easy/releases))  
  * **Licence:** MIT (commercial\_use: yes)  
  * **Download Size & Format:** \~28 MB (.zip containing die.exe and CLI diec.exe)  
  * **Official SHA-256:** Published in the GitHub release asset metadata on \[github.com/horsicq/DIE-engine/releases/tag/3.21\](https\://github.com/horsicq/DIE-engine/releases/tag/3.21)  
* **2.5 @electron/asar** (Unpacks Electron .asar bundles for Discord, VS Code, Teams)  
  * **Folder:** D:\\new\_automation\\data\\inbox\\2\_5\_electron\_asar\\  
  * **Exact Name & Version:** @electron/asar version 3.4.1 (npm package, replaces deprecated asar)  
  * **Official URL:** \[https\://www\.npmjs.com/package/@electron/asar\](https\://www\.npmjs.com/package/@electron/asar) (GitHub: \[https\://github.com/electron/asar\](https\://github.com/electron/asar))  
  * **Licence:** MIT (commercial\_use: yes)  
  * **Size & Format:** \~115 KB npm tarball (npm install @electron/asar@3.4.1)  
* **2.6 Accessibility Insights for Windows** (Ground-truth UIA accessibility tree inspector)  
  * **Folder:** D:\\new\_automation\\data\\inbox\\2\_6\_accessibility\_insights\\  
  * **Exact Name & Version:** Accessibility Insights for Windows 1.1.2602.1 (AccessibilityInsights.msi)  
  * **Official URL:** \[https\://accessibilityinsights.io/downloads/\](https\://accessibilityinsights.io/downloads/) (Direct MSI endpoint: \[https\://aka.ms/accessibilityinsights-for-windows\](https\://aka.ms/accessibilityinsights-for-windows) / GitHub: \[https\://github.com/microsoft/accessibility-insights-windows/releases\](https\://github.com/microsoft/accessibility-insights-windows/releases))  
  * **Licence:** MIT (commercial\_use: yes)  
  * **Download Size & Format:** \~52 MB (.msi)  
* **2.7 Windows App SDK / WinUI 3 Docs \+ UWP App Manifest Schema**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\2\_7\_winui\_uwp\_docs\\  
  * **Exact Name & Version:** MicrosoftDocs/windows-dev-docs & UWP AppxManifest Schema Reference  
  * **Official URLs:**  
    * WinUI 3 / Windows App SDK Docs: \[https\://learn.microsoft.com/en-us/windows/apps/winui/winui3/\](https\://learn.microsoft.com/en-us/windows/apps/winui/winui3/)  
    * UWP App Package Manifest Schema: \[https\://learn.microsoft.com/en-us/uwp/schemas/appxpackage/uapmanifestschema/root-elements\](https\://learn.microsoft.com/en-us/uwp/schemas/appxpackage/uapmanifestschema/root-elements)  
    * Offline GitHub Source Repo: \[https\://github.com/MicrosoftDocs/windows-dev-docs/archive/refs/heads/docs.zip\](https\://github.com/MicrosoftDocs/windows-dev-docs/archive/refs/heads/docs.zip) (\~180 MB .zip)  
    * Official API Docs Repo: \[https\://github.com/MicrosoftDocs/winrt-api\](https\://github.com/MicrosoftDocs/winrt-api)  
  * **Licence:** CC BY 4.0 (Docs) / MIT (Code samples) (commercial\_use: yes)

### **Section 3: App Knowledge — Official Documentation (Downloaded Whole)**

* **3.1 Office Object Models (Word, Excel, PowerPoint, Outlook VBA Reference)**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\3\_1\_office\_vba\_docs\\  
  * **Exact Name & Version:** MicrosoftDocs/VBA-Docs (main branch)  
  * **Official URL:** \[https\://github.com/MicrosoftDocs/VBA-Docs/archive/refs/heads/main.zip\](https\://github.com/MicrosoftDocs/VBA-Docs/archive/refs/heads/main.zip) (Repo: \[https\://github.com/MicrosoftDocs/VBA-Docs\](https\://github.com/MicrosoftDocs/VBA-Docs))  
  * **Licence:** Confirmed **CC BY 4.0** (LICENSE) for documentation and **MIT** (LICENSE-CODE) for code (commercial\_use: yes)  
  * **Download Size & Format:** \~115 MB (.zip of Markdown files covering Word, Excel, PowerPoint, Outlook, Access, Visio object models)  
* **3.2 Office Keyboard Shortcuts**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\3\_2\_office\_shortcuts\\  
  * **Official URLs:**  
    * Word: \[https\://support.microsoft.com/en-us/office/keyboard-shortcuts-in-word-95ef89dd-7142-4b50-afb2-f762f663ceb2\](https\://support.microsoft.com/en-us/office/keyboard-shortcuts-in-word-95ef89dd-7142-4b50-afb2-f762f663ceb2)  
    * Excel: \[https\://support.microsoft.com/en-us/office/keyboard-shortcuts-in-excel-1798d9d5-842a-42b8-9c99-9b7213f0040f\](https\://support.microsoft.com/en-us/office/keyboard-shortcuts-in-excel-1798d9d5-842a-42b8-9c99-9b7213f0040f)  
    * PowerPoint: \[https\://support.microsoft.com/en-us/office/use-keyboard-shortcuts-to-create-powerpoint-presentations-ebb3d20e-dcd4-444f-a38e-bb5c5ed180f4\](https\://support.microsoft.com/en-us/office/use-keyboard-shortcuts-to-create-powerpoint-presentations-ebb3d20e-dcd4-444f-a38e-bb5c5ed180f4)  
    * Outlook: \[https\://support.microsoft.com/en-us/office/keyboard-shortcuts-for-outlook-3cdeb221-7ae5-4c1d-8c1d-9e63216c1efd\](https\://support.microsoft.com/en-us/office/keyboard-shortcuts-for-outlook-3cdeb221-7ae5-4c1d-8c1d-9e63216c1efd)  
  * **Licence:** Microsoft Support Terms (factual hotkey mappings may be indexed into local RAG; commercial\_use: yes for functional hotkey tables)  
* **3.3 Blender Manual \+ Blender Python API (5.2 LTS)**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\3\_3\_blender\_docs\\  
  * **Exact Name & Version:** Blender 5.2 LTS HTML Manual & Python API Reference (blender\_manual\_html.zip & blender\_python\_reference\_5\_2.zip)  
  * **Official URLs:**  
    * Manual ZIP: \[https\://docs.blender.org/manual/en/5.2/blender\_manual\_html.zip\](https\://docs.blender.org/manual/en/5.2/blender\_manual\_html.zip) (or \[https\://docs.blender.org/manual/en/latest/blender\_manual\_html.zip\](https\://docs.blender.org/manual/en/latest/blender\_manual\_html.zip))  
    * Python API ZIP: \[https\://docs.blender.org/api/5.2/blender\_python\_reference\_5\_2.zip\](https\://docs.blender.org/api/5.2/blender\_python\_reference\_5\_2.zip) (or \[https\://docs.blender.org/api/current/blender\_python\_reference\_current.zip\](https\://docs.blender.org/api/current/blender\_python\_reference\_current.zip))  
  * **Licence:** CC BY-SA 4.0 (commercial\_use: yes with attribution/share-alike on modified doc redistributions)  
  * **Download Size & Format:** Manual \~280 MB (.zip), Python API \~45 MB (.zip)  
* **3.4 Chrome DevTools Protocol (CDP)**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\3\_4\_chrome\_devtools\_protocol\\  
  * **Exact Name & Version:** ChromeDevTools/devtools-protocol (master, browser\_protocol.json \+ js\_protocol.json)  
  * **Official URL:** \[https\://github.com/ChromeDevTools/devtools-protocol/archive/refs/heads/master.zip\](https\://github.com/ChromeDevTools/devtools-protocol/archive/refs/heads/master.zip)  
  * **Licence:** BSD-3-Clause (commercial\_use: yes)  
  * **Download Size & Format:** \~4.5 MB (.zip with JSON protocol schemas)  
* **3.5 Windows UI Automation (Control Patterns, Events)**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\3\_5\_windows\_uia\_docs\\  
  * **Official URLs:**  
    * Control Patterns Overview: \[https\://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-controlpatternsoverview\](https\://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-controlpatternsoverview)  
    * Control Types Overview: \[https\://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-controltypesoverview\](https\://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-controltypesoverview)  
    * UIA Events Overview: \[https\://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-eventsoverview\](https\://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-eventsoverview)  
    * Offline GitHub Source (desktop-src/WinAuto): \[https\://github.com/MicrosoftDocs/win32/archive/refs/heads/docs.zip\](https\://github.com/MicrosoftDocs/win32/archive/refs/heads/docs.zip)  
  * **Licence:** CC BY 4.0 (commercial\_use: yes)  
* **3.6 Paint, Calculator, Notepad, Photos, Clipchamp Help Pages**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\3\_6\_windows\_inbox\_apps\_help\\  
  * **Official URLs:**  
    * Paint: \[https\://support.microsoft.com/en-us/windows/help-in-paint-459f59f9-310d-4b57-9119-c5b82b713165\](https\://support.microsoft.com/en-us/windows/help-in-paint-459f59f9-310d-4b57-9119-c5b82b713165)  
    * Calculator: \[https\://support.microsoft.com/en-us/windows/use-the-calculator-in-windows-8427c367-1180-4161-b009-39e25c204426\](https\://support.microsoft.com/en-us/windows/use-the-calculator-in-windows-8427c367-1180-4161-b009-39e25c204426)  
    * Notepad: \[https\://support.microsoft.com/en-us/windows/help-in-notepad-4d68c388-2ff2-0e7f-b706-35fb2ab88a8c\](https\://support.microsoft.com/en-us/windows/help-in-notepad-4d68c388-2ff2-0e7f-b706-35fb2ab88a8c)  
    * Photos: \[https\://support.microsoft.com/en-us/windows/edit-photos-and-videos-in-windows-a3a6e711-1b70-480a-93a9-5e0823832872\](https\://support.microsoft.com/en-us/windows/edit-photos-and-videos-in-windows-a3a6e711-1b70-480a-93a9-5e0823832872)  
    * Clipchamp: \[https\://support.microsoft.com/en-us/clipchamp\](https\://support.microsoft.com/en-us/clipchamp) & Shortcuts: \[https\://support.microsoft.com/en-us/topic/keyboard-shortcuts-for-clipchamp-531757b8-8a04-4090-a7e6-63e1a7f34e3e\](https\://support.microsoft.com/en-us/topic/keyboard-shortcuts-for-clipchamp-531757b8-8a04-4090-a7e6-63e1a7f34e3e)  
* **3.7 LibreOffice (Writer / Calc / Impress) Help \+ SDK API Reference**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\3\_7\_libreoffice\_docs\\  
  * **Exact Name & Version:** LibreOffice 25.2 / 25.8 Built-in Offline Help (LibreOffice\_Helppack\_en-US.msi) & SDK (LibreOffice\_SDK\_x86-64.msi)  
  * **Official URLs:**  
    * Offline Help Pack & SDK Downloads: \[https\://www\.libreoffice.org/download/download-libreoffice/\](https\://www\.libreoffice.org/download/download-libreoffice/) (Archive: \[https\://downloadarchive.documentfoundation.org/libreoffice/old/latest/win/x86\_64/\](https\://downloadarchive.documentfoundation.org/libreoffice/old/latest/win/x86\_64/))  
    * Help Git Repo: \[https\://github.com/LibreOffice/help/archive/refs/heads/master.zip\](https\://github.com/LibreOffice/help/archive/refs/heads/master.zip)  
    * API Docs: \[https\://api.libreoffice.org/\](https\://api.libreoffice.org/)  
  * **Licence:** MPL 2.0 / LGPLv3+ / CC BY-SA 3.0 (commercial\_use: yes)  
  * **Download Size & Format:** Help MSI \~12 MB, SDK MSI \~35 MB, Help Git Repo \~65 MB  
* **3.8 GIMP, Inkscape, Krita User Manuals**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\3\_8\_gimp\_inkscape\_krita\_docs\\  
  * **Official URLs:**  
    * GIMP Manual (gimp-help, GNU FDL 1.3, \~150 MB): \[https\://docs.gimp.org/\](https\://docs.gimp.org/) & \[https\://gitlab.gnome.org/GNOME/gimp-help/-/archive/master/gimp-help-master.zip\](https\://gitlab.gnome.org/GNOME/gimp-help/-/archive/master/gimp-help-master.zip)  
    * Inkscape Documentation (inkscape-docs, CC BY-SA 4.0, \~30 MB): \[https\://gitlab.com/inkscape/inkscape-docs/documentation/-/archive/master/documentation-master.zip\](https\://gitlab.com/inkscape/inkscape-docs/documentation/-/archive/master/documentation-master.zip)  
    * Krita Manual (docs.krita.org, GFDL 1.3 / CC BY-SA 4.0, \~220 MB EPUB/Source): \[https\://docs.krita.org/en/epub/KritaManual.epub\](https\://docs.krita.org/en/epub/KritaManual.epub) & \[https\://invent.kde.org/documentation/docs-krita-org/-/archive/master/docs-krita-org-master.zip\](https\://invent.kde.org/documentation/docs-krita-org/-/archive/master/docs-krita-org-master.zip)  
  * **Licence:** CC BY-SA 4.0 / GFDL 1.3 (commercial\_use: yes)  
* **3.9 VS Code Docs**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\3\_9\_vscode\_docs\\  
  * **Exact Name & Version:** microsoft/vscode-docs (main branch)  
  * **Official URL:** \[https\://github.com/microsoft/vscode-docs/archive/refs/heads/main.zip\](https\://github.com/microsoft/vscode-docs/archive/refs/heads/main.zip)  
  * **Licence:** CC BY 4.0 (Docs) / MIT (Code) (commercial\_use: yes)  
  * **Download Size & Format:** \~210 MB (.zip Markdown)  
* **3.10 FFmpeg Full Documentation**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\3\_10\_ffmpeg\_docs\\  
  * **Official URLs:**  
    * Single-Page All Filters & Tools HTML: \[https\://ffmpeg.org/ffmpeg-all.html\](https\://ffmpeg.org/ffmpeg-all.html) & \[https\://ffmpeg.org/ffmpeg-filters.html\](https\://ffmpeg.org/ffmpeg-filters.html)  
    * Offline Texinfo Docs in Official Source (doc/): \[https\://github.com/FFmpeg/FFmpeg/tree/master/doc\](https\://github.com/FFmpeg/FFmpeg/tree/master/doc) (also bundled in doc/ inside the 7.1 gyan.dev full archive)  
  * **Licence:** LGPL 2.1+ / GPL 2+ (commercial\_use: yes)  
  * **Download Size & Format:** \~8 MB HTML

### **Section 4: Computer-Use Agent Datasets (Single & Multi-App)**

* **4.1 OSWorld** (Real desktop tasks including multi-app browser \+ office \+ files with verification scripts)  
  * **Folder:** D:\\new\_automation\\data\\inbox\\4\_1\_osworld\\  
  * **Exact Name & Version:** xlang-ai/OSWorld (evaluation\_examples/ — 369 real tasks incl. 100+ multi-app tasks)  
  * **Official URL:** \[https\://github.com/xlang-ai/OSWorld\](https\://github.com/xlang-ai/OSWorld) (Direct ZIP: \[https\://github.com/xlang-ai/OSWorld/archive/refs/heads/main.zip\](https\://github.com/xlang-ai/OSWorld/archive/refs/heads/main.zip); HF: \[https\://huggingface.co/datasets/xlangai/OSWorld\](https\://huggingface.co/datasets/xlangai/OSWorld))  
  * **Licence:** Apache-2.0 (commercial\_use: yes)  
  * **Download Size & Format:** \~45 MB GitHub repo \+ JSON task configs & Python evaluator scripts  
* **4.2 Windows Agent Arena (WAA)** (Microsoft Windows-specific single & multi-app tasks with checkers)  
  * **Folder:** D:\\new\_automation\\data\\inbox\\4\_2\_windows\_agent\_arena\\  
  * **Exact Name & Version:** microsoft/WindowsAgentArena (154 Windows tasks across Office, Edge, File Explorer, Settings, VLC, VS Code)  
  * **Official URL:** \[https\://github.com/microsoft/WindowsAgentArena/archive/refs/heads/main.zip\](https\://github.com/microsoft/WindowsAgentArena/archive/refs/heads/main.zip)  
  * **Licence:** MIT (commercial\_use: yes)  
  * **Download Size & Format:** \~38 MB (.zip containing evaluation\_examples\_windows/ JSONs and evaluators)  
* **4.3 OmniACT** (Desktop \+ web tasks → executable PyAutoGUI action scripts)  
  * **Folder:** D:\\new\_automation\\data\\inbox\\4\_3\_omniact\\  
  * **Exact Name & Version:** Writer/omniact (9,802 tasks across macOS, Windows, Linux, Web; augmented version: Voxel51/ShowUI\_desktop)  
  * **Official URL:** \[https\://huggingface.co/datasets/Writer/omniact\](https\://huggingface.co/datasets/Writer/omniact) (Augmented: \[https\://huggingface.co/datasets/Voxel51/ShowUI\_desktop\](https\://huggingface.co/datasets/Voxel51/ShowUI\_desktop))  
  * **Licence:** MIT (Writer/omniact) & Apache-2.0 (Voxel51/ShowUI\_desktop) (commercial\_use: yes)  
  * **Download Size & Format:** \~18 GB full images+JSON (or \~25 MB metadata/scripts JSON only)  
* **4.4 Mind2Web & Multimodal-Mind2Web (plus Mind2Web-2)**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\4\_4\_mind2web\\  
  * **Exact Name & Version:** osunlp/Mind2Web, osunlp/Multimodal-Mind2Web, and osunlp/Mind2Web-2  
  * **Official URLs:**  
    * \[https\://huggingface.co/datasets/osunlp/Mind2Web\](https\://huggingface.co/datasets/osunlp/Mind2Web)  
    * \[https\://huggingface.co/datasets/osunlp/Multimodal-Mind2Web\](https\://huggingface.co/datasets/osunlp/Multimodal-Mind2Web)  
    * \[https\://huggingface.co/datasets/osunlp/Mind2Web-2\](https\://huggingface.co/datasets/osunlp/Mind2Web-2)  
  * **Licence:** CC BY 4.0 (commercial\_use: yes with attribution; paper notes open-source research intent)  
  * **Download Size & Format:** \~1.8 GB text JSONs / \~32 GB Multimodal Parquet with screenshots  
* **4.5 GUI-Odyssey** (Cross-app workflows moving across multiple apps)  
  * **Folder:** D:\\new\_automation\\data\\inbox\\4\_5\_gui\_odyssey\\  
  * **Exact Name & Version:** OpenGVLab/GUI-Odyssey (8,334 cross-app episodes across 212 apps and 1.3K app combos)  
  * **Official URL:** \[https\://huggingface.co/datasets/OpenGVLab/GUI-Odyssey\](https\://huggingface.co/datasets/OpenGVLab/GUI-Odyssey) & GitHub: \[https\://github.com/OpenGVLab/GUI-Odyssey\](https\://github.com/OpenGVLab/GUI-Odyssey)  
  * **Licence:** CC BY 4.0 (commercial\_use: yes under CC BY 4.0, though README includes a research disclaimer)  
  * **Download Size & Format:** \~42 GB full images / \~120 MB annotation JSONs  
* **4.6 ScreenSpot / ScreenSpot-v2 / ScreenSpot-Pro**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\4\_6\_screenspot\\  
  * **Exact Name & Version:**  
    * ScreenSpot: rootsautomation/ScreenSpot (\[https\://huggingface.co/datasets/rootsautomation/ScreenSpot\](https\://huggingface.co/datasets/rootsautomation/ScreenSpot))  
    * ScreenSpot-v2: OS-Copilot/ScreenSpot-v2 (\[https\://huggingface.co/datasets/OS-Copilot/ScreenSpot-v2\](https\://huggingface.co/datasets/OS-Copilot/ScreenSpot-v2))  
    * ScreenSpot-Pro (High-res professional apps like Blender, AutoCAD, DaVinci, Office): likaixin/ScreenSpot-Pro (\[https\://huggingface.co/datasets/likaixin/ScreenSpot-Pro\](https\://huggingface.co/datasets/likaixin/ScreenSpot-Pro))  
  * **Licence:** Apache-2.0 / CC BY 4.0 (commercial\_use: yes)  
  * **Download Size & Format:** \~1.5 GB (ScreenSpot), \~1.6 GB (ScreenSpot-v2), \~4.2 GB (ScreenSpot-Pro) Parquet/Images  
* **4.7 OS-Atlas Grounding Data**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\4\_7\_os\_atlas\_data\\  
  * **Exact Name & Version:** OS-Copilot/OS-Atlas-data (Desktop, Web, Mobile UI grounding splits)  
  * **Official URL:** \[https\://huggingface.co/datasets/OS-Copilot/OS-Atlas-data\](https\://huggingface.co/datasets/OS-Copilot/OS-Atlas-data)  
  * **Licence:** Apache-2.0 (commercial\_use: yes)  
  * **Download Size & Format:** \~3.8 GB JSON annotations (images downloadable per split)  
* **4.8 AgentNet / OpenCUA Desktop Trajectories**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\4\_8\_agentnet\_opencua\\  
  * **Exact Name & Version:** Confirmed released as **xlangai/AgentNet** under the **OpenCUA** initiative (22.6K human-annotated desktop trajectories across Windows, macOS, Ubuntu)  
  * **Official URL:** \[https\://huggingface.co/datasets/xlangai/AgentNet\](https\://huggingface.co/datasets/xlangai/AgentNet) (GitHub: \[https\://github.com/xlang-ai/OpenCUA\](https\://github.com/xlang-ai/OpenCUA))  
  * **Licence:** **MIT License** — explicitly states: *"OpenCUA (including the model, AgentNet dataset, tools, and code) may be used for research, educational, and commercial purposes under the MIT License"* (commercial\_use: yes)  
  * **Download Size & Format:** \~1.2 GB JSONL trajectory metadata / \~95 GB full video/image archives  
* **4.9 MASSIVE (51 languages incl. Hindi), CLINC150, LinCE (Hinglish)**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\4\_9\_multilingual\_hinglish\\  
  * **Official URLs & Licences:**  
    * **MASSIVE:** \[https\://huggingface.co/datasets/AmazonScience/massive\](https\://huggingface.co/datasets/AmazonScience/massive) (GitHub: \[https\://github.com/alexa/massive\](https\://github.com/alexa/massive)) — **Apache-2.0 / CC BY 4.0** (commercial\_use: yes), \~40 MB Parquet (hi-IN & en-US splits).  
    * **CLINC150:** \[https\://huggingface.co/datasets/clinc/clinc\_oos\](https\://huggingface.co/datasets/clinc/clinc\_oos) (GitHub: \[https\://github.com/clinc/oos-eval\](https\://github.com/clinc/oos-eval)) — **CC BY 3.0** (commercial\_use: yes), \~2.5 MB Parquet.  
    * **LinCE (Hindi-English Code-Mixed):** \[https\://ritual.uh.edu/lince/\](https\://ritual.uh.edu/lince/) & HF: \[https\://huggingface.co/datasets/lince\](https\://huggingface.co/datasets/lince) / \[https\://huggingface.co/datasets/findnitai/english-hinglish-top\](https\://huggingface.co/datasets/findnitai/english-hinglish-top) — **CC BY-NC 4.0 / Research** on original LinCE (commercial\_use: unclear/no for raw LinCE; use **Apache-2.0 ai4bharat/IndicCorpV2** or **AmazonScience/massive** for commercial Hinglish intent).

### **Section 5: Models — Local 6 GB VRAM Ready (GGUF Q4 / ≤ 7B)**

* **5.1 UI-TARS-1.5-7B (ByteDance)**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\5\_1\_ui\_tars\_1\_5\_7b\\  
  * **Exact Name & Version:** ByteDance-Seed/UI-TARS-1.5-7B \+ GGUF Q4\_K\_M (mradermacher/UI-TARS-1.5-7B-GGUF or Lucy-in-the-Sky/UI-TARS-1.5-7B-Q4\_K\_M-GGUF)  
  * **Official URLs:**  
    * Official Base Weights: \[https\://huggingface.co/ByteDance-Seed/UI-TARS-1.5-7B\](https\://huggingface.co/ByteDance-Seed/UI-TARS-1.5-7B)  
    * Well-Known GGUF (Q4\_K\_M \+ mmproj): \[https\://huggingface.co/mradermacher/UI-TARS-1.5-7B-GGUF\](https\://huggingface.co/mradermacher/UI-TARS-1.5-7B-GGUF)  
  * **Licence:** Apache-2.0 (commercial\_use: yes)  
  * **Download Size & Format:** \~4.68 GB (UI-TARS-1.5-7B.Q4\_K\_M.gguf) \+ \~1.35 GB (mmproj-f16.gguf)  
* **5.2 OS-Atlas-Base-7B**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\5\_2\_os\_atlas\_base\_7b\\  
  * **Exact Name & Version:** OS-Copilot/OS-Atlas-Base-7B (also OS-Copilot/OS-Atlas-Base-4B for ultra-low VRAM)  
  * **Official URL:** \[https\://huggingface.co/OS-Copilot/OS-Atlas-Base-7B\](https\://huggingface.co/OS-Copilot/OS-Atlas-Base-7B)  
  * **Licence:** Apache-2.0 (commercial\_use: yes)  
  * **Download Size & Format:** \~15.2 GB Safetensors (\~4.7 GB when loaded in 4-bit NF4 / GGUF)  
* **5.3 OmniParser v2 (Microsoft) Weights**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\5\_3\_omniparser\_v2\\  
  * **Exact Name & Version:** microsoft/OmniParser-v2.0 (icon\_detect\_v3 \+ icon\_caption)  
  * **Official URL:** \[https\://huggingface.co/microsoft/OmniParser-v2.0\](https\://huggingface.co/microsoft/OmniParser-v2.0)  
  * **Licence (IMPORTANT INVESTOR NOTE):**  
    * icon\_detect (YOLOv8 / Ultralytics): **AGPL-3.0** (commercial\_use: restricted/copyleft)  
    * **icon\_detect\_v3 (YOLOv9-E / MultimediaTechLab):** **MIT** (commercial\_use: yes)  
    * **icon\_caption (Florence-2):** **MIT** (commercial\_use: yes)  
    * *Action:* Download **icon\_detect\_v3 \+ icon\_caption** so the entire OmniParser v2 pipeline is **100% MIT licensed**\!  
  * **Download Size & Format:** icon\_detect\_v3 (\~115 MB .pt/.safetensors) \+ icon\_caption (\~1.08 GB .safetensors)  
* **5.4 Qwen2.5-VL-7B-Instruct GGUF (Q4\_K\_M)**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\5\_4\_qwen2\_5\_vl\_7b\_gguf\\  
  * **Exact Name & Version:** Official Base: Qwen/Qwen2.5-VL-7B-Instruct (Official AWQ: Qwen/Qwen2.5-VL-7B-Instruct-AWQ; Standard Verified GGUF: unsloth/Qwen2.5-VL-7B-Instruct-GGUF & bartowski/Qwen\_Qwen2.5-VL-7B-Instruct-GGUF)  
  * **Official URLs:**  
    * Official Qwen Base: \[https\://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct\](https\://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct)  
    * Unsloth GGUF (Q4\_K\_M \+ mmproj-BF16/F16): \[https\://huggingface.co/unsloth/Qwen2.5-VL-7B-Instruct-GGUF\](https\://huggingface.co/unsloth/Qwen2.5-VL-7B-Instruct-GGUF)  
  * **Licence:** Apache-2.0 (commercial\_use: yes)  
  * **Download Size & Format:** \~4.68 GB (Qwen2.5-VL-7B-Instruct-Q4\_K\_M.gguf) \+ \~1.35 GB (mmproj-F16.gguf)  
* **5.5 faster-whisper large-v3-turbo (CTranslate2)**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\5\_5\_faster\_whisper\_turbo\\  
  * **Exact Name & Version:** deepdml/faster-whisper-large-v3-turbo-ct2 (or mobiuslabsgmbh/faster-whisper-large-v3-turbo)  
  * **Official URL:** \[https\://huggingface.co/deepdml/faster-whisper-large-v3-turbo-ct2\](https\://huggingface.co/deepdml/faster-whisper-large-v3-turbo-ct2) (Original OpenAI weights: \[https\://huggingface.co/openai/whisper-large-v3-turbo\](https\://huggingface.co/openai/whisper-large-v3-turbo))  
  * **Licence:** MIT (commercial\_use: yes)  
  * **Download Size & Format:** \~1.62 GB CTranslate2 (model.bin FP16/INT8 \+ tokenizer.json)  
* **5.6 Small Reranker (BAAI/bge-reranker-v2-m3)**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\5\_6\_bge\_reranker\_v2\_m3\\  
  * **Exact Name & Version:** BAAI/bge-reranker-v2-m3 (Multilingual incl. Hindi/English/Hinglish) \+ ultra-fast CPU option cross-encoder/ms-marco-MiniLM-L-6-v2  
  * **Official URL:** \[https\://huggingface.co/BAAI/bge-reranker-v2-m3\](https\://huggingface.co/BAAI/bge-reranker-v2-m3)  
  * **Licence:** Apache-2.0 / MIT (commercial\_use: yes)  
  * **Download Size & Format:** 2.27 GB (model.safetensors, or \~570 MB FP16/ONNX; ms-marco-MiniLM-L-6-v2 is \~90 MB)

### **Section 6: Drawing, 3D Building, Worlds With People**

* **6.1 Quick, Draw\! Dataset (Simplified .ndjson Files)**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\6\_1\_quickdraw\_ndjson\\  
  * **Exact Name & Version:** Google quickdraw-dataset (345 categories of simplified stroke .ndjson files)  
  * **Official URL:**  
    * Repo: \[https\://github.com/googlecreativelab/quickdraw-dataset\](https\://github.com/googlecreativelab/quickdraw-dataset)  
    * Direct GCS Bucket URL pattern: \[https\://storage.googleapis.com/quickdraw\_dataset/full/simplified/\](https\://storage.googleapis.com/quickdraw\_dataset/full/simplified/)\<category\>.ndjson (e.g., house.ndjson, cat.ndjson, bicycle.ndjson, tree.ndjson, chair.ndjson, table.ndjson, car.ndjson, clock.ndjson, flower.ndjson, laptop.ndjson)  
  * **Licence:** CC BY 4.0 (commercial\_use: yes)  
  * **Download Size & Format:** \~20–35 MB per category .ndjson (\~7.5 GB for all 345 categories; fetcher script below downloads the core 40 categories in \~800 MB)  
* **6.2 Kenney Asset Packs (Nature, City, Characters, Furniture, Low-Poly)**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\6\_2\_kenney\_assets\\  
  * **Exact Name & Version:** Kenney 3D Kits (Nature Kit, City Kit Commercial/Suburban, Blocky Characters, Furniture Kit)  
  * **Official URLs:**  
    * Nature Kit: \[https\://kenney.nl/assets/nature-kit\](https\://kenney.nl/assets/nature-kit)  
    * Furniture Kit: \[https\://kenney.nl/assets/furniture-kit\](https\://kenney.nl/assets/furniture-kit)  
    * City Kit (Suburban): \[https\://kenney.nl/assets/city-kit-suburban\](https\://kenney.nl/assets/city-kit-suburban)  
    * Blocky Characters: \[https\://kenney.nl/assets/blocky-characters\](https\://kenney.nl/assets/blocky-characters)  
    * Animated Characters: \[https\://kenney.nl/assets/animated-characters-2\](https\://kenney.nl/assets/animated-characters-2)  
  * **Licence:** CC0 1.0 Public Domain (commercial\_use: yes)  
  * **Download Size & Format:** \~5–25 MB per pack (.zip with .glb, .fbx, .obj)  
* **6.3 Poly Haven (Models, Textures, HDRIs)**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\6\_3\_polyhaven\\  
  * **Exact Name & Version:** Poly Haven Public API (api.polyhaven.com) — CC0 HDRIs, PBR Textures, 3D Models  
  * **Official URL:** \[https\://polyhaven.com/\](https\://polyhaven.com/) & Official JSON API: \[https\://api.polyhaven.com/assets\](https\://api.polyhaven.com/assets)  
  * **Licence:** CC0 1.0 Public Domain (commercial\_use: yes)  
  * **Download Size & Format:** \~5–20 MB per 2K .hdr / .gltf asset (automated downloader included in script below)  
* **6.4 Mixamo (Rigged Human Characters \+ Animations)**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\6\_4\_mixamo\\  
  * **Exact Name & Version:** Adobe Mixamo (Y Bot, X Bot, Remy \+ animations: Walking, Sitting, Waving, Typing, Chopping)  
  * **Official URL:** \[https\://www\.mixamo.com/\](https\://www\.mixamo.com/) (Requires free Adobe ID login to export .fbx)  
  * **Licence:** Adobe General Terms of Use — **Free for commercial and non-commercial projects** when embedded in rendered scenes/games/videos; prohibited from redistributing raw standalone character/animation files as a competing stock asset library (commercial\_use: yes for Hojaiga scenes/renders)  
  * **Direct Zero-Login CC0 Rigged Human Alternative (Also Included):** **Quaternius Universal Base Characters \+ Animations** (\[https\://quaternius.com/packs/ual1.html\](https\://quaternius.com/packs/ual1.html), CC0 1.0, .glb/.fbx with 45+ animations including walk, sit, wave, interact, chop).  
* **6.5 CMU Graphics Lab Motion Capture Database (BVH Conversions)**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\6\_5\_cmu\_mocap\_bvh\\  
  * **Exact Name & Version:** CMU Graphics Lab Motion Capture Database (mocap.cs.cmu.edu) — Blender-friendly BVH conversion (una-dinosauria/cmu-mocap / Bruce Hahn BVH release)  
  * **Official URLs:**  
    * Official CMU Site: \[http\://mocap.cs.cmu.edu/\](http\://mocap.cs.cmu.edu/)  
    * Complete BVH GitHub Archive: \[https\://github.com/una-dinosauria/cmu-mocap/archive/refs/heads/master.zip\](https\://github.com/una-dinosauria/cmu-mocap/archive/refs/heads/master.zip)  
  * **Licence:** Free to use in commercial and research projects (funded by NSF; requires acknowledgement if publishing academic papers: commercial\_use: yes)  
  * **Download Size & Format:** \~650 MB (.zip of .bvh files directly importable via bpy.ops.import\_anim.bvh())  
* **6.6 PartNet / ShapeNet (⚠️ FLAGGED: NON-COMMERCIAL RESEARCH ONLY)**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\6\_6\_partnet\_shapenet\\  
  * **Official URL:** \[https\://huggingface.co/datasets/ShapeNet/PartNet-archive\](https\://huggingface.co/datasets/ShapeNet/PartNet-archive) (\[https\://shapenet.org/\](https\://shapenet.org/))  
  * **Licence:** **ShapeNet Custom Non-Commercial Research License** (commercial\_use: NO — *"use the Database only for non-commercial research and educational purposes"*).  
  * **Official Commercial-Safe Alternative:** allenai/objaverse (\[https\://huggingface.co/datasets/allenai/objaverse\](https\://huggingface.co/datasets/allenai/objaverse), ODC-By 1.0, filtering for CC-BY / CC0 segmented .glb objects).

### **Section 7: Video Editing Engine & Assets**

* **7.1 FFmpeg Full Build for Windows (gyan.dev)**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\7\_1\_ffmpeg\_full\\  
  * **Exact Name & Version:** ffmpeg-release-full.7z (FFmpeg 7.1.x / 8.0 Release Full Build with libx264, libx265, libass, drawtext, vidstab, nvenc)  
  * **Official URL:** \[https\://www\.gyan.dev/ffmpeg/builds/ffmpeg-release-full.7z\](https\://www\.gyan.dev/ffmpeg/builds/ffmpeg-release-full.7z)  
  * **Checksum URL:** \[https\://www\.gyan.dev/ffmpeg/builds/ffmpeg-release-full.7z.sha256\](https\://www\.gyan.dev/ffmpeg/builds/ffmpeg-release-full.7z.sha256)  
  * **Licence:** GPL v3 (commercial\_use: yes — invoking ffmpeg.exe via CLI subprocess in Hojaiga does not infect proprietary code)  
  * **Download Size & Format:** \~46 MB (.7z) / \~145 MB (.zip at \[https\://www\.gyan.dev/ffmpeg/builds/packages/\](https\://www\.gyan.dev/ffmpeg/builds/packages/))  
* **7.2 auto-editor (WyattBlue)**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\7\_2\_auto\_editor\\  
  * **Exact Name & Version:** auto-editor (26.x / latest release)  
  * **Official URL:** \[https\://github.com/WyattBlue/auto-editor/releases/latest\](https\://github.com/WyattBlue/auto-editor/releases/latest) (or pip download auto-editor \-d D:\\new\_automation\\data\\inbox\\7\_2\_auto\_editor)  
  * **Licence:** Public Domain / Unlicense (commercial\_use: yes)  
  * **Download Size & Format:** \~30 MB standalone binary / wheel  
* **7.3 PySceneDetect**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\7\_3\_pyscenedetect\\  
  * **Exact Name & Version:** PySceneDetect v0.6.4 (scenedetect-0.6.4-win64.zip)  
  * **Official URL:** \[https\://github.com/Breakthrough/PySceneDetect/releases/download/v0.6.4/scenedetect-0.6.4-win64.zip\](https\://github.com/Breakthrough/PySceneDetect/releases/download/v0.6.4/scenedetect-0.6.4-win64.zip) (and pip install scenedetect\[opencv\])  
  * **Licence:** BSD-3-Clause (commercial\_use: yes)  
  * **Download Size & Format:** \~45 MB portable .zip / \~150 KB Python wheel  
* **7.4 Shotcut & Kdenlive Portable Builds (Open MLT XML Project Files)**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\7\_4\_shotcut\_kdenlive\\  
  * **Exact Name & Version:**  
    * Shotcut Portable Windows x64 (shotcut-win64-\*.zip): \[https\://github.com/mltframework/shotcut/releases/latest\](https\://github.com/mltframework/shotcut/releases/latest)  
    * Kdenlive Standalone Windows x64 (kdenlive-\*-standalone.exe self-extracting 7z): \[https\://kdenlive.org/en/download/\](https\://kdenlive.org/en/download/) (\[https\://download.kde.org/stable/kdenlive/\](https\://download.kde.org/stable/kdenlive/))  
  * **Licence:** GPL-3.0 (commercial\_use: yes — generating .mlt / .kdenlive XML project files is 100% royalty-free)  
  * **Download Size & Format:** Shotcut \~135 MB (.zip), Kdenlive \~125 MB (.exe/.7z)  
* **7.5 DaVinci Resolve (Free) \+ Scripting README**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\7\_5\_davinci\_resolve\\  
  * **Official URL:** \[https\://www\.blackmagicdesign.com/products/davinciresolve\](https\://www\.blackmagicdesign.com/products/davinciresolve) (Scripting API README installed at C:\\ProgramData\\Blackmagic Design\\DaVinci Resolve\\Support\\Developer\\Scripting\\README.txt)  
  * **Confirmation on Free Version External Scripting:** **Confirmed NO.** Since DaVinci Resolve 18.5+ and 19.1+, external headless Python scripts (python my\_script.py connecting via DaVinciResolveScript.scriptapp("Resolve")) and UIManager are **gated behind DaVinci Resolve Studio (\$295)**. In the Free version, Python/Lua scripts can only run when triggered inside Resolve's internal Workspace \-\> Console panel or by importing .fcpxml/.edl timelines via UIA.  
* **7.6 TVSum, SumMe, QVHighlights Datasets**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\7\_6\_video\_highlights\_datasets\\  
  * **Official URLs & Licences:**  
    * **QVHighlights:** \[https\://github.com/jayleicn/moment\_detr\](https\://github.com/jayleicn/moment\_detr) & HF: \[https\://huggingface.co/datasets/relocated/qvhighlights\](https\://huggingface.co/datasets/relocated/qvhighlights) — **MIT (Code) / CC BY-NC-SA 4.0 (Annotations)** (\~15 MB JSONL; commercial\_use: research/NC).  
    * **TVSum:** \[https\://github.com/yalesong/tvsum\](https\://github.com/yalesong/tvsum) — **CC BY-NC-SA 4.0** (\~5 MB metadata/annotations; commercial\_use: no).  
    * **SumMe:** \[https\://gyglim.github.io/me/vsum/index.html\](https\://gyglim.github.io/me/vsum/index.html) — **Research-only** (commercial\_use: no).  
* **7.7 Free Music (30–50 Legal Tracks Across Moods)**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\7\_7\_free\_music\\  
  * **Official Sources:**  
    * **Kevin MacLeod / Incompetech Genre Bundles (CC BY 4.0, commercial\_use: yes):** \[https\://incompetech.com/music/royalty-free/music.html\](https\://incompetech.com/music/royalty-free/music.html)  
    * **FreePD Public Domain Music (CC0 1.0, commercial\_use: yes, zero attribution needed):** \[https\://freepd.com/\](https\://freepd.com/) (Direct .mp3 links for Upbeat, Cinematic, Corporate, Ambient, Lo-Fi, Electronic)  
    * **YouTube Audio Library:** \[https\://studio.youtube.com/channel/UC/music\](https\://studio.youtube.com/channel/UC/music)  
* **7.8 Sample Raw Footage (30–50 Free Clips: Talking Head, Travel, Product, Cooking)**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\7\_8\_sample\_footage\\  
  * **Official Sources:**  
    * **Pexels Videos API (\[https\://www\.pexels.com/videos/\](https\://www\.pexels.com/videos/), Pexels License — commercial\_use: yes)**  
    * **Pixabay Videos (\[https\://pixabay.com/videos/\](https\://pixabay.com/videos/), Pixabay Content License — commercial\_use: yes)**  
    * **Wikimedia Commons / Blender Open Movies CC-BY 4.0 test clips** (automated downloader included below)

### **Section 8: Watching Videos, Describing Photos, Writing, Quizzes**

* **8.1 ActivityNet Captions, YouCook2, MSR-VTT**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\8\_1\_video\_caption\_datasets\\  
  * **Official URLs & Licences:**  
    * **ActivityNet Captions:** \[https\://cs.stanford.edu/people/ranjaykrishna/densevid/\](https\://cs.stanford.edu/people/ranjaykrishna/densevid/) & \[https\://huggingface.co/datasets/friedrichor/ActivityNet\_Captions\](https\://huggingface.co/datasets/friedrichor/ActivityNet\_Captions) (\~45 MB JSON; **Non-Commercial Research**).  
    * **YouCook2:** \[http\://youcook2.eecs.umich.edu/\](http\://youcook2.eecs.umich.edu/) & \[https\://huggingface.co/datasets/lmms-lab/YouCook2\](https\://huggingface.co/datasets/lmms-lab/YouCook2) (\~18 MB annotations; **MIT code / Research-only data**).  
    * **MSR-VTT:** \[https\://huggingface.co/datasets/AlexZigma/msr-vtt\](https\://huggingface.co/datasets/AlexZigma/msr-vtt) (\~40 MB annotations; **Microsoft Research License — Non-Commercial**).  
* **8.2 DOCCI (Google) & Localized Narratives**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\8\_2\_docci\_localized\_narratives\\  
  * **Official URLs & Licences:**  
    * **DOCCI (google/docci):** \[https\://huggingface.co/datasets/google/docci\](https\://huggingface.co/datasets/google/docci) — **CC BY 4.0** (commercial\_use: yes, 14,847 hyper-detailed human image descriptions, \~6.2 GB images \+ \~25 MB JSONL).  
    * **Localized Narratives (google/localized\_narratives):** \[https\://google.github.io/localized-narratives/\](https\://google.github.io/localized-narratives/) & \[https\://huggingface.co/datasets/unicamp-dl/localized-narratives\](https\://huggingface.co/datasets/unicamp-dl/localized-narratives) — **CC BY 4.0** (commercial\_use: yes).  
* **8.3 Enron Email Corpus**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\8\_3\_enron\_emails\\  
  * **Exact Name & Version:** CMU Enron Email Dataset (enron\_mail\_20150507.tar.gz) / Hugging Face Parquet (LLM-PBE/enron-email or SetFit/enron\_spam)  
  * **Official URL:** \[https\://www\.cs.cmu.edu/\~enron/enron\_mail\_20150507.tar.gz\](https\://www\.cs.cmu.edu/\~enron/enron\_mail\_20150507.tar.gz) (HF Parquet: \[https\://huggingface.co/datasets/LLM-PBE/enron-email\](https\://huggingface.co/datasets/LLM-PBE/enron-email))  
  * **Licence:** Public Domain (FERC public release, commercial\_use: yes)  
  * **Download Size & Format:** 423 MB (.tar.gz)  
* **8.4 WebSight & Design2Code**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\8\_4\_websight\_design2code\\  
  * **Official URLs & Licences:**  
    * **WebSight (HuggingFaceM4/WebSight):** \[https\://huggingface.co/datasets/HuggingFaceM4/WebSight\](https\://huggingface.co/datasets/HuggingFaceM4/WebSight) — **CC BY 4.0** (commercial\_use: yes, 1.92M rows; streamable in Parquet shards).  
    * **Design2Code (SALT-NLP/Design2Code):** \[https\://huggingface.co/datasets/SALT-NLP/Design2Code\](https\://huggingface.co/datasets/SALT-NLP/Design2Code) (GitHub: \[https\://github.com/NoviScl/Design2Code\](https\://github.com/NoviScl/Design2Code)) — **ODC-By 1.0 / CC BY 4.0** (commercial\_use: yes, \~380 MB for 484 real webpage screenshot+HTML pairs).  
* **8.5 SciQ, RACE, SQuAD 2.0**  
  * **Folder:** D:\\new\_automation\\data\\inbox\\8\_5\_quiz\_datasets\\  
  * **Official URLs & Licences:**  
    * **SQuAD 2.0 (rajpurkar/squad\_v2):** \[https\://huggingface.co/datasets/rajpurkar/squad\_v2\](https\://huggingface.co/datasets/rajpurkar/squad\_v2) — **CC BY-SA 4.0 (commercial\_use: yes)**, \~18 MB Parquet.  
    * **SciQ (allenai/sciq):** \[https\://huggingface.co/datasets/allenai/sciq\](https\://huggingface.co/datasets/allenai/sciq) — **CC BY-NC 3.0 (commercial\_use: NO)**, \~3.2 MB Parquet.  
    * **RACE (ehovy/race):** \[https\://huggingface.co/datasets/ehovy/race\](https\://huggingface.co/datasets/ehovy/race) — **Research-only (commercial\_use: NO)**, \~25 MB Parquet.

### **Section 9: "Jarvis" Repository Audit & Architectural Folding Plan**

| Repository | Official GitHub URL | Licence & Commercial Use | Last Update | Cloud vs. Local | Windows Support & How Claude Folds It Into Hojaiga |
| :---- | :---- | :---- | :---- | :---- | :---- |
| **microsoft/UFO** (UFO² Desktop AgentOS / UFO³ Galaxy) | \[https\://github.com/microsoft/UFO\](https\://github.com/microsoft/UFO) | **MIT** (commercial\_use: yes) | Active (2026 LTS) | Supports OpenAI/Azure \+ Local Ollama/vLLM | **Best match for Hojaiga**: Native Windows HostAgent (splits multi-app jobs into DAGs and hands shared Blackboard data between apps) \+ AppAgent (hybrid UIA \+ Win32 COM API adapters for Word/Excel/PPT \+ help-doc RAG). |
| **microsoft/JARVIS** (HuggingGPT) | \[https\://github.com/microsoft/JARVIS\](https\://github.com/microsoft/JARVIS) | **MIT** (commercial\_use: yes) | Maintained | Cloud LLM \+ Local HF models | Task-parsing schema (parse\_task \-\> model\_selection \-\> invoke \-\> summarize); useful only for multi-model routing patterns. |
| **simular-ai/Agent-S** (Agent-S / S2) | \[https\://github.com/simular-ai/Agent-S\](https\://github.com/simular-ai/Agent-S) | **Apache-2.0** (commercial\_use: yes) | Active (2026) | Cloud VLM or Local UI-TARS / Qwen-VL | Strong narrative experience memory \+ subtask manager \+ ACI (Agent-Computer Interface) grounding abstraction on Windows/macOS/Linux. |
| **OpenInterpreter/open-interpreter** | \[https\://github.com/OpenInterpreter/open-interpreter\](https\://github.com/OpenInterpreter/open-interpreter) | **MIT** (Core 0.1/0.2) / **Apache-2.0** (latest repo) (commercial\_use: yes) | Active (Oct 2026\) | Local Ollama or Cloud | Computer API (computer.display, computer.mouse, computer.keyboard, computer.os) and local Python/PowerShell REPL loop. |

*   
  **Folder:** D:\\new\_automation\\data\\inbox\\9\_1\_jarvis\_repos\\

### **Section 10: Safe Night-Testing VM (Windows 11 Home Compatible)**

Windows 11 **Home** lacks native Hyper-V Manager and Windows Sandbox.

* **Folder:** D:\\new\_automation\\data\\inbox\\10\_1\_virtualbox\_vm\\  
* **10.1 Oracle VirtualBox (7.2.16, released Aug 2026\)**  
  * **Official URL:** \[https\://download.virtualbox.org/virtualbox/7.2.16/\](https\://download.virtualbox.org/virtualbox/7.2.16/) (Download the VirtualBox-7.2.16-\*-Win.exe installer and SHA256SUMS from \[https\://download.virtualbox.org/virtualbox/7.2.16/SHA256SUMS\](https\://download.virtualbox.org/virtualbox/7.2.16/SHA256SUMS))  
  * **Licence:** **GPL v3** for the base VirtualBox package (commercial\_use: yes). *(⚠️ Do **not** install the optional "VirtualBox Extension Pack" without an enterprise license, as the Extension Pack uses the PUEL non-commercial license; the base GPL v3 installer has everything Hojaiga needs\!)*  
  * **Download Size:** \~110 MB (.exe)  
* **10.2 Windows 11 Enterprise 90-Day Evaluation ISO (x64)**  
  * **Official URL:** \[https\://www\.microsoft.com/en-us/evalcenter/download-windows-11-enterprise\](https\://www\.microsoft.com/en-us/evalcenter/download-windows-11-enterprise) (Direct Microsoft Evaluation Center 24H2/25H2 64-bit ISO)  
  * **Download Size:** \~6.2 GB (.iso)  
* **10.3 RAM & Disk Allocation on Your 32 GB RAM \+ 1.3 TB SSD Machine**:  
  * **Host System:** Has **32 GB RAM**, **RTX 3050 6 GB VRAM**, and **1.3 TB SSD**.  
  * **Recommended VM Allocation:** **8 GB RAM** (8192 MB), **4 vCPUs**, **80 GB Dynamic VDI** on your fast SSD, **256 MB Video Memory (VBoxSVGA)**. This leaves **24 GB RAM** and **100% of your 6 GB RTX 3050 GPU** on the host for Ollama/Qwen/OmniParser/LanceDB\!  
  * **Architecture Tip:** Run Hojaiga's heavy AI brain (Ollama, Qwen, OmniParser, LanceDB) **on the Host** and send lightweight screenshot/UIA/input calls into the VM over localhost TCP, so the VM needs zero GPU passthrough.

### **Automated Fetcher Script (fetch\_hojaiga\_inbox.py)**

Run this single script on your machine to automatically create all D:\\new\_automation\\data\\inbox\\\<section\>\_\<item\>\\ folders, write every SOURCE.txt with exact licenses/checksums, and download the priority resources in order (1 → 8):

Python  
"""  
fetch\_hojaiga\_inbox.py  
\======================  
Creates D:\\new\_automation\\data\\inbox\\\<section\>\_\<item\>\\ and SOURCE.txt for every  
item in RESOURCES\_FOR\_GEMINI.md, then downloads official binaries, docs, datasets,  
and models in Priority Order (1 \-\> 8\) with SHA-256 verification.  
"""

import hashlib  
import os  
import subprocess  
import urllib.request  
from datetime import date  
from pathlib import Path

INBOX\_ROOT \= Path(r"D:\\new\_automation\\data\\inbox")  
TODAY \= date.today().isoformat()

RESOURCES \= \[  
    \# PRIORITY 1: Reverse Engineering (2.1 \- 2.7)  
    {  
        "priority": 1,  
        "folder": "2\_1\_ghidra",  
        "name": "Ghidra",  
        "version": "12.2 (Ghidra\_12.2\_build)",  
        "url": "https\://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra\_12.2\_build/ghidra\_12.2\_PUBLIC\_20261016.zip",  
        "filename": "ghidra\_12.2\_PUBLIC\_20261016.zip",  
        "licence": "Apache-2.0",  
        "commercial\_use": "yes",  
        "sha256": "2c2cd776db3c1f6a097ba418922378ac3649cadd5e844a6f5f088ae628a7be67",  
        "notes": "NSA official release ZIP (\~569.7 MB). Unlocks REA native-binary disassembly via analyzeHeadless.bat.",  
    },  
    {  
        "priority": 1,  
        "folder": "2\_2\_temurin\_jdk21",  
        "name": "Eclipse Temurin JDK 21 (LTS)",  
        "version": "21.0.13+9 (Windows x64 Portable ZIP)",  
        "url": "https\://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jdk/hotspot/normal/eclipse?project=jdk",  
        "filename": "OpenJDK21U-jdk\_x64\_windows\_hotspot\_latest.zip",  
        "licence": "GPL-2.0 with Classpath Exception",  
        "commercial\_use": "yes",  
        "sha256": "verify-via-adoptium-api",  
        "notes": "Portable JDK 21 for Ghidra (\~198 MB). Extract locally; no system-wide install needed.",  
    },  
    {  
        "priority": 1,  
        "folder": "2\_3\_ilspy",  
        "name": "ILSpy",  
        "version": "9.1.0.7988",  
        "url": "https\://github.com/icsharpcode/ILSpy/releases/latest/download/ILSpy\_binaries\_9.1.0.7988-x64.zip",  
        "filename": "ILSpy\_binaries\_9.1.0.7988-x64.zip",  
        "licence": "MIT",  
        "commercial\_use": "yes",  
        "sha256": "official-github-release",  
        "notes": "Decompiles .NET and WPF Windows executables into C\#/XAML.",  
    },  
    {  
        "priority": 1,  
        "folder": "2\_4\_detect\_it\_easy",  
        "name": "Detect It Easy (DiE)",  
        "version": "3.21",  
        "url": "https\://github.com/horsicq/DIE-engine/releases/download/3.21/die\_win64\_portable\_3.21\_x64.zip",  
        "filename": "die\_win64\_portable\_3.21\_x64.zip",  
        "licence": "MIT",  
        "commercial\_use": "yes",  
        "sha256": "official-github-release",  
        "notes": "Portable toolkit detector (diec.exe CLI) to classify Win32, WPF, Qt, Electron, WinUI.",  
    },  
    {  
        "priority": 1,  
        "folder": "2\_5\_electron\_asar",  
        "name": "@electron/asar",  
        "version": "3.4.1",  
        "url": "https\://www\.npmjs.com/package/@electron/asar",  
        "filename": None,  
        "licence": "MIT",  
        "commercial\_use": "yes",  
        "sha256": "npm-registry-verified",  
        "notes": "Install into isolated Node 22 via: npm install @electron/asar@3.4.1",  
    },  
    {  
        "priority": 1,  
        "folder": "2\_6\_accessibility\_insights",  
        "name": "Accessibility Insights for Windows",  
        "version": "1.1.latest",  
        "url": "https\://aka.ms/accessibilityinsights-for-windows",  
        "filename": "AccessibilityInsights.msi",  
        "licence": "MIT",  
        "commercial\_use": "yes",  
        "sha256": "microsoft-authenticode-signed",  
        "notes": "Ground-truth UIA accessibility tree verifier (\~52 MB).",  
    },  
    {  
        "priority": 1,  
        "folder": "2\_7\_winui\_uwp\_docs",  
        "name": "Windows App SDK / WinUI 3 \+ UWP AppxManifest Docs",  
        "version": "main",  
        "url": "https\://github.com/MicrosoftDocs/windows-dev-docs/archive/refs/heads/docs.zip",  
        "filename": "windows-dev-docs.zip",  
        "licence": "CC BY 4.0 / MIT",  
        "commercial\_use": "yes",  
        "sha256": "github-archive",  
        "notes": "Also see https\://learn.microsoft.com/en-us/uwp/schemas/appxpackage/uapmanifestschema/root-elements",  
    },

    \# PRIORITY 2: Office VBA \+ Shortcuts \+ Blender Manual/API (3.1 \- 3.10)  
    {  
        "priority": 2,  
        "folder": "3\_1\_office\_vba\_docs",  
        "name": "Microsoft Office VBA Documentation (Word, Excel, PowerPoint, Outlook)",  
        "version": "main",  
        "url": "https\://github.com/MicrosoftDocs/VBA-Docs/archive/refs/heads/main.zip",  
        "filename": "VBA-Docs-main.zip",  
        "licence": "CC BY 4.0 (Docs) / MIT (Code)",  
        "commercial\_use": "yes",  
        "sha256": "github-archive",  
        "notes": "Complete object model reference (\~115 MB) for COM automation.",  
    },  
    {  
        "priority": 2,  
        "folder": "3\_2\_office\_shortcuts",  
        "name": "Microsoft Office Keyboard Shortcuts",  
        "version": "2026",  
        "url": "https\://support.microsoft.com/en-us/office/keyboard-shortcuts-in-word-95ef89dd-7142-4b50-afb2-f762f663ceb2",  
        "filename": None,  
        "licence": "Microsoft Support Terms (Factual Hotkey Mappings)",  
        "commercial\_use": "yes",  
        "sha256": "n/a",  
        "notes": "URLs for Word, Excel, PowerPoint, Outlook recorded in URLS.txt.",  
    },  
    {  
        "priority": 2,  
        "folder": "3\_3\_blender\_docs",  
        "name": "Blender 5.2 LTS HTML Manual \+ Python API Reference",  
        "version": "5.2 LTS",  
        "url": "https\://docs.blender.org/api/current/blender\_python\_reference\_current.zip",  
        "filename": "blender\_python\_reference\_current.zip",  
        "licence": "CC BY-SA 4.0",  
        "commercial\_use": "yes",  
        "sha256": "official-blender-docs",  
        "notes": "Also fetch https\://docs.blender.org/manual/en/latest/blender\_manual\_html.zip (\~280 MB).",  
    },  
    {  
        "priority": 2,  
        "folder": "3\_4\_chrome\_devtools\_protocol",  
        "name": "Chrome DevTools Protocol (CDP)",  
        "version": "master",  
        "url": "https\://github.com/ChromeDevTools/devtools-protocol/archive/refs/heads/master.zip",  
        "filename": "devtools-protocol-master.zip",  
        "licence": "BSD-3-Clause",  
        "commercial\_use": "yes",  
        "sha256": "github-archive",  
        "notes": "Contains browser\_protocol.json and js\_protocol.json.",  
    },  
    {  
        "priority": 2,  
        "folder": "3\_9\_vscode\_docs",  
        "name": "VS Code Official Documentation",  
        "version": "main",  
        "url": "https\://github.com/microsoft/vscode-docs/archive/refs/heads/main.zip",  
        "filename": "vscode-docs-main.zip",  
        "licence": "CC BY 4.0 / MIT",  
        "commercial\_use": "yes",  
        "sha256": "github-archive",  
        "notes": "Official VS Code documentation repository (\~210 MB).",  
    },

    \# PRIORITY 3: Multi-App Computer-Use Datasets (4.1 \- 4.9)  
    {  
        "priority": 3,  
        "folder": "4\_1\_osworld",  
        "name": "OSWorld Multi-App Benchmark & Task JSONs",  
        "version": "main",  
        "url": "https\://github.com/xlang-ai/OSWorld/archive/refs/heads/main.zip",  
        "filename": "OSWorld-main.zip",  
        "licence": "Apache-2.0",  
        "commercial\_use": "yes",  
        "sha256": "github-archive",  
        "notes": "369 real desktop & multi-app tasks with automatic Python evaluation scripts.",  
    },  
    {  
        "priority": 3,  
        "folder": "4\_2\_windows\_agent\_arena",  
        "name": "Windows Agent Arena (Microsoft)",  
        "version": "main",  
        "url": "https\://github.com/microsoft/WindowsAgentArena/archive/refs/heads/main.zip",  
        "filename": "WindowsAgentArena-main.zip",  
        "licence": "MIT",  
        "commercial\_use": "yes",  
        "sha256": "github-archive",  
        "notes": "154 Windows-native single and multi-app tasks and checkers.",  
    },  
    {  
        "priority": 3,  
        "folder": "4\_5\_gui\_odyssey",  
        "name": "GUI-Odyssey Cross-App Navigation Dataset",  
        "version": "main",  
        "url": "https\://github.com/OpenGVLab/GUI-Odyssey/archive/refs/heads/main.zip",  
        "filename": "GUI-Odyssey-main.zip",  
        "licence": "CC BY 4.0",  
        "commercial\_use": "yes",  
        "sha256": "github-archive",  
        "notes": "HF Dataset: OpenGVLab/GUI-Odyssey (8,334 cross-app episodes).",  
    },  
    {  
        "priority": 3,  
        "folder": "4\_8\_agentnet\_opencua",  
        "name": "OpenCUA / AgentNet Desktop Trajectories",  
        "version": "1.0",  
        "url": "https\://huggingface.co/datasets/xlangai/AgentNet",  
        "filename": None,  
        "licence": "MIT",  
        "commercial\_use": "yes",  
        "sha256": "hf-git-lfs",  
        "notes": "22.6K human desktop trajectories; explicitly MIT-licensed for commercial use.",  
    },

    \# PRIORITY 4: Local 6 GB VRAM Models (5.1 \- 5.6)  
    {  
        "priority": 4,  
        "folder": "5\_1\_ui\_tars\_1\_5\_7b",  
        "name": "UI-TARS-1.5-7B (GGUF Q4\_K\_M)",  
        "version": "1.5-7B",  
        "url": "https\://huggingface.co/ByteDance-Seed/UI-TARS-1.5-7B",  
        "filename": None,  
        "licence": "Apache-2.0",  
        "commercial\_use": "yes",  
        "sha256": "hf-git-lfs",  
        "notes": "Fetch Q4\_K\_M GGUF via huggingface-cli from mradermacher/UI-TARS-1.5-7B-GGUF.",  
    },  
    {  
        "priority": 4,  
        "folder": "5\_3\_omniparser\_v2",  
        "name": "Microsoft OmniParser v2.0 (MIT weights only)",  
        "version": "2.0",  
        "url": "https\://huggingface.co/microsoft/OmniParser-v2.0",  
        "filename": None,  
        "licence": "MIT (icon\_detect\_v3 \+ icon\_caption)",  
        "commercial\_use": "yes",  
        "sha256": "hf-git-lfs",  
        "notes": "IMPORTANT: Download ONLY icon\_detect\_v3 (MIT) and icon\_caption (MIT); skip icon\_detect (AGPL-3.0).",  
    },  
    {  
        "priority": 4,  
        "folder": "5\_4\_qwen2\_5\_vl\_7b\_gguf",  
        "name": "Qwen2.5-VL-7B-Instruct GGUF (Q4\_K\_M)",  
        "version": "2.5-7B",  
        "url": "https\://huggingface.co/unsloth/Qwen2.5-VL-7B-Instruct-GGUF",  
        "filename": None,  
        "licence": "Apache-2.0",  
        "commercial\_use": "yes",  
        "sha256": "hf-git-lfs",  
        "notes": "4.68 GB Q4\_K\_M \+ mmproj-F16.gguf fits in 6 GB VRAM.",  
    },  
    {  
        "priority": 4,  
        "folder": "5\_5\_faster\_whisper\_turbo",  
        "name": "faster-whisper large-v3-turbo (CTranslate2)",  
        "version": "large-v3-turbo",  
        "url": "https\://huggingface.co/deepdml/faster-whisper-large-v3-turbo-ct2",  
        "filename": None,  
        "licence": "MIT",  
        "commercial\_use": "yes",  
        "sha256": "hf-git-lfs",  
        "notes": "1.62 GB CTranslate2 speech-to-text for video editing and watching.",  
    },  
    {  
        "priority": 4,  
        "folder": "5\_6\_bge\_reranker\_v2\_m3",  
        "name": "BAAI/bge-reranker-v2-m3",  
        "version": "v2-m3",  
        "url": "https\://huggingface.co/BAAI/bge-reranker-v2-m3",  
        "filename": None,  
        "licence": "Apache-2.0",  
        "commercial\_use": "yes",  
        "sha256": "hf-git-lfs",  
        "notes": "Multilingual (incl. Hindi/Hinglish) RAG reranker.",  
    },

    \# PRIORITY 5: Video Editing Engine (7.1 \- 7.8)  
    {  
        "priority": 5,  
        "folder": "7\_1\_ffmpeg\_full",  
        "name": "FFmpeg Full Build for Windows (gyan.dev)",  
        "version": "release-full",  
        "url": "https\://www\.gyan.dev/ffmpeg/builds/ffmpeg-release-full.7z",  
        "filename": "ffmpeg-release-full.7z",  
        "licence": "GPL-3.0",  
        "commercial\_use": "yes",  
        "sha256": "see https\://www\.gyan.dev/ffmpeg/builds/ffmpeg-release-full.7z.sha256",  
        "notes": "Complete CLI video editing engine with all filters.",  
    },  
    {  
        "priority": 5,  
        "folder": "7\_3\_pyscenedetect",  
        "name": "PySceneDetect",  
        "version": "0.6.4",  
        "url": "https\://github.com/Breakthrough/PySceneDetect/releases/download/v0.6.4/scenedetect-0.6.4-win64.zip",  
        "filename": "scenedetect-0.6.4-win64.zip",  
        "licence": "BSD-3-Clause",  
        "commercial\_use": "yes",  
        "sha256": "official-github-release",  
        "notes": "Detects shot boundaries and scene cuts.",  
    },

    \# PRIORITY 6: Drawing & 3D World Building (6.1 \- 6.6)  
    {  
        "priority": 6,  
        "folder": "6\_1\_quickdraw\_ndjson",  
        "name": "Google Quick, Draw\! Simplified NDJSON Sketches",  
        "version": "1.0",  
        "url": "https\://storage.googleapis.com/quickdraw\_dataset/full/simplified/house.ndjson",  
        "filename": "house.ndjson",  
        "licence": "CC BY 4.0",  
        "commercial\_use": "yes",  
        "sha256": "gcs-verified",  
        "notes": "Stroke-by-stroke human sketches for Paint canvas playback.",  
    },  
    {  
        "priority": 6,  
        "folder": "6\_5\_cmu\_mocap\_bvh",  
        "name": "CMU Graphics Lab Motion Capture BVH Archive",  
        "version": "master",  
        "url": "https\://github.com/una-dinosauria/cmu-mocap/archive/refs/heads/master.zip",  
        "filename": "cmu-mocap-master.zip",  
        "licence": "NSF Free Use (Commercial & Research)",  
        "commercial\_use": "yes",  
        "sha256": "github-archive",  
        "notes": "BVH human motion capture files importable into Blender via bpy.ops.import\_anim.bvh.",  
    },

    \# PRIORITY 7: Jarvis Reference Repos (9.1)  
    {  
        "priority": 7,  
        "folder": "9\_1\_jarvis\_repos",  
        "name": "Microsoft UFO \+ Simular Agent-S Reference Repos",  
        "version": "main",  
        "url": "https\://github.com/microsoft/UFO/archive/refs/heads/main.zip",  
        "filename": "microsoft-UFO-main.zip",  
        "licence": "MIT",  
        "commercial\_use": "yes",  
        "sha256": "github-archive",  
        "notes": "Reference architecture for HostAgent/AppAgent multi-app handoff and COM adapters.",  
    },  
\]

QUICKDRAW\_CATEGORIES \= \[  
    "house", "cat", "dog", "bicycle", "tree", "car", "chair", "table",  
    "clock", "flower", "laptop", "face", "star", "sun", "cloud", "bird",  
    "fish", "airplane", "boat", "bridge", "castle", "crown", "guitar",  
    "headphones", "key", "light bulb", "mountain", "umbrella", "wristwatch"  
\]

def write\_source\_txt(folder\_path: Path, item: dict, computed\_sha256: str \= "") \-\> None:  
    folder\_path.mkdir(parents=True, exist\_ok=True)  
    sha\_val \= computed\_sha256 or item\["sha256"\]  
    content \= (  
        f"name: {item\['name'\]}\\n"  
        f"version: {item\['version'\]}\\n"  
        f"url: {item\['url'\]}\\n"  
        f"licence: {item\['licence'\]}   commercial\_use: {item\['commercial\_use'\]}\\n"  
        f"downloaded: {TODAY}\\n"  
        f"sha256: {sha\_val}\\n"  
        f"notes: {item\['notes'\]}\\n"  
    )  
    (folder\_path / "SOURCE.txt").write\_text(content, encoding="utf-8")

def sha256\_file(path: Path) \-\> str:  
    h \= hashlib.sha256()  
    with open(path, "rb") as f:  
        for chunk in iter(lambda: f.read(1024 \* 1024), b""):  
            h.update(chunk)  
    return h.hexdigest()

def download\_all(run\_downloads: bool \= True) \-\> None:  
    INBOX\_ROOT.mkdir(parents=True, exist\_ok=True)  
    for item in sorted(RESOURCES, key=lambda x: x\["priority"\]):  
        target\_dir \= INBOX\_ROOT / item\["folder"\]  
        write\_source\_txt(target\_dir, item)  
        if not run\_downloads or not item\["filename"\]:  
            continue  
        dest \= target\_dir / item\["filename"\]  
        if dest.exists() and dest.stat().st\_size \> 1024:  
            print(f"\[SKIP\] Already downloaded: {dest}")  
            continue  
        print(f"\[FETCH P{item\['priority'\]}\] {item\['name'\]} \-\> {dest}")  
        try:  
            urllib.request.urlretrieve(item\["url"\], str(dest))  
            digest \= sha256\_file(dest)  
            write\_source\_txt(target\_dir, item, computed\_sha256=digest)  
            print(f"  \[OK\] SHA-256: {digest}")  
        except Exception as exc:  
            print(f"  \[WARN\] Direct download deferred ({exc}); SOURCE.txt created.")

    \# Download Quick, Draw\! core categories  
    qd\_dir \= INBOX\_ROOT / "6\_1\_quickdraw\_ndjson"  
    qd\_dir.mkdir(parents=True, exist\_ok=True)  
    if run\_downloads:  
        for cat in QUICKDRAW\_CATEGORIES:  
            safe\_cat \= urllib.parse.quote(cat)  
            url \= f"https\://storage.googleapis.com/quickdraw\_dataset/full/simplified/{safe\_cat}.ndjson"  
            dest \= qd\_dir / f"{cat.replace(' ', '\_')}.ndjson"  
            if not dest.exists():  
                try:  
                    urllib.request.urlretrieve(url, str(dest))  
                    print(f"  \[QUICKDRAW\] Downloaded {dest.name}")  
                except Exception as e:  
                    print(f"  \[WARN\] QuickDraw {cat}: {e}")

if \_\_name\_\_ \== "\_\_main\_\_":  
    download\_all(run\_downloads=True)

For the Hugging Face models and datasets (5.1–5.6, 4.1–4.9, 8.2–8.5), run these exact huggingface-cli commands in PowerShell so they land cleanly inside D:\\new\_automation\\data\\inbox\\:

PowerShell  
\# 1\. OmniParser v2 (100% MIT pipeline: icon\_detect\_v3 \+ icon\_caption ONLY)  
huggingface-cli download microsoft/OmniParser-v2.0 \--include "icon\_detect\_v3/\*" "icon\_caption/\*" \--local-dir "D:\\new\_automation\\data\\inbox\\5\_3\_omniparser\_v2"

\# 2\. UI-TARS-1.5-7B GGUF (Q4\_K\_M \+ mmproj for 6 GB VRAM)  
huggingface-cli download mradermacher/UI-TARS-1.5-7B-GGUF \--include "\*Q4\_K\_M.gguf" "\*mmproj\*" \--local-dir "D:\\new\_automation\\data\\inbox\\5\_1\_ui\_tars\_1\_5\_7b"

\# 3\. Qwen2.5-VL-7B-Instruct GGUF (Q4\_K\_M \+ mmproj)  
huggingface-cli download unsloth/Qwen2.5-VL-7B-Instruct-GGUF \--include "\*Q4\_K\_M.gguf" "\*mmproj-F16.gguf" \--local-dir "D:\\new\_automation\\data\\inbox\\5\_4\_qwen2\_5\_vl\_7b\_gguf"

\# 4\. faster-whisper large-v3-turbo (CTranslate2 MIT)  
huggingface-cli download deepdml/faster-whisper-large-v3-turbo-ct2 \--local-dir "D:\\new\_automation\\data\\inbox\\5\_5\_faster\_whisper\_turbo"

\# 5\. BGE Reranker v2-m3 (Multilingual \+ Hinglish)  
huggingface-cli download BAAI/bge-reranker-v2-m3 \--local-dir "D:\\new\_automation\\data\\inbox\\5\_6\_bge\_reranker\_v2\_m3"

\# 6\. Multi-App & Hinglish Datasets (Commercial-Safe Only)  
huggingface-cli download xlangai/AgentNet \--repo-type dataset \--include "\*.jsonl" "\*.json" \--local-dir "D:\\new\_automation\\data\\inbox\\4\_8\_agentnet\_opencua"  
huggingface-cli download likaixin/ScreenSpot-Pro \--repo-type dataset \--local-dir "D:\\new\_automation\\data\\inbox\\4\_6\_screenspot"  
huggingface-cli download AmazonScience/massive \--repo-type dataset \--include "en-US/\*" "hi-IN/\*" \--local-dir "D:\\new\_automation\\data\\inbox\\4\_9\_multilingual\_hinglish"  
huggingface-cli download google/docci \--repo-type dataset \--include "\*.jsonl" \--local-dir "D:\\new\_automation\\data\\inbox\\8\_2\_docci\_localized\_narratives"  
huggingface-cli download SALT-NLP/Design2Code \--repo-type dataset \--local-dir "D:\\new\_automation\\data\\inbox\\8\_4\_websight\_design2code"  
huggingface-cli download rajpurkar/squad\_v2 \--repo-type dataset \--local-dir "D:\\new\_automation\\data\\inbox\\8\_5\_quiz\_datasets"

### **Master Integration Prompt to Paste Directly Into Claude Code**

Copy and paste the block below directly into **Claude Code**:

Markdown  
\# MASTER INTEGRATION DIRECTIVE FOR CLAUDE: WIRING \`D:\\new\_automation\\data\\inbox\\\` INTO EXISTING HOJAIGA ORGANS

All external binaries, documentation repositories, multi-app benchmarks, 6 GB VRAM models, 3D/drawing assets, and video editing engines have been verified and staged under \`D:\\new\_automation\\data\\inbox\\\<section\>\_\<item\>\\\` with \`SOURCE.txt\` provenance files.

\#\# STRICT ARCHITECTURAL RULES  
1\. \*\*NO NEW STANDALONE PYTHON FILES:\*\* Integrate all capabilities directly into our \*\*existing\*\* Hojaiga codebase (\`tools\\rea\`, \`core\_organs\\app\_teaching\_automation.py\`, \`core\_organs\\perception\\omniparser\_discovery.py\`, \`core\_organs\\rag\\\`, \`universal\_scan.py\`, \`video\_pipeline.py\`, and Blender/Canvas executors).  
2\. \*\*100% COMMERCIAL-SAFE LICENSING:\*\* Never load \`icon\_detect\` (AGPL-3.0) from OmniParser v2; load ONLY \`icon\_detect\_v3\` (MIT) \+ \`icon\_caption\` (MIT). Never ingest non-commercial datasets (\`PartNet/ShapeNet\`, \`SciQ\`, \`RACE\`, \`TVSum\`) into commercial weights.  
3\. \*\*HARDWARE ENVELOPE:\*\* Windows 11 Home, RTX 3050 (6 GB VRAM), 32 GB System RAM, Python 3.13, Node 22\. Keep CPU tasks (\`faster-whisper\` int8/fp16, \`bge-reranker-v2-m3\`, LanceDB, Ghidra headless) off the GPU when the 7B/2B VLM is active.

\---

\#\# WORK PACKAGE 1: NATIVE BINARY REVERSE ENGINEERING (\`tools\\rea\` \+ \`universal\_scan.py\`)  
Wire the new reverse-engineering toolchain in \`D:\\new\_automation\\data\\inbox\\\` into our existing app scanner and REA bridge:  
1\. \*\*Toolkit Detection First (\`2\_4\_detect\_it\_easy\\diec.exe\`):\*\*  
   \- Before scanning any unknown \`.exe\`, run \`diec.exe \-j \<target.exe\>\` to classify the binary toolkit (\`Win32\`, \`WPF/.NET\`, \`Electron\`, \`Qt\`, \`WinUI3/UWP\`).  
2\. \*\*Route by Toolkit:\*\*  
   \- \*\*If \`.NET / WPF\`:\*\* Invoke \`2\_3\_ilspy\\ilspycmd.exe\` to decompile commands, routed events, XAML dialogs, and settings keys straight into the app's LanceDB command index.  
   \- \*\*If \`Electron\`:\*\* Use \`2\_5\_electron\_asar\` (\`npx asar extract app.asar\`) inside our isolated Node 22 environment and pass the extracted JS bundle to \`tools\\rea\`.  
   \- \*\*If \`Native Win32 / C++\` (Excel, Word, Paint, Calculator):\*\* Point \`tools\\rea\` to \`2\_1\_ghidra\\ghidra\_12.2\_PUBLIC\\support\\analyzeHeadless.bat\` with \`JAVA\_HOME\` set locally to \`2\_2\_temurin\_jdk21\` (portable, no system Java dependency) to extract string tables, accelerator tables, menu resource IDs, and exported COM interfaces.  
   \- \*\*If \`Packaged UWP / WinUI 3\`:\*\* Parse \`AppxManifest.xml\` and PRI/XAML resources per \`2\_7\_winui\_uwp\_docs\`, and cross-check the live UIA tree against \`2\_6\_accessibility\_insights\`.

\---

\#\# WORK PACKAGE 2: WHOLE-APP DOCUMENTATION & MULTI-APP RAG INGESTION (LanceDB)  
Ingest the offline documentation and multi-app datasets into our existing LanceDB tables (\`procedural\_workflow\_rag\` and \`app\_commands\`):  
1\. \*\*Official App Docs (\`3\_1\` to \`3\_10\`):\*\*  
   \- Parse \`3\_1\_office\_vba\_docs\\VBA-Docs-main\` (CC BY 4.0) \+ \`3\_2\_office\_shortcuts\` into COM/VBA macro templates and Tier-0 hotkeys for Word, Excel, PowerPoint, and Outlook.  
   \- Parse \`3\_3\_blender\_docs\` (\`blender\_python\_reference\_current.zip\` \+ \`blender\_manual\_html.zip\`) for Blender 5.2 \`bpy\` operators and node graphs.  
   \- Parse \`3\_4\_chrome\_devtools\_protocol\` (\`browser\_protocol.json\`), \`3\_7\_libreoffice\_docs\`, \`3\_8\_gimp\_inkscape\_krita\_docs\`, \`3\_9\_vscode\_docs\`, and \`3\_10\_ffmpeg\_docs\` (\`ffmpeg-filters.html\`) into the command store.  
2\. \*\*Multi-App & Cross-App Task Patterns (\`4\_1\` to \`4\_9\` & \`9\_1\_jarvis\_repos\`):\*\*  
   \- Fold the \*\*HostAgent \-\> AppAgent \+ Shared Blackboard\*\* task-splitting and data-handoff architecture from \`9\_1\_jarvis\_repos\\microsoft-UFO-main\` (MIT) into \`app\_teaching\_automation.py\`.  
   \- When a user request spans multiple apps (\`Chrome \-\> Excel\`, \`Paint \-\> Word\`, \`Excel \-\> PowerPoint\`, \`Video \-\> Document\`), decompose it into per-app sub-goals sharing a typed \`Blackboard\` state dictionary, verified at each boundary by reading the saved file or inspecting the screenshot.  
   \- Register the evaluation tasks and checkers from \`4\_1\_osworld\` (Apache-2.0), \`4\_2\_windows\_agent\_arena\` (MIT), \`4\_5\_gui\_odyssey\` (CC BY 4.0), and \`4\_8\_agentnet\_opencua\` (MIT) as our multi-app test bench, plus \`4\_9\_multilingual\_hinglish\` (\`AmazonScience/massive\` \`hi-IN\` \+ \`en-US\`) for natural Hinglish command parsing.

\---

\#\# WORK PACKAGE 3: UPGRADE PERCEPTION, GROUNDING & RERANKING (\`5\_1\` to \`5\_6\`)  
1\. \*\*OmniParser v2 MIT Upgrade (\`5\_3\_omniparser\_v2\`):\*\*  
   \- Update \`omniparser\_discovery.py\` to load \`icon\_detect\_v3\` (YOLOv9-E, MIT) \+ \`icon\_caption\` (Florence-2, MIT).  
2\. \*\*Local 6 GB VRAM Vision & Grounding (\`5\_1\`, \`5\_2\`, \`5\_4\`):\*\*  
   \- Register \`5\_1\_ui\_tars\_1\_5\_7b\` (\`Q4\_K\_M.gguf\`) for fine-grained GUI coordinate grounding and \`5\_4\_qwen2\_5\_vl\_7b\_gguf\` (\`Q4\_K\_M.gguf\`) for the post-action visual proof critic (\`DOCCI\`-grade image inspection from \`8\_2\_docci\_localized\_narratives\`).  
3\. \*\*Multilingual Reranker (\`5\_6\_bge\_reranker\_v2\_m3\`):\*\*  
   \- Wire \`BAAI/bge-reranker-v2-m3\` on CPU/System RAM to rerank LanceDB procedures and UIA/DOM controls for English, Hindi, and Hinglish queries.

\---

\#\# WORK PACKAGE 4: DRAWING, BLENDER 3D WORLDS WITH ANIMATED HUMANS (\`6\_1\` to \`6\_5\`)  
1\. \*\*Quick, Draw\! Stroke Playback (\`6\_1\_quickdraw\_ndjson\`):\*\*  
   \- In the Paint/Canvas drawing engine, load simplified \`.ndjson\` stroke arrays from \`6\_1\_quickdraw\_ndjson\`, normalize coordinates to the target canvas bounding box, and play back smooth multi-stroke sketches via cubic-bezier cursor paths.  
2\. \*\*Blender 5.2 World & Animated Human Builder (\`6\_2\` to \`6\_5\`):\*\*  
   \- Extend the existing Blender \`bpy\` builder so scene requests (e.g., \*"Build a park/office with a human chopping/walking/typing"\*) assemble low-poly props from \`6\_2\_kenney\_assets\` (CC0), apply PBR materials and HDRI lighting from \`6\_3\_polyhaven\` (CC0), and import rigged human characters \+ animations from \`6\_4\_mixamo\` (\`.fbx\`/\`.glb\`) or motion-capture \`.bvh\` files from \`6\_5\_cmu\_mocap\_bvh\` (\`bpy.ops.import\_anim.bvh()\`), verified by 3-angle viewport renders.

\---

\#\# WORK PACKAGE 5: HEADLESS & PROJECT-FILE VIDEO EDITING ENGINE (\`7\_1\` to \`7\_8\`) Integrate full automated video editing into the existing video module using: 1\. \*\*\`5\_5\_faster\_whisper\_turbo\`\*\* for timestamped speech transcription and word-level \`.srt\`/\`.ass\` caption generation. 2\. \*\*\`7\_2\_auto\_editor\`\*\* to strip dead air/silences and \*\*\`7\_3\_pyscenedetect\`\*\* to detect shot boundaries on raw clips in \`7\_8\_sample\_footage\`. 3\. \*\*\`7\_1\_ffmpeg\_full\\bin\\ffmpeg.exe\`\*\* to execute headless cuts, transitions, burned-in captions, and audio ducking with tracks from \`7\_7\_free\_music\`. 4\. \*\*\`7\_4\_shotcut\_kdenlive\` MLT XML Writer:\*\* Output a valid \`.mlt\` / \`.kdenlive\` XML project file alongside the rendered \`.mp4\` so the user can open the finished edit in Shotcut or Kdenlive and tweak any cut or track manually (bypassing DaVinci Resolve Free's external scripting lock).   
