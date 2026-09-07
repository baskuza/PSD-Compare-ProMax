# PSD Compare Pro Max 🎨

An offline, open-source GUI tool for deeply analyzing, comparing, and visualizing differences between two Photoshop (`.psd`) files. Built specifically for complex layer structures like Live2D rigging or heavy graphic design projects.

## ✨ Features

- **100% Offline & Secure:** No API keys, no internet connection required, zero data leaks.
- **Deep Metadata Analysis:** Tracks layer IDs, visibility, opacity, blend modes, offsets, and text content.
- **Structural Tree Diff:** Reconstructs the exact Photoshop Group/Folder hierarchy so you can see *where* the changes happened, not just *what* changed.
- **Visual Web Slider:** Generates an interactive Before/After image slider in your browser.
- **Save Diff PSD:** Automatically extracts and saves a new `.psd` containing *only* the added or modified layers while keeping the folder structure perfectly intact.
- **Native PDF Export:** Generates clean, printer-friendly reports with visual thumbnails of the changed layers.
- **Drag & Drop:** Just drag your old and new PSD files into the sleek UI to begin.

## 🛠️ Requirements

- Python 3.10+
- `customtkinter` (UI)
- `psd-tools` (PSD Parser)
- `fpdf2` (PDF Generator)
- `windnd` (Windows Drag & Drop)
- `Pillow` (Image Processing)

## 🚀 How to Run

1. Clone this repository.
2. Install the required libraries:
   ```bash
   pip install customtkinter psd-tools fpdf2 windnd Pillow
   ```
3. Run the GUI:
   ```bash
   python psd_compare_gui.py
   ```

## 🖥️ Headless CLI Mode (Automation)

You can also run the tool via terminal to generate a JSON report:
```bash
python psd_compare_gui.py --file1 old.psd --file2 new.psd --json report.json
```

## 🔒 Security
This script operates completely locally on your machine. It does not phone home, does not upload files, and requires no API tokens.
