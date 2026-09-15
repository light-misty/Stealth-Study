"""Generate all app icon variants from the new icon source (v5).

Tauri 2's new icon handling requires at least one high-quality PNG (>=512x512)
alongside a multi-resolution .ico for Windows installers. PNG icons are preferred
because Tauri can regenerate platform-specific .icns at build time on macOS.
"""
import os
from PIL import Image

SRC = r"D:\DeskTop\Stealth-Study-replace-app-icon\docs\assets\偷偷学APP图标.png"
ICONS_DIR = r"D:\DeskTop\Stealth-Study-replace-app-icon\surfaces\gui\src-tauri\icons"
GUI_ASSETS = r"D:\DeskTop\Stealth-Study-replace-app-icon\surfaces\gui\assets"
DMG_DIR = r"D:\DeskTop\Stealth-Study-replace-app-icon\packaging"

src = Image.open(SRC).convert("RGBA")
sw, sh = src.size
print(f"Source: {sw}x{sh}, mode={src.mode}")

# -- 1. PNG variants for Tauri config & windows tiles --
PNG_SIZES = {
    "32x32.png": 32,
    "64x64.png": 64,
    "128x128.png": 128,
    "128x128@2x.png": 256,
    "icon.png": 1024,
    "Square30x30Logo.png": 30,
    "Square44x44Logo.png": 44,
    "Square71x71Logo.png": 71,
    "Square89x89Logo.png": 89,
    "Square107x107Logo.png": 107,
    "Square142x142Logo.png": 142,
    "Square150x150Logo.png": 150,
    "Square284x284Logo.png": 284,
    "Square310x310Logo.png": 310,
    "StoreLogo.png": 50,
    "tray.png": 44,
}
for name, size in PNG_SIZES.items():
    out = src.resize((size, size), Image.LANCZOS)
    out.save(os.path.join(ICONS_DIR, name), optimize=True)
    print(f"  [PNG] {name} {size}x{size}")

# -- 2. Multi-resolution ICO (for Windows installer PE resource embedding) --
ICO_SIZES = [16, 32, 48, 64, 128, 256]
ico_imgs = {s: src.resize((s, s), Image.LANCZOS) for s in ICO_SIZES}
main = ico_imgs[ICO_SIZES[-1]]
rest = [ico_imgs[s] for s in ICO_SIZES[:-1]]
main.save(
    os.path.join(ICONS_DIR, "icon.ico"),
    format="ICO",
    sizes=[(s, s) for s in ICO_SIZES],
    append_images=rest,
)
print(f"  [ICO] icon.ico contains dimensions: {ICO_SIZES}")

# -- 3. tray.rgba (raw RGBA pixels for system tray) --
tray = src.resize((44, 44), Image.LANCZOS)
rgba_bytes = tray.tobytes("raw", "RGBA")
with open(os.path.join(ICONS_DIR, "tray.rgba"), "wb") as f:
    f.write(rgba_bytes)
print(f"  [RGBA] tray.rgba {len(rgba_bytes)} bytes (44x44 RGBA)")

# -- 4. surfaces/gui/assets/icon.png (PWA favicon / dev marker) --
web_icon = src.resize((512, 512), Image.LANCZOS)
web_icon.save(os.path.join(GUI_ASSETS, "icon.png"), optimize=True)
print(f"  [PNG] surfaces/gui/assets/icon.png 512x512")

# -- 5. DMG background with new icon overlaid --
# Store originals first, then overwrite outputs from their masters in the right
# order so masters are not consumed as inputs before we've finished with them.
TIFF_SRC = os.path.join(DMG_DIR, "dmg-background.tiff")
PNG_1X = os.path.join(DMG_DIR, "dmg-background.png")
PNG_2X_ORIG = os.path.join(DMG_DIR, "dmg-background@2x.png")

# Read the original masters once, in a safe order.
with Image.open(PNG_2X_ORIG) as bg2x:
    bg2x_master = bg2x.copy().convert("RGBA")
    bw2m, bh2m = bg2x_master.size
print(f"  [DMG] @2x master original size: {bw2m}x{bh2m}")

with Image.open(TIFF_SRC) as tiff:
    tiff_master = tiff.copy()
    tw, th = tiff_master.size
print(f"  [DMG] TIFF master original size: {tw}x{th}")

with Image.open(PNG_1X) as png1x:
    png1x_master = png1x.copy().convert("RGBA")
    pw, ph = png1x_master.size
print(f"  [DMG] 1x PNG master original size: {pw}x{ph}")

def embed_icon(bg: Image.Image, scale: float):
    bw, bh = bg.size
    target = int(min(bw, bh) * scale)
    scaled = src.resize((target, target), Image.LANCZOS)
    x = (bw - scaled.width) // 2
    y = (bh - scaled.height) // 2
    bg.paste(scaled, (x, y), scaled)
    return target, x, y

# 1x (resized from 1x master appearance)
icon_sz, ix, iy = embed_icon(png1x_master, 0.35)
png1x_master.convert("RGB").save(PNG_1X, optimize=True)
print(f"  [DMG] dmg-background.png {pw}x{ph}, icon={icon_sz}px center ({ix},{iy})")

# @2x (from 2x master)
icon_sz2, ix2, iy2 = embed_icon(bg2x_master, 0.35)
bg2x_master.convert("RGB").save(PNG_2X_ORIG, optimize=True)
print(f"  [DMG] dmg-background@2x.png {bw2m}x{bh2m}, icon={icon_sz2}px center ({ix2},{iy2})")

# TIFF master: replace with icon-embedded version from the @2x canvas to preserve
# full fidelity for future regeneration
tiff_master_rgba = bg2x_master if bg2x_master.mode == "RGBA" else bg2x_master.convert("RGBA")
# keep alpha on save so the TIFF file is lossless
bg2x_master.save(TIFF_SRC)
print(f"  [DMG] dmg-background.tiff replaced with icon-embedded master {bg2x_master.size}")

print("\nAll icons generated successfully.")
