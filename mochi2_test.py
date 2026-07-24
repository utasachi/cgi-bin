from pathlib import Path

titles = set()

for ass_file in Path(r"F:\karaoke").rglob("*.ass"):
    try:
        with open(ass_file, "r", encoding="utf-8-sig", errors="ignore") as f:
            for line in f:
                if line.startswith("Title:"):
                    titles.add(line[6:].strip())
                    break
    except Exception as e:
        print(f"Error: {ass_file} ({e})")

for title in sorted(titles):
    print(title)