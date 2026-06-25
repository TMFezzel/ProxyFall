# ProxyFall

ProxyFall is a Python utility that downloads MTG card images from Scryfall, upscales them, adds a border, and exports the requested number of copies for use with MPC.

## Features

- Reads a decklist CSV from an interactive prompt
- Supports both headered and headerless CSV input
- Saves processed images to a new folder under the user's `Pictures` directory named after the decklist file
- Upscales card images to `816x1110`
- Adds a solid black border around each image
- Exports duplicate copies by quantity
- Optionally downloads and processes back faces for double-sided cards

## Requirements

- Python 3.11+
- `requests` library (will be installed if not present)
- `Pillow` library (will be installed if not present)

Install dependencies with:

```bash
python -m pip install requests pillow
```

## Usage

***Decklist from Archidekt should be exported into CSV using the columns of Scryfall ID and Quantity only.***

Run the program from the `Python` folder:

```bash
python ProxyFall.py
```

Or provide a decklist path directly:

```bash
python ProxyFall.py "C:\path\to\decklist.csv"
```

If no path is given, the program prompts for one.



## Decklist format

ProxyFall accepts:

- Headerless CSV with `quantity,id` columns
- Headered CSV with either `id,quantity` or `quantity,id`
- Header names are detected case-insensitively

Example headerless row:

```csv
3,9bac8176-d0db-4397-820d-acbdd3264377
```

Example headered CSV:

```csv
quantity,id
3,9bac8176-d0db-4397-820d-acbdd3264377
```

## Back-face workflow

After exporting the main card images, ProxyFall asks whether you need any back faces for double-sided cards. If you answer yes, it:

1. Prompts for a card name
2. Searches Scryfall for the first matching card
3. Confirms the result with you
4. Downloads the back face image.
5. Upscales and borders the image in the same output folder

## Output location

Processed files are saved to:

```
%USERPROFILE%\Pictures\<decklist-name>
```

For example, a decklist named `decklist.csv` saves output to:

```
C:\Users\YourName\Pictures\decklist
```
