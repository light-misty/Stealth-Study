"""T01 SPIKE-1 语料抓取与归一化：公开四六级范文库 -> 20 篇批改样本。

来源（唯一来源，允许再分发并保留版权声明）：
  ZhaoyuanLiu23/CET-Prompt-Hub, essays/{topic}_{level}.pdf
  5 话题（adversity / collaboration / courage / innovation / perseverance）
  x 2 级别（cet4 / cet6），每份 PDF 内含同话题 3 篇范文。

归一化规则见 README.md；产出自带 sha256 便于复核。
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent / "corpus"
CACHE_DIR = CORPUS_DIR / ".cache"

SOURCE = {
    "id": "cet-prompt-hub",
    "title": "ZhaoyuanLiu23/CET-Prompt-Hub — CET-4/6 sample essays",
    "repo_url": "https://github.com/ZhaoyuanLiu23/CET-Prompt-Hub",
    "raw_base": "https://raw.githubusercontent.com/ZhaoyuanLiu23/CET-Prompt-Hub/main/",
    "revision": "main",
}

TOPICS = ["adversity", "collaboration", "courage", "innovation", "perseverance"]
LEVELS = ["cet4", "cet6"]

WORD_LIMIT = {"cet4": {"min": 120, "max": 180}, "cet6": {"min": 150, "max": 200}}

CJK = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")
SECTION_SPLIT = re.compile(r"第([一二三四五六七八九十]+)篇：")
PARAGRAPH_MARK = re.compile(r"^\**\s*Paragraph\s*\d+\s*\([^)]*\)\s*:?\s*\**$")
WORD_COUNT_MARK = re.compile(r"[（(]\s*总词数\s*[:：]\s*(\d+)\s*[)）]")
ENGLISH_BODY_MARK = re.compile(r"英文全文")
TRANSLATION_MARK = re.compile(r"整体中文翻译")
CJK_PAREN = re.compile(r"[（(][^（()）]*[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef][^（()）]*[)）]")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")
SINGLE_LETTER = re.compile(r"(?<!['A-Za-z-])([b-hj-z])(?!['A-Za-z-])")
DOUBLE_SPACE = re.compile(r"  +")

ARTIFACT_REPAIRS: tuple[tuple[str, str], ...] = (
    ("outcomes b ased on", "outcomes based on"),
    ("agreement o n every", "agreement on every"),
    ("hardships a nd providing", "hardships and providing"),
    ("costs for co llective benefit", "costs for collective benefit"),
    ("courage is paralyze d.", "courage is paralyzed."),
    ("his bagless vacuum cleane r.", "his bagless vacuum cleaner."),
)


def fetch(url: str, dest: Path, tries: int = 4) -> bytes:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 1000:
        return dest.read_bytes()
    last: Exception | None = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "stealth-study-v0-spike"})
            with urllib.request.urlopen(req, timeout=90) as resp:
                chunks = b""
                while True:
                    piece = resp.read(65536)
                    if not piece:
                        break
                    chunks += piece
            dest.write_bytes(chunks)
            return chunks
        except http.client.IncompleteRead as exc:
            if exc.partial and len(exc.partial) > 1000:
                dest.write_bytes(exc.partial)
                return exc.partial
            last = exc
        except Exception as exc:
            last = exc
        time.sleep(2)
    raise RuntimeError(f"download failed: {url} ({last})")


def pdf_pages(path: Path) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return [(page.extract_text() or "") for page in reader.pages]


def _join_lines(lines: list[str]) -> str:
    out = ""
    for raw in lines:
        line = raw.strip().replace("**", "")
        if not line:
            continue
        if not out:
            out = line
        elif out.endswith("-"):
            out += line
        else:
            out += " " + line
    return out


def _clean_english(text: str) -> str:
    text = text.replace("**", "")
    text = CJK_PAREN.sub("", text)
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"\(\s*\)", "", text)
    return text.strip()


def _word_count(text: str) -> int:
    return len(WORD_RE.findall(text))


def apply_artifact_repairs(text: str, applied: dict[str, int]) -> str:
    for broken, fixed in ARTIFACT_REPAIRS:
        hits = text.count(broken)
        if hits:
            applied[broken] = applied.get(broken, 0) + hits
            text = text.replace(broken, fixed)
    return text


def verify_repairs(applied: dict[str, int]) -> None:
    missing = [broken for broken, _ in ARTIFACT_REPAIRS if broken not in applied]
    if missing:
        raise RuntimeError(
            "ARTIFACT_REPAIRS 未命中，说明语料或修复表已漂移，需重新核对: " + repr(missing)
        )


def verify_corpus(corpus: dict) -> list[str]:
    problems: list[str] = []
    for essay in corpus["essays"]:
        label = essay["essay_id"]
        texts = {"essay": essay["essay"]}
        if essay["reference"]:
            texts["reference"] = essay["reference"]["text"]
        for field, text in texts.items():
            tag = f"{label}.{field}"
            if CJK.search(text):
                problems.append(f"{tag}: 残留 CJK 字符")
            if DOUBLE_SPACE.search(text):
                problems.append(f"{tag}: 连续空格")
            if SINGLE_LETTER.search(text):
                problems.append(
                    f"{tag}: 单字母碎片 {SINGLE_LETTER.search(text).group(1)!r}（疑似 PDF 断词）"
                )
            if not text.endswith((".", "!", "?")):
                problems.append(f"{tag}: 未以句末标点结束")
            words = _word_count(text)
            if not 90 <= words <= 260:
                problems.append(f"{tag}: 词数越界 {words}")
            if len([s for s in re.split(r"[.!?]+", text) if s.strip()]) < 5:
                problems.append(f"{tag}: 句子数不足 5")
        if essay["role_group"] == "paired" and not essay["reference"]:
            problems.append(f"{label}: paired 组缺少参考范文对照")
        if essay["role_group"] == "solo" and essay["reference"]:
            problems.append(f"{label}: solo 组不应带参考范文对照")
    return problems


def split_sections(pages: list[str]) -> list[list[str]]:
    lines: list[str] = []
    for page in pages:
        lines.extend(page.splitlines())
    marks = [i for i, line in enumerate(lines) if SECTION_SPLIT.search(line)]
    sections: list[list[str]] = []
    for idx, start in enumerate(marks):
        end = marks[idx + 1] if idx + 1 < len(marks) else len(lines)
        sections.append(lines[start:end])
    return sections


def parse_section(section: list[str], applied: dict[str, int]) -> dict | None:
    head = section[0].strip()
    title = SECTION_SPLIT.split(head, maxsplit=1)[-1].strip()
    body_lines = section[1:]

    stated_word_count = None
    style = "cet4_freeform"
    if any(ENGLISH_BODY_MARK.search(line) for line in body_lines):
        style = "cet6_annotated"
        start = next(i for i, line in enumerate(body_lines) if ENGLISH_BODY_MARK.search(line))
        stop = next(
            (i for i, line in enumerate(body_lines) if TRANSLATION_MARK.search(line)),
            len(body_lines),
        )
        body_lines = body_lines[start + 1 : stop]
        body_lines = [line for line in body_lines if not PARAGRAPH_MARK.match(line.strip())]
    else:
        stop = next(
            (i for i, line in enumerate(body_lines) if WORD_COUNT_MARK.search(line)),
            len(body_lines),
        )
        match = WORD_COUNT_MARK.search("\n".join(body_lines))
        if match:
            stated_word_count = int(match.group(1))
        body_lines = body_lines[:stop]

    body = apply_artifact_repairs(_clean_english(_join_lines(body_lines)), applied)
    if not body:
        return None
    return {
        "section_title": title,
        "style": style,
        "essay": body,
        "extracted_word_count": _word_count(body),
        "stated_word_count": stated_word_count,
    }


def build_corpus() -> dict:
    applied: dict[str, int] = {}
    groups: list[dict] = []
    for topic in TOPICS:
        for level in LEVELS:
            name = f"{topic}_{level}.pdf"
            url = SOURCE["raw_base"] + "essays/" + name
            raw = fetch(url, CACHE_DIR / name)
            digest = hashlib.sha256(raw).hexdigest()
            sections = split_sections(pdf_pages(CACHE_DIR / name))
            essays = [
                item for item in (parse_section(sec, applied) for sec in sections) if item
            ]
            groups.append(
                {
                    "group_id": f"{topic}-{level}",
                    "topic": topic,
                    "level": level,
                    "source_file": f"essays/{name}",
                    "source_url": url,
                    "sha256": digest,
                    "essay_count": len(essays),
                    "essays": essays,
                }
            )

    records: list[dict] = []
    for group in groups:
        essays = group["essays"]
        if len(essays) < 3:
            raise RuntimeError(f"group {group['group_id']} expected >=3 essays, got {len(essays)}")
        plan = [("paired", essays[0], essays[2]), ("solo", essays[1], None)]
        for role, essay, reference_essay in plan:
            index = len(records) + 1
            reference = None
            if reference_essay is not None:
                reference = {
                    "text": reference_essay["essay"],
                    "role": "same_topic_reference",
                    "source_file": group["source_file"],
                    "sha256": group["sha256"],
                    "section_title": reference_essay["section_title"],
                    "note": "同话题另一篇范文，作为人工对照参考",
                }
            records.append(
                {
                    "essay_id": f"E{index:02d}",
                    "group_id": group["group_id"],
                    "role_group": role,
                    "track": group["level"],
                    "topic": group["topic"],
                    "prompt": f"话题：{group['topic']}（{group['group_id']}）",
                    "prompt_kind": "source_topic_verbatim",
                    "title": essay["section_title"],
                    "essay": essay["essay"],
                    "word_limit": WORD_LIMIT[group["level"]],
                    "extracted_word_count": essay["extracted_word_count"],
                    "stated_word_count": essay["stated_word_count"],
                    "source_file": group["source_file"],
                    "source_url": group["source_url"],
                    "sha256": group["sha256"],
                    "reference": reference,
                }
            )

    paired = [r for r in records if r["role_group"] == "paired"]
    solo = [r for r in records if r["role_group"] == "solo"]
    manifest = {
        "corpus_version": 1,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": SOURCE,
        "groups": [
            {k: v for k, v in group.items() if k != "essays"} for group in groups
        ],
        "essay_count": len(records),
        "paired_count": len(paired),
        "solo_count": len(solo),
        "levels": LEVELS,
        "policy": {
            "redistributable": True,
            "basis": "语料为英文范文正文，含中文注释已在归一化中剥离，"
            "中文标题保留在 section 字段用于溯源",
            "not_official_prompts": "prompt 字段取上游话题声明原文，非官方考试 Directions",
            "stated_word_count_note": "上游 PDF 的『总词数』标注与朴素词数统计口径不同，"
            "以 extracted_word_count 为准，两者差异不作质量判据",
        },
        "applied_repairs": applied,
    }
    corpus = {
        "corpus_version": 1,
        "built_at": manifest["built_at"],
        "source_id": SOURCE["id"],
        "source_url": SOURCE["repo_url"],
        "essays": records,
    }
    return {"manifest": manifest, "corpus": corpus}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="构建 T01 批改 spike 语料")
    parser.add_argument("--out-dir", default=str(CORPUS_DIR))
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    built = build_corpus()
    manifest = built["manifest"]
    corpus = built["corpus"]

    verify_repairs(manifest["applied_repairs"])
    problems = verify_corpus(corpus)

    write_json(out_dir / "cet_essays.json", corpus)
    write_json(out_dir / "corpus_manifest.json", manifest)

    print(
        f"essays={manifest['essay_count']} paired={manifest['paired_count']} solo={manifest['solo_count']}"
    )
    for group in manifest["groups"]:
        print(f"  {group['group_id']}: {group['essay_count']} essays sha256={group['sha256'][:12]}")
    print(f"applied_repairs={manifest['applied_repairs']}")
    print(f"word_counts={[e['extracted_word_count'] for e in corpus['essays']]}")
    if problems:
        print("INTEGRITY FAILURES:")
        for item in problems:
            print("  -", item)
        return 1
    print("integrity=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
