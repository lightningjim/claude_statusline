---
slug: moon-shown-before-sunset
status: resolved
trigger: "Is this supposed to show the moon before sunset? [WxDesktopPy] [main ] [4 (51/47) ] [Opus 4.8 (1M context) ] [ 86°F |  8:38pm]"
created: 2026-05-29
updated: 2026-05-29
---

# Debug: moon-shown-before-sunset

## Symptoms

- **Expected behavior:** Before local sunset, the weather/time segment should show a daytime (sun) condition icon, not a moon. A moon icon should only appear after sunset.
- **Actual behavior:** The weather condition icon (leading glyph in the `[ 86°F |  8:38pm]` segment) renders as a moon while the sun segment shows the upcoming sunset at 8:38pm — i.e. it is still daytime, yet the moon is displayed.
- **Error messages:** None — silent rendering issue.
- **Timeline:** Observed 2026-05-29 evening (statusline shown ~before 8:38pm sunset).
- **Reproduction:** Render the statusline in the evening, after NWS's forecast period flips to "night" but before the locally-computed astral sunset time.

## Current Focus

- hypothesis: CONFIRMED — The weather condition icon's day/night selection used the NWS icon URL (`is_night = "/night/" in icon_path`) rather than the locally-computed astral sun times. NWS labels its forecast period "night" earlier than the true local sunset, so the moon glyph appeared before sunset. The sun segment independently uses astral, which is why `8:38pm` (sunset not yet past) was shown alongside the moon — an internal inconsistency.
- next_action: DONE — fix applied and tested.
- test: tests/test_nerd_icons.py::TestIsNightOverride (5 new tests)
- expecting: day glyph when is_night_override=False on /night/ URL

## Evidence

- `_icon_to_glyph` (claude-statusline.py:628) derived `is_night` purely from `/night/` in the NWS icon URL path.
- `_condition_category` (claude-statusline.py:698) had the same URL-only derivation.
- `_sun_segment` (claude-statusline.py:2170) uses `astral` to compute real local sunset — completely independent.
- `_weather_segment` called `_icon_to_glyph` and `_condition_category` with no day/night correction from astral.
- NWS API commonly flips its period URL to `/night/` before the true local sunset (typically 30–90 min early), causing the inconsistency near sunset.

## Eliminated

- NWS API data quality — NWS sends correct temperature; only the icon URL path is affected.
- astral library correctness — astral sun times are correct and used by the sun segment; they just weren't consulted by the condition icon path.

## Resolution

- root_cause: `_icon_to_glyph` and `_condition_category` derived `is_night` solely from the NWS icon URL (`/night/` substring), which NWS sets before the true local sunset. The `_sun_segment` used astral independently, so the two day/night sources could disagree near sunset.
- fix: Added `is_night_override: bool | None = None` parameter to both `_icon_to_glyph` and `_condition_category`. In `_weather_segment`, compute local astral `is_night` using the same `LocationInfo`/`sun()` pattern as `_sun_segment`, and pass it as `is_night_override` to both functions. Falls back to URL-derived flag when `_ASTRAL_OK` is False or location is unconfigured.
- verification: 443 tests pass (5 new regression tests in TestIsNightOverride). Visual verification pending — Kyle should confirm the condition icon now shows a sun/day glyph when rendered before sunset.
- files_changed:
  - claude-statusline.py (lines 628–656, 705–721, 2315–2365)
  - tests/test_nerd_icons.py (new TestIsNightOverride class)
