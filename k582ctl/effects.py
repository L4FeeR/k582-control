"""Built-in hardware effects of the EVision firmware (values from OpenRGB's driver)."""
from dataclasses import dataclass

CUSTOM_MODE = 0x14

# direction values the firmware expects
DIR_LEFT, DIR_RIGHT, DIR_UP, DIR_DOWN = 0, 1, 2, 3


@dataclass(frozen=True)
class Effect:
    name: str
    value: int
    speed: bool = True
    color: bool = True      # accepts a chosen colour
    random: bool = True     # supports "random colours"
    directions: tuple = ()  # e.g. ("Left", "Right")


EFFECTS = [
    Effect("Static", 0x06, speed=False),
    Effect("Breathing", 0x05),
    Effect("Spectrum Cycle", 0x04, color=False, random=False),
    Effect("Color Wave", 0x02, directions=("Left", "Right")),
    Effect("Color Wave (Short)", 0x01, directions=("Left", "Right")),
    Effect("Color Wheel", 0x03, directions=("Left", "Right")),
    Effect("Vertical Rainbow", 0x0C, directions=("Up", "Down")),
    Effect("Rainbow Circle", 0x12, speed=False, color=False),
    Effect("Hurricane", 0x0D),
    Effect("Accumulate", 0x0E),
    Effect("Starlight", 0x0A),
    Effect("Starlight (Slow)", 0x0F),
    Effect("Visor", 0x10, speed=False),
    Effect("Blooming", 0x0B, color=False),
    Effect("Reactive", 0x07),
    Effect("Reactive Ripple", 0x08),
    Effect("Reactive Line", 0x09),
]

BY_NAME = {e.name.lower(): e for e in EFFECTS}

DIRECTION_VALUES = {"Left": DIR_LEFT, "Right": DIR_RIGHT, "Up": DIR_UP, "Down": DIR_DOWN}
