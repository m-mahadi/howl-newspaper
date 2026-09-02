"""Catalog and crop paper-native figures and tables from a PDF.

Geometry is deterministic; an agent chooses which catalog candidate best carries
the paper's central result.

The crop geometry was ported from Bayaz with Monir's explicit approval; report
templates, styling, prose, and pipeline were not imported.

Usage:
    python paper_figures.py catalog paper.pdf --emit-crops crops
    python paper_figures.py crop paper.pdf c00 crops/paper__Figure1.png
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import fitz


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


CAPTION = re.compile(r"^\s*(Figure|Fig\.?|Table)\s*([0-9]+)", re.IGNORECASE)


def page_graphics(page: fitz.Page) -> list[fitz.Rect]:
    """Return raster images, image blocks, and clustered vector drawings."""
    rects: list[fitz.Rect] = []
    for image in page.get_images(full=True):
        try:
            rects.extend(fitz.Rect(rect) for rect in page.get_image_rects(image[0]))
        except Exception:
            pass
    for block in page.get_text("blocks"):
        if block[6] == 1:
            rects.append(fitz.Rect(block[:4]))
    try:
        rects.extend(page.cluster_drawings())
    except Exception:
        drawings = page.get_drawings()
        if drawings:
            union = fitz.Rect(drawings[0]["rect"])
            for drawing in drawings[1:]:
                union |= fitz.Rect(drawing["rect"])
            rects.append(union)
    return [rect for rect in rects if rect.width > 12 and rect.height > 12]


def _complete_sentence(text: str) -> bool:
    return text.rstrip().rstrip("”’\")]").endswith((".", "!", "?"))


def full_caption(page: fitz.Page, caption_rect: fitz.Rect, text: str) -> fitz.Rect:
    """Extend a split caption without swallowing adjacent body text."""
    if _complete_sentence(text):
        return fitz.Rect(caption_rect)
    page_rect = page.rect
    gap = page_rect.height * 0.02
    max_add = page_rect.height * 0.14
    region = fitz.Rect(caption_rect)
    blocks = sorted(
        (
            (fitz.Rect(block[:4]), block[4])
            for block in page.get_text("blocks")
            if block[6] == 0
        ),
        key=lambda item: item[0].y0,
    )
    for rect, continuation in blocks:
        if rect.y0 <= caption_rect.y0 + 1:
            continue
        if CAPTION.match(continuation.strip()):
            break
        if rect.y0 - region.y1 > gap or rect.y1 - caption_rect.y1 > max_add:
            break
        overlap = min(rect.x1, caption_rect.x1) - max(rect.x0, caption_rect.x0)
        if overlap <= 0.25 * caption_rect.width:
            continue
        region |= rect
        if _complete_sentence(continuation):
            break
    return region


def _tabular(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    digits = sum(character.isdigit() for character in text)
    average_line_length = sum(len(line) for line in lines) / len(lines)
    prose_punctuation = text.count(". ") + text.count(", ")
    return digits >= 4 and average_line_length < 70 and prose_punctuation <= 2


def associated_region(
    page: fitz.Page,
    caption_rect: fitz.Rect,
    kind: str,
    graphics: list[fitz.Rect],
) -> fitz.Rect:
    """Join a caption to its figure above or table below."""
    page_rect = page.rect
    band = page_rect.height * 0.62
    is_table = kind.lower().startswith("t")
    region = fitz.Rect(caption_rect)
    for graphic in graphics:
        overlap = min(graphic.x1, caption_rect.x1) - max(graphic.x0, caption_rect.x0)
        if overlap <= -0.15 * page_rect.width:
            continue
        if is_table:
            near = 0 <= graphic.y0 - caption_rect.y1 < band or (
                abs(graphic.y0 - caption_rect.y1) < band and graphic.y0 > caption_rect.y0
            )
        else:
            near = 0 <= caption_rect.y0 - graphic.y1 < band or (
                graphic.y1 <= caption_rect.y1 and caption_rect.y1 - graphic.y0 < band
            )
        if near:
            region |= graphic

    if region.height < caption_rect.height * 1.25:
        blocks = [
            (fitz.Rect(block[:4]), block[4])
            for block in page.get_text("blocks")
            if block[6] == 0 and fitz.Rect(block[:4]) != caption_rect
        ]
        gap = page_rect.height * 0.045
        if is_table:
            sequence = sorted(
                (item for item in blocks if item[0].y0 >= caption_rect.y1 - 2),
                key=lambda item: item[0].y0,
            )
        else:
            sequence = sorted(
                (item for item in blocks if item[0].y1 <= caption_rect.y0 + 2),
                key=lambda item: -item[0].y1,
            )
        for rect, text in sequence:
            overlap = min(rect.x1, region.x1) - max(rect.x0, region.x0)
            edge = rect.y0 - region.y1 if is_table else region.y0 - rect.y1
            if edge > gap:
                break
            if overlap <= 0 or not _tabular(text):
                continue
            if is_table and rect.y1 - caption_rect.y1 > band:
                continue
            if not is_table and caption_rect.y0 - rect.y0 > band:
                continue
            region |= rect

    padding = 0.006 * page_rect.width
    return fitz.Rect(
        region.x0 - padding,
        region.y0 - padding,
        region.x1 + padding,
        region.y1 + padding,
    ) & page_rect


def _abstract(document: fitz.Document) -> str:
    first_page = document[0].get_text()
    match = re.search(
        r"Abstract(.{0,1600}?)(\n1\s|\nIntroduction|\n1\.)",
        first_page,
        re.DOTALL | re.IGNORECASE,
    )
    return " ".join((match.group(1) if match else first_page[:1200]).split())[:1200]


def catalog_pdf(pdf: Path, emit_crops: Path | None = None) -> dict:
    """Return JSON-ready metadata and deterministic crop boxes."""
    if emit_crops:
        emit_crops.mkdir(parents=True, exist_ok=True)
    candidates: list[dict] = []
    seen: set[tuple[str, int]] = set()
    with fitz.open(pdf) as document:
        for page_number in range(document.page_count):
            page = document[page_number]
            page_rect = page.rect
            graphics = page_graphics(page)
            for block in page.get_text("blocks"):
                if block[6] != 0:
                    continue
                text = block[4].strip()
                match = CAPTION.match(text)
                if not match:
                    continue
                kind = "Table" if match.group(1).lower().startswith("t") else "Figure"
                label = f"{kind} {match.group(2)}"
                key = (label, page_number)
                if key in seen:
                    continue
                seen.add(key)
                caption_rect = full_caption(page, fitz.Rect(block[:4]), text)
                region = associated_region(page, caption_rect, kind, graphics)
                bbox = [
                    round((region.x0 - page_rect.x0) / page_rect.width, 4),
                    round((region.y0 - page_rect.y0) / page_rect.height, 4),
                    round((region.x1 - page_rect.x0) / page_rect.width, 4),
                    round((region.y1 - page_rect.y0) / page_rect.height, 4),
                ]
                candidate = {
                    "id": f"c{len(candidates):02d}",
                    "kind": kind,
                    "label": label,
                    "page": page_number,
                    "caption": " ".join(text.split())[:220],
                    "bbox_frac": bbox,
                    "area_frac": round((bbox[2] - bbox[0]) * (bbox[3] - bbox[1]), 4),
                }
                candidates.append(candidate)
                if emit_crops:
                    crop(document, candidate, emit_crops / f"{candidate['id']}-p{page_number}.png", 2.4)
        return {
            "paper": str(pdf),
            "pages": document.page_count,
            "abstract": _abstract(document),
            "candidates": candidates,
        }


def crop(
    document: fitz.Document,
    candidate: dict,
    output: Path,
    scale: float = 3.0,
) -> None:
    """Render one catalog candidate to PNG."""
    if scale <= 0:
        raise ValueError("scale must be positive")
    page = document[candidate["page"]]
    page_rect = page.rect
    x0, y0, x1, y1 = candidate["bbox_frac"]
    clip = fitz.Rect(
        page_rect.x0 + x0 * page_rect.width,
        page_rect.y0 + y0 * page_rect.height,
        page_rect.x0 + x1 * page_rect.width,
        page_rect.y0 + y1 * page_rect.height,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False).save(output)


def crop_candidate(pdf: Path, candidate_id: str, output: Path, scale: float = 3.0) -> dict:
    catalog = catalog_pdf(pdf)
    candidate = next(
        (item for item in catalog["candidates"] if item["id"] == candidate_id),
        None,
    )
    if candidate is None:
        raise ValueError(f"unknown candidate: {candidate_id}")
    with fitz.open(pdf) as document:
        crop(document, candidate, output, scale)
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    catalog_command = commands.add_parser("catalog")
    catalog_command.add_argument("pdf", type=Path)
    catalog_command.add_argument("--emit-crops", type=Path)
    crop_command = commands.add_parser("crop")
    crop_command.add_argument("pdf", type=Path)
    crop_command.add_argument("candidate_id")
    crop_command.add_argument("output", type=Path)
    crop_command.add_argument("--scale", type=float, default=3.0)
    args = parser.parse_args()

    if args.command == "catalog":
        print(json.dumps(catalog_pdf(args.pdf, args.emit_crops), ensure_ascii=False, indent=2))
    else:
        chosen = crop_candidate(args.pdf, args.candidate_id, args.output, args.scale)
        print(json.dumps({"output": str(args.output), "candidate": chosen}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
