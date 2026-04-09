#!/usr/bin/env python3


from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


DEFAULT_URL = "https://psg.1token.tech/v3/home?tab=dm3oj8"
WORKDIR = Path(__file__).resolve().parent
PROFILE_DIR = WORKDIR / ".playwright-profile"
SCREENSHOT_DIR = WORKDIR / "screenshots"


@dataclass(frozen=True)
class SelectorAttempt:
    description: str
    factory: Callable[[Page], Locator]


class AutomationError(RuntimeError):
    """Raised when the page does not expose an expected control."""


def log(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "step"


def screenshot_path(prefix: str) -> Path:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    return SCREENSHOT_DIR / f"{slugify(prefix)}_{suffix}.png"


def click_locator(page: Page, attempt: SelectorAttempt, timeout_ms: int = 500) -> bool:
    try:
        locator = attempt.factory(page).first
        if locator.count() == 0:
            return False
        if not locator.is_visible():
            return False
        locator.click(timeout=timeout_ms)
        return True
    except Exception:
        return False


def click_first_match(
    page: Page,
    step_name: str,
    attempts: Iterable[SelectorAttempt],
    timeout_ms: int = 5000,
    settle_ms: int = 180,
) -> None:
    deadline = time.monotonic() + (timeout_ms / 1000)
    attempt_list = list(attempts)
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        for attempt in attempt_list:
            try:
                if click_locator(page, attempt):
                    log(f"Completed: {step_name} via {attempt.description}")
                    page.wait_for_timeout(settle_ms)
                    return
            except Exception as exc:  # pragma: no cover
                last_error = exc
        page.wait_for_timeout(60)

    labels = ", ".join(item.description for item in attempt_list)
    raise AutomationError(
        f"Could not complete step '{step_name}'. Tried: {labels}"
    ) from last_error


def labeled_attempts(
    labels: Iterable[str],
    *,
    roles: Iterable[str] = ("tab", "link", "button", "menuitem", "option", "treeitem"),
    exact_text: bool = False,
) -> list[SelectorAttempt]:
    attempts: list[SelectorAttempt] = []
    for label in labels:
        name_pattern = re.compile(rf"^{re.escape(label)}$", re.I) if exact_text else re.compile(label, re.I)
        for role in roles:
            attempts.append(
                SelectorAttempt(
                    description=f"{role}({label})",
                    factory=lambda page, role=role, pattern=name_pattern: page.get_by_role(role, name=pattern),
                )
            )
        attempts.append(
            SelectorAttempt(
                description=f"text({label})",
                factory=lambda page, pattern=name_pattern: page.get_by_text(pattern),
            )
        )
    return attempts


def analysis_report_attempts() -> list[SelectorAttempt]:
    return labeled_attempts(
        [r"analysis report"],
        roles=("link", "button", "treeitem", "tab"),
    )


def reporting_attempts() -> list[SelectorAttempt]:
    return labeled_attempts(
        [r"reporting"],
        roles=("link", "button", "treeitem", "menuitem"),
    )


def multi_portfolio_attempts() -> list[SelectorAttempt]:
    return labeled_attempts(
        [r"multi(?:ple)?\s+portfolio\s+report"],
        roles=("tab", "link", "button"),
    )


def portfolio_filter_attempts() -> list[SelectorAttempt]:
    attempts = labeled_attempts(
        [r"portfolio"],
        roles=("button", "combobox", "textbox", "tab", "link"),
    )
    attempts.extend(
        [
            SelectorAttempt(
                description="textbox[placeholder*=portfolio]",
                factory=lambda page: page.locator(
                    "input[placeholder*='portfolio' i], textarea[placeholder*='portfolio' i]"
                ),
            ),
            SelectorAttempt(
                description="element[title*=portfolio]",
                factory=lambda page: page.locator(
                    "[title*='portfolio' i], [aria-label*='portfolio' i]"
                ),
            ),
        ]
    )
    return attempts


def sp_core_attempts() -> list[SelectorAttempt]:
    return labeled_attempts(
        [r"sp core"],
        roles=("tab", "option", "treeitem", "button", "menuitem", "link"),
        exact_text=False,
    )


def edit_filter_icon_attempts() -> list[SelectorAttempt]:
    attempts = labeled_attempts(
        [r"edit filter", r"filter", r"settings"],
        roles=("button", "tab", "link"),
    )
    attempts.extend(
        [
            SelectorAttempt(
                description="button[aria-label*=filter]",
                factory=lambda page: page.locator(
                    "button[aria-label*='filter' i], [role='button'][aria-label*='filter' i]"
                ),
            ),
            SelectorAttempt(
                description="button[title*=filter]",
                factory=lambda page: page.locator(
                    "button[title*='filter' i], [role='button'][title*='filter' i]"
                ),
            ),
            SelectorAttempt(
                description="button[aria-label*=edit]",
                factory=lambda page: page.locator(
                    "button[aria-label*='edit' i], [role='button'][aria-label*='edit' i]"
                ),
            ),
            SelectorAttempt(
                description="button[title*=edit]",
                factory=lambda page: page.locator(
                    "button[title*='edit' i], [role='button'][title*='edit' i]"
                ),
            ),
        ]
    )
    return attempts


def click_edit_filter_icon(
    page: Page,
    *,
    timeout_ms: int = 4000,
    settle_ms: int = 150,
) -> None:
    deadline = time.monotonic() + (timeout_ms / 1000)

    while time.monotonic() < deadline:
        try:
            target = page.evaluate(
                """
                () => {
                  const normalize = (value) => (value || "").replace(/\\s+/g, " ").trim().toLowerCase();
                  const isVisible = (el) => {
                    if (!(el instanceof HTMLElement)) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
                  };
                  const allElements = Array.from(document.querySelectorAll("*"));
                  const portfolioLabel = allElements.find((el) => {
                    if (!isVisible(el)) return false;
                    const rect = el.getBoundingClientRect();
                    return rect.top < 140 && normalize(el.innerText || el.textContent) === "portfolio";
                  });
                  if (!portfolioLabel) return null;

                  const labelRect = portfolioLabel.getBoundingClientRect();
                  const candidates = allElements.filter((el) => {
                    if (!isVisible(el)) return false;
                    const isButtonLike = el.tagName === "BUTTON" || el.getAttribute("role") === "button";
                    if (!isButtonLike) return false;
                    const rect = el.getBoundingClientRect();
                    if (rect.top > labelRect.bottom + 30 || rect.bottom < labelRect.top - 30) return false;
                    if (rect.right > labelRect.left + 10) return false;
                    if (rect.width < 20 || rect.width > 80 || rect.height < 20 || rect.height > 80) return false;
                    return true;
                  });

                  if (candidates.length === 0) return null;

                  candidates.sort((a, b) => {
                    const rectA = a.getBoundingClientRect();
                    const rectB = b.getBoundingClientRect();
                    const scoreA = Math.abs(labelRect.left - rectA.right) + Math.abs(labelRect.top - rectA.top);
                    const scoreB = Math.abs(labelRect.left - rectB.right) + Math.abs(labelRect.top - rectB.top);
                    return scoreA - scoreB;
                  });

                  const rect = candidates[0].getBoundingClientRect();
                  return {
                    x: rect.left + rect.width / 2,
                    y: rect.top + rect.height / 2,
                    strategy: "geometry(left of Portfolio)",
                  };
                }
                """
            )
            if target:
                page.mouse.click(target["x"], target["y"])
                log(f"Completed: Open edit filter icon via {target['strategy']}")
                page.wait_for_timeout(settle_ms)
                return
        except Exception:
            pass

        for attempt in edit_filter_icon_attempts():
            if click_locator(page, attempt):
                log(f"Completed: Open edit filter icon via {attempt.description}")
                page.wait_for_timeout(settle_ms)
                return

        page.wait_for_timeout(60)

    raise AutomationError("Could not complete step 'Open edit filter icon'.")


def visible_text_boxes(page: Page, pattern: re.Pattern[str]) -> list[dict[str, float]]:
    boxes: list[dict[str, float]] = []
    locator = page.get_by_text(pattern)

    try:
        count = locator.count()
    except Exception:
        return boxes

    for index in range(count):
        item = locator.nth(index)
        try:
            if not item.is_visible(timeout=250):
                continue
            box = item.bounding_box()
            if box:
                boxes.append(box)
        except Exception:
            continue

    return boxes


def topmost_visible_box(page: Page, pattern: re.Pattern[str]) -> dict[str, float] | None:
    boxes = visible_text_boxes(page, pattern)
    if not boxes:
        return None
    return min(boxes, key=lambda item: (item["y"], item["x"]))


def ensure_dropdown_option_selected(
    page: Page,
    option_name: str,
    *,
    timeout_ms: int = 5000,
    settle_ms: int = 150,
) -> None:
    deadline = time.monotonic() + (timeout_ms / 1000)
    label_pattern = re.compile(rf"^\s*{re.escape(option_name)}\s*$", re.I)
    search_input = page.locator(
        "input[placeholder*='select or search a portfolio' i], "
        "textarea[placeholder*='select or search a portfolio' i]"
    ).first

    while time.monotonic() < deadline:
        try:
            search_input.wait_for(state="visible", timeout=1000)
            search_box = search_input.bounding_box()
            if search_box:
                all_boxes = visible_text_boxes(page, label_pattern)
                selected_chip = None
                dropdown_label = None

                for box in all_boxes:
                    if box["y"] + box["height"] <= search_box["y"] + 6:
                        selected_chip = box
                    elif box["y"] >= search_box["y"] + search_box["height"] - 2:
                        if dropdown_label is None or box["y"] < dropdown_label["y"]:
                            dropdown_label = box

                if selected_chip is not None:
                    log(f"Completed: Select {option_name} via selected portfolio chip (already selected)")
                    page.wait_for_timeout(settle_ms)
                    return

                if dropdown_label is not None:
                    click_x = max(search_box["x"] + 14, dropdown_label["x"] - 18)
                    click_y = dropdown_label["y"] + (dropdown_label["height"] / 2)
                    page.mouse.click(click_x, click_y)
                    page.wait_for_timeout(120)
                    continue

                visible_checkboxes = page.locator("input[type='checkbox'], [role='checkbox']")
                checkbox_count = visible_checkboxes.count()
                closest_box = None

                for index in range(checkbox_count):
                    checkbox = visible_checkboxes.nth(index)
                    try:
                        if not checkbox.is_visible(timeout=200):
                            continue
                        box = checkbox.bounding_box()
                        if not box:
                            continue
                        if box["y"] < search_box["y"] + search_box["height"] - 2:
                            continue
                        if box["x"] > search_box["x"] + 60:
                            continue
                        if closest_box is None or box["y"] < closest_box["y"]:
                            closest_box = box
                    except Exception:
                        continue

                if closest_box is not None:
                    page.mouse.click(
                        closest_box["x"] + (closest_box["width"] / 2),
                        closest_box["y"] + (closest_box["height"] / 2),
                    )
                    page.wait_for_timeout(120)
                    continue
        except Exception:
            pass

        page.wait_for_timeout(60)

    raise AutomationError(f"Could not complete step 'Select {option_name}'.")


def close_dropdown(page: Page, *, settle_ms: int = 150) -> None:
    page.keyboard.press("Escape")
    page.wait_for_timeout(settle_ms)


def close_filter_panel(page: Page, *, settle_ms: int = 200) -> None:
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(120)
    except Exception:
        pass

    try:
        viewport = page.viewport_size or {"width": 1440, "height": 960}
        page.mouse.click(int(viewport["width"] * 0.72), 120)
        page.wait_for_timeout(settle_ms)
    except Exception:
        page.wait_for_timeout(settle_ms)


def calendar_attempts() -> list[SelectorAttempt]:
    attempts = labeled_attempts(
        [r"calendar", r"start date", r"end date", r"\d{4}-\d{2}-\d{2}\s*~\s*\d{4}-\d{2}-\d{2}"],
        roles=("button", "textbox", "combobox", "link"),
    )
    attempts.extend(
        [
            SelectorAttempt(
                description="date range input",
                factory=lambda page: page.locator(
                    "input[value*='-' i][value*='~' i], input[placeholder*='date' i]"
                ),
            ),
            SelectorAttempt(
                description="date range text",
                factory=lambda page: page.get_by_text(
                    re.compile(r"\d{4}-\d{2}-\d{2}\s*~\s*\d{4}-\d{2}-\d{2}")
                ),
            ),
            SelectorAttempt(
                description="calendar button aria-label",
                factory=lambda page: page.locator(
                    "button[aria-label*='calendar' i], [role='button'][aria-label*='calendar' i]"
                ),
            ),
            SelectorAttempt(
                description="calendar button title",
                factory=lambda page: page.locator(
                    "button[title*='calendar' i], [role='button'][title*='calendar' i]"
                ),
            ),
            SelectorAttempt(
                description="calendar icon svg parent",
                factory=lambda page: page.locator(
                    "svg[data-icon*='calendar' i], svg[aria-label*='calendar' i]"
                ).locator("xpath=ancestor::*[@role='button' or self::button][1]"),
            ),
        ]
    )
    return attempts


def click_calendar_control(
    page: Page,
    *,
    timeout_ms: int = 5000,
    settle_ms: int = 150,
) -> None:
    deadline = time.monotonic() + (timeout_ms / 1000)
    date_pattern = re.compile(r"\d{4}-\d{2}-\d{2}\s*~\s*\d{4}-\d{2}-\d{2}")

    while time.monotonic() < deadline:
        for attempt in calendar_attempts():
            if click_locator(page, attempt):
                log(f"Completed: Open calendar via {attempt.description}")
                page.wait_for_timeout(settle_ms)
                return

        try:
            boxes = visible_text_boxes(page, date_pattern)
            if boxes:
                box = min(boxes, key=lambda item: item["y"])
                click_x = box["x"] + box["width"] + 18
                click_y = box["y"] + (box["height"] / 2)
                page.mouse.click(click_x, click_y)
                log("Completed: Open calendar via date-range right edge")
                page.wait_for_timeout(settle_ms)
                return
        except Exception:
            pass

        page.wait_for_timeout(60)

    labels = ", ".join(item.description for item in calendar_attempts())
    raise AutomationError(f"Could not complete step 'Open calendar'. Tried: {labels}")


def month_to_today_attempts() -> list[SelectorAttempt]:
    attempts = labeled_attempts(
        ["MTD"],
        roles=("button", "menuitem", "option", "link", "tab"),
        exact_text=True,
    )
    attempts.extend(
        labeled_attempts(
            [r"month to today"],
            roles=("button", "menuitem", "option", "link", "tab"),
            exact_text=False,
        )
    )
    return attempts


def confirm_attempts() -> list[SelectorAttempt]:
    return labeled_attempts(
        [r"confirm"],
        roles=("button", "menuitem", "link"),
        exact_text=False,
    )


def capture_report_section(page: Page, destination: Path) -> None:
    page.set_viewport_size({"width": 1440, "height": 1800})
    page.wait_for_timeout(150)
    general_info_locator = page.get_by_text(re.compile(r"general info", re.I)).first
    third_return_row_pattern = re.compile(r"^\s*7-day pnl%\s*\(annualized\)\s*$", re.I)
    deadline = time.monotonic() + 8
    general_box = None
    return_box = None
    first_return_row_box = None
    second_return_row_box = None
    third_return_row_box = None

    while time.monotonic() < deadline:
        general_info_locator.scroll_into_view_if_needed(timeout=5000)
        page.wait_for_timeout(100)

        general_box = topmost_visible_box(page, re.compile(r"general info", re.I))
        return_box = topmost_visible_box(page, re.compile(r"return", re.I))
        first_return_row_box = topmost_visible_box(page, re.compile(r"^\s*period pnl%\s*$", re.I))
        second_return_row_box = topmost_visible_box(
            page,
            re.compile(r"^\s*period pnl%\s*\(annualized\)\s*$", re.I),
        )
        third_return_row_box = topmost_visible_box(page, third_return_row_pattern)

        if general_box and return_box and first_return_row_box and second_return_row_box:
            break

        page.wait_for_timeout(120)

    if not general_box or not return_box or not first_return_row_box or not second_return_row_box:
        raise AutomationError("Could not locate the General Info / Return section for the clipped screenshot.")

    viewport = page.viewport_size or {"width": 1440, "height": 1400}
    row_gap = max(
        second_return_row_box["y"] - first_return_row_box["y"],
        first_return_row_box["height"],
        second_return_row_box["height"],
        44,
    )

    clip_x = max(general_box["x"] - 30, 0)
    clip_y = max(general_box["y"] - 18, 0)
    clip_width = max(viewport["width"] - clip_x - 10, 200)
    if third_return_row_box:
        clip_bottom = max(second_return_row_box["y"] + second_return_row_box["height"] + 24, third_return_row_box["y"] - 8)
    else:
        clip_bottom = second_return_row_box["y"] + row_gap - 6
    clip_height = max(clip_bottom - clip_y, 300)

    page.screenshot(
        path=str(destination),
        clip={
            "x": clip_x,
            "y": clip_y,
            "width": clip_width,
            "height": clip_height,
        },
    )
    log(f"Saved screenshot to: {destination}")


def wait_for_post_login_ready(page: Page) -> None:
    page.wait_for_load_state("domcontentloaded")
    deadline = time.monotonic() + 300

    while time.monotonic() < deadline:
        if "login" not in page.url.lower():
            for attempt in (
                multi_portfolio_attempts()
                + analysis_report_attempts()
                + reporting_attempts()
            ):
                try:
                    attempt.factory(page).first.wait_for(state="visible", timeout=600)
                    log("Authenticated page detected.")
                    page.wait_for_timeout(200)
                    return
                except Exception:
                    continue
        page.wait_for_timeout(200)

    raise AutomationError("Timed out waiting for the authenticated reporting page.")


def run_flow(page: Page, destination: Path) -> None:
    click_first_match(page, "Analysis Report", analysis_report_attempts())
    click_first_match(page, "Reporting", reporting_attempts())
    click_first_match(page, "Multiple Portfolio Report", multi_portfolio_attempts())
    click_edit_filter_icon(page)
    click_first_match(page, "Select SP Core", sp_core_attempts())
    close_filter_panel(page)
    click_first_match(page, "Open portfolio filter", portfolio_filter_attempts())
    ensure_dropdown_option_selected(page, "All")
    close_dropdown(page)
    click_calendar_control(page)
    click_first_match(page, "Select Month to today", month_to_today_attempts())
    click_first_match(page, "Confirm", confirm_attempts(), timeout_ms=7000, settle_ms=350)

    # Let the report repaint before capturing the final image.
    page.wait_for_timeout(1000)
    capture_report_section(page, destination)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture PSG multiple portfolio report screenshot.")
    parser.add_argument("--url", default=DEFAULT_URL, help="Authenticated PSG page URL.")
    parser.add_argument(
        "--profile-dir",
        default=str(PROFILE_DIR),
        help="Chromium user data directory used by Playwright.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output screenshot path. Defaults to ./screenshots/report_<timestamp>.png",
    )
    parser.add_argument(
        "--pause-on-finish",
        action="store_true",
        help="Keep the browser open after the screenshot is saved.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output).expanduser().resolve() if args.output else screenshot_path("report")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    profile_dir = Path(args.profile_dir).expanduser().resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            viewport={"width": 1440, "height": 960},
        )

        page = context.pages[0] if context.pages else context.new_page()
        page.goto(args.url, wait_until="domcontentloaded")
        log(f"Opened {args.url}")

        try:
            wait_for_post_login_ready(page)
            run_flow(page, output_path)
        except (AutomationError, PlaywrightTimeoutError) as exc:
            failure_path = screenshot_path("failure")
            page.screenshot(path=str(failure_path), full_page=True)
            log(f"Failure screenshot saved to: {failure_path}")
            print(f"\nAutomation failed: {exc}", file=sys.stderr)
            return 1
        finally:
            if args.pause_on_finish:
                print("\nBrowser left open. Press Enter to close it...", flush=True)
                input()
            context.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
