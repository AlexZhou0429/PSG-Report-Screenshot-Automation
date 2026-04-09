# PSG Report Screenshot Automation

Small Playwright + Python tool for capturing a PSG multi-portfolio report screenshot after login.

## What It Does

The script:

1. Opens `Analysis Report`
2. Opens `Reporting`
3. Opens `Multiple Portfolio Report`
4. Selects `SP Core`
5. Ensures `Portfolio = All`
6. Selects `MTD`
7. Clicks `Confirm`
8. Saves a cropped screenshot

## Requirements

- Python 3.10+
- Access to the PSG system

## Install

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## Run

```bash
python3 psg_report_screenshot.py
```

Custom output path:

```bash
python3 psg_report_screenshot.py --output screenshots/my_report.png
```

Keep browser open after the run:

```bash
python3 psg_report_screenshot.py --pause-on-finish
```

## Notes

- Login is manual.
- The script depends on the current PSG UI and may need selector updates if the page changes.
- Screenshots are saved to `screenshots/` by default.
- Do not commit `.playwright-profile/` or sensitive screenshots.
