import argparse
import csv
import os
import sys
import time
import urllib.parse
from pathlib import Path
import importlib
import subprocess


def ensure_dependencies(packages):
    """Ensure the given packages are installed (pip names -> import paths).

    `packages` is a list of tuples: (pip_name, import_path, as_name)
    After installation, the imported modules are placed into globals() under
    the provided `as_name`.
    """
    missing = []
    for pip_name, import_path, _ in packages:
        try:
            importlib.import_module(import_path)
        except ImportError:
            missing.append(pip_name)

    if missing:
        print(f"[INFO] Installing missing packages: {' '.join(missing)}")
        cmd = [sys.executable, "-m", "pip", "install", *missing]
        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Failed to install packages: {e}")
            sys.exit(1)

    for _, import_path, as_name in packages:
        module = importlib.import_module(import_path)
        globals()[as_name] = module


# Ensure runtime deps (requests, Pillow)
ensure_dependencies([
    ("requests", "requests", "requests"),
    ("Pillow", "PIL.Image", "Image"),
])


# =========================
# Configuration
# =========================
API_DELAY_SECONDS = 0.12
OUTPUT_SIZE = (816, 1110)
BORDER_PIXELS = 40
USER_AGENT = "ProxyFall/1.0"

HEADERS = {
    "User-Agent": USER_AGENT
}


# =========================
# Utility helpers
# =========================

def print_banner():
    """Display the program banner."""
    print(r"""
  _____                     ______    _ _ 
 |  __ \                   |  ____|  | | |
 | |__) | __ _____  ___   _| |__ __ _| | |
 |  ___/ '__/ _ \ \/ / | | |  __/ _` | | |
 | |   | | | (_) >  <| |_| | | | (_| | | |
 |_|   |_|  \___/_/\_\\__, |_|  \__,_|_|_|
                       __/ |              
                      |___/               
""")
    print("by Adam Smith\n")


def sanitize_path_input(path_text: str) -> str:
    """Strip surrounding quotes and whitespace from a provided file path."""
    if path_text is None:
        return None
    return path_text.strip().strip('"\'')


def sanitize_folder_name(name: str) -> str:
    """Generate a safe folder name from an arbitrary string."""
    invalid_chars = '<>:"/\\|?*'
    return ''.join('_' if ch in invalid_chars else ch for ch in name).strip()


def prompt_yes_no(prompt: str) -> bool:
    """Ask a yes/no question and return True for yes."""
    answer = input(prompt).strip().lower()
    return answer in ("y", "yes")


# =========================
# Decklist parsing
# =========================

def load_deck_csv(csv_file):
    """Read a decklist CSV and return {card_id: quantity}."""
    deck = {}
    csv_path = Path(csv_file)

    with open(csv_path, newline="", encoding="utf-8") as file:
        rows = [row for row in csv.reader(file) if any(cell.strip() for cell in row)]

    if not rows:
        return deck

    header = [cell.strip().lower() for cell in rows[0]]
    has_header = any(h in header for h in ("id", "card_id")) and any(h in header for h in ("quantity", "qty"))

    if has_header:
        idx_id = next(i for i, h in enumerate(header) if h in ("id", "card_id"))
        idx_qty = next(i for i, h in enumerate(header) if h in ("quantity", "qty"))
        data_rows = rows[1:]
    else:
        idx_qty = 0
        idx_id = 1
        data_rows = rows

    for row in data_rows:
        if len(row) <= max(idx_id, idx_qty):
            print(f"[WARN] Skipping malformed row: {row}")
            continue

        card_id = row[idx_id].strip()
        qty_text = row[idx_qty].strip()

        if not card_id:
            print(f"[WARN] Skipping row with empty card id: {row}")
            continue

        try:
            quantity = int(qty_text)
        except ValueError:
            print(f"[WARN] Invalid quantity '{qty_text}' for id '{card_id}', skipping")
            continue

        deck[card_id] = quantity

    return deck


# =========================
# Image download and processing
# =========================

def fetch_card_image(card_id, path, face=None):
    """Download a card image from Scryfall, optionally requesting a back face."""
    url = f"https://api.scryfall.com/cards/{card_id}?format=image&version=png"
    if face:
        url += f"&face={face}"

    try:
        response = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=30)
        if response.status_code != 200:
            try:
                body = response.json()
            except Exception:
                body = response.text

            print(f"[FAIL] {card_id} HTTP {response.status_code} {response.reason}")
            print(f"[API RESPONSE] {body}")
            return False

        with open(path, "wb") as out_file:
            out_file.write(response.content)

        print(f"[OK] Downloaded image for {card_id}")
        return True

    except Exception as error:
        print(f"[ERROR] {card_id}: {error}")
        return False


def upscale_image(image_path):
    """Resize the image to the configured output size."""
    with Image.open(image_path) as img:
        upscaled = img.resize(OUTPUT_SIZE, Image.Resampling.LANCZOS)
        upscaled.save(image_path)
    print(f"[OK] Upscaled to {OUTPUT_SIZE}")


def apply_border(image_path):
    """Add a solid black border around the image."""
    with Image.open(image_path) as img:
        new_width = img.width + BORDER_PIXELS * 2
        new_height = img.height + BORDER_PIXELS * 2
        canvas = Image.new("RGB", (new_width, new_height), (0, 0, 0))
        canvas.paste(img, (BORDER_PIXELS, BORDER_PIXELS))
        canvas.save(image_path)
    print(f"[OK] Added {BORDER_PIXELS}px border")


def export_card_copies(image_path, card_id, quantity, output_dir):
    """Write one or more card copy files to the output folder."""
    for copy_index in range(1, quantity + 1):
        filename = f"{card_id}_{copy_index:03}.png"
        destination = Path(output_dir) / filename
        with open(image_path, "rb") as source, open(destination, "wb") as target:
            target.write(source.read())
    print(f"[OK] Exported {quantity} copies")


# =========================
# User interaction
# =========================

def prompt_deckfile_path(cli_path=None):
    """Return a valid decklist path from CLI argument or interactive prompt.

    Requires an explicit path from the user; empty input will be rejected.
    """
    if cli_path:
        normalized = sanitize_path_input(cli_path)
        candidate = Path(normalized) if normalized else None
        if candidate and candidate.exists() and candidate.is_file():
            return candidate
        print(f"[WARN] Provided deckfile not found: {candidate}")

    while True:
        try:
            user_input = input("Enter path to decklist CSV (required): ")
        except (KeyboardInterrupt, EOFError):
            print("\n[ERROR] No decklist provided. Exiting.")
            sys.exit(1)

        normalized = sanitize_path_input(user_input)
        if not normalized:
            print("[ERROR] Decklist path is required. Please enter a valid path.")
            continue

        candidate = Path(normalized)
        if candidate.exists() and candidate.is_file():
            return candidate

        print(f"[ERROR] Decklist file not found: {candidate}")


def search_card_by_name(card_name):
    """Search Scryfall for a card by name and return the first result."""
    quoted = urllib.parse.quote(card_name)
    url = f"https://api.scryfall.com/cards/search?q={quoted}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code != 200:
            try:
                body = response.json()
            except Exception:
                body = response.text
            print(f"[FAIL] Search HTTP {response.status_code} {response.reason}")
            print(f"[API RESPONSE] {body}")
            return None
        data = response.json()
        results = data.get("data", [])
        return results[0] if results else None
    except Exception as error:
        print(f"[ERROR] Search request failed: {error}")
        return None


def prompt_back_faces(output_dir):
    """Prompt the user for back-face cards and process them interactively."""
    while prompt_yes_no("Do you require any back faces of cards (double sided planeswalkers/MDFCs etc.)? (Y/N): "):
        card_name = input("Enter card name to search: ").strip()
        if not card_name:
            print("Please enter a card name.")
            continue

        result = search_card_by_name(card_name)
        if not result:
            if prompt_yes_no("No match found. Try another name? (Y/N): "):
                continue
            return

        found_name = result.get("name", "<unknown>")
        set_name = result.get("set_name") or result.get("set", "<unknown>")
        print(f"Found: {found_name} — {set_name}")

        if not prompt_yes_no("Is this correct? (Y/N): "):
            if prompt_yes_no("Return to previous step to enter card name? (Y/N): "):
                continue
            return

        card_id = result.get("id")
        if not card_id:
            print("[ERROR] Selected result does not contain an ID.")
            return

        temp_path = Path(output_dir) / f"{card_id}_back.png"
        if not fetch_card_image(card_id, temp_path, face="back"):
            print("Failed to download back face image.")
            return

        upscale_image(temp_path)
        apply_border(temp_path)
        print(f"Saved back face image to {temp_path}")

        if prompt_yes_no("Are you done? (Y/N): "):
            return


# =========================
# Main program flow
# =========================

def run():
    print_banner()

    parser = argparse.ArgumentParser(description="ProxyFall deck image generator")
    parser.add_argument("deckfile", nargs="?", default=None, help="Path to decklist CSV (will prompt if omitted)")
    args = parser.parse_args()

    deckfile_path = prompt_deckfile_path(args.deckfile)
    output_folder = Path.home() / "Pictures" / sanitize_folder_name(deckfile_path.stem)
    output_folder.mkdir(parents=True, exist_ok=True)

    deck = load_deck_csv(deckfile_path)
    card_count = len(deck)

    print(f"Loaded {card_count} cards from {deckfile_path}")
    print(f"Saving outputs to: {output_folder}\n")

    for index, (card_id, quantity) in enumerate(deck.items(), start=1):
        time.sleep(API_DELAY_SECONDS)
        temp_path = output_folder / f"{card_id}.png"

        if not fetch_card_image(card_id, temp_path):
            continue

        upscale_image(temp_path)
        apply_border(temp_path)
        export_card_copies(temp_path, card_id, quantity, output_folder)

        remaining = card_count - index
        print(f"{remaining} cards left to export\n")
        os.remove(temp_path)

    print("\nDone.")
    prompt_back_faces(output_folder)


if __name__ == "__main__":
    run()
