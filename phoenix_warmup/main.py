"""
main.py
Phoenix Warm-Up Engine — Entry Point
Phoenix Solutions © 2024

PyInstaller-compatible entry point.
Run directly: python main.py
Export:       pyinstaller --onefile --windowed main.py
"""
import sys
import os
from pathlib import Path


# ── Path resolution (PyInstaller-safe) ────────────────────────────────────── #

def get_base_dir() -> Path:
    """
    Returns the application base directory.
    - Development: directory containing main.py
    - PyInstaller bundle: directory containing the .exe (not _MEIPASS)
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def get_assets_dir() -> Path:
    """
    Assets (logo images) are bundled inside the PyInstaller archive
    at _MEIPASS/assets, but stored alongside the exe for dev mode.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", str(get_base_dir()))) / "assets"
    return Path(__file__).parent / "assets"


def get_data_dir() -> Path:
    """Data directory always lives next to the exe / script (writable)."""
    d = get_base_dir() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Add project root to sys.path (for non-frozen development) ─────────────── #
if not getattr(sys, "frozen", False):
    project_root = str(Path(__file__).parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)


# ── Load .env before any other imports ────────────────────────────────────── #
def _load_env() -> None:
    env_path = get_base_dir() / ".env"
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=env_path, override=False)
    except ImportError:
        pass  # python-dotenv not installed; use system env vars


# ── Generate logo if missing ───────────────────────────────────────────────── #
def _ensure_logo() -> None:
    """Generate a simple programmatic logo PNG if none exists."""
    assets_dir = get_assets_dir()
    assets_dir.mkdir(parents=True, exist_ok=True)
    logo_path = assets_dir / "phoenix_logo.png"
    if logo_path.exists():
        return
    try:
        from PIL import Image, ImageDraw, ImageFont
        size = 128
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Orange circle background
        draw.ellipse([4, 4, size - 4, size - 4], fill="#FF6A00")
        # White "P" letter
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
        except Exception:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), "P", font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (size - text_w) // 2 - bbox[0]
        y = (size - text_h) // 2 - bbox[1]
        draw.text((x, y), "P", fill="white", font=font)
        img.save(logo_path, "PNG")
    except Exception:
        pass  # Logo generation is optional


# ── Main ───────────────────────────────────────────────────────────────────── #
def main() -> None:
    _load_env()
    _ensure_logo()

    data_dir = get_data_dir()
    assets_dir = get_assets_dir()

    from app import App
    application = App(data_dir=data_dir, assets_dir=assets_dir)
    application.run()


if __name__ == "__main__":
    main()
