LeanProductivity MarkItDown Batch Converter (with GUI)
=======================================================

Version: 0.10 (2025-06-20)
Author : Sascha D. Kasper – LeanProductivity
Website: https://sascha-kasper.com
Help   : https://github.com/microsoft/markitdown


Overview
--------
This is the GUI version of the LeanProductivity MarkItDown Batch Converter.

It allows you to convert multiple files and folders to clean Markdown using a 
simple graphical interface — powered by the MarkItDown engine from Microsoft.

All conversions run 100% locally on your machine. No data is uploaded or sent online.

Supported Formats
-----------------
- Documents: DOCX, PDF, HTML, EPUB, PPTX, TXT, CSV, JSON, XML
- Images: JPG, PNG
- Audio: MP3, WAV, M4A (requires ffmpeg.exe)
- Archives: ZIP
- More formats supported by MarkItDown core

Key Features
------------
- ✅ Select input/output folders via GUI
- ✅ Drag & drop file support
- ✅ Convert entire folders recursively
- ✅ Choose which file extensions to include
- ✅ Automatic skip for already converted files
- ✅ Dry-run mode (preview what will be converted)
- ✅ Force convert (override last modified checks)
- ✅ Real-time log output during conversion
- ✅ Offline audio transcription via ffmpeg and speech recognition

Installation
------------
Run the setup and follow the instructions. Then launch the application.

Make sure the following files/folders are present in the same directory:
- MarkItDownBatchConverter.exe        ← the main app
- ffmpeg.exe                          ← required for audio
- /resources/bin/ffmpeg.exe           ← also used internally
- conversion_config.json              ← optional config overrides
- logo.png                            ← app icon or UI resource
- /logs/                              ← logs from previous runs

Troubleshooting
---------------
❌ Audio files fail to convert?
→ Ensure `ffmpeg.exe` is present in the same folder as the .exe  
→ Check your internet connection (used for speech recognition)  
→ Make sure the audio file has clear speech

❌ The app doesn't launch?
→ Check your antivirus/smartscreen settings  
→ Try running as administrator  

❌ Files are skipped?
→ They may already be up to date. Use "Force Convert" if needed.

License
-------
MIT License.  
See LICENSE.txt for details.

This app includes open-source components from:
- Microsoft (MarkItDown)
- Python ecosystem (pydub, speech_recognition)
- ffmpeg (LGPL)

For questions or support, visit:
https://sascha-kasper.com
