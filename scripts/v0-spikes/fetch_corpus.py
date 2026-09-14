"""SPIKE-2 / T02 语料抓取器（V0.0 临时脚本，非入库代码）。

从公开可再分发来源抓取 docs/dev/07-开发任务分解.md T02 要求的 5 本中文 PDF：
  >=2 本无书签无目录页讲义 + >=2 本章节规范教材 + 1 本扫描件。
每本钉住 URL 与 sha256，落盘后校验；校验失败即失败退出，不静默降级。
语料仅落 scripts/v0-spikes/corpus/（.gitignore 排除），不入库、不再分发。

用法：
  python scripts/v0-spikes/fetch_corpus.py --dest scripts/v0-spikes/corpus
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import urllib.parse
import urllib.request

RAW_TSC = (
    "https://raw.githubusercontent.com/PKUanonym/REKCARC-TSC-UHT/master/"
    + urllib.parse.quote("")
)

MANIFEST = [
    {
        "doc_id": "jc_hello_algo",
        "file": "jc_hello_algo.pdf",
        "class": "textbook",
        "title": "Hello 算法（中文版，Python 语言描述）",
        "source": "https://github.com/krahets/hello-algo releases 1.3.0",
        "license": "CC BY-NC-SA 4.0 / 仓库公开可下载",
        "url": "https://github.com/krahets/hello-algo/releases/download/1.3.0/"
        "hello-algo_1.3.0_zh_python.pdf",
        "sha256": "7a1bb221fe4e968b7fef16bbde24b20db07b339f0d6552ab5109cdc3a23bb5bb",
        "bytes": 16176086,
    },
    {
        "doc_id": "jc_docker",
        "file": "jc_docker.pdf",
        "class": "textbook",
        "title": "Docker——从入门到实践（v1.11.0）",
        "source": "https://github.com/yeasy/docker_practice releases v1.11.0",
        "license": "CC BY-NC-SA 4.0 / 仓库公开可下载",
        "url": "https://github.com/yeasy/docker_practice/releases/download/v1.11.0/"
        "docker_practice-v1.11.0.pdf",
        "sha256": "a2a7d57ee3e2585bb2b5405a491c73d24cda4edbf69b45a5589316860f66f972",
        "bytes": 17874228,
    },
    {
        "doc_id": "jy_xitike",
        "file": "jy_xitike.pdf",
        "class": "handout",
        "title": "数值分析 第三次习题课课件",
        "source": "https://github.com/PKUanonym/REKCARC-TSC-UHT 大三下/数值分析/hw/习题课/",
        "license": "学生自建课程资料仓库，公开可下载",
        "url": RAW_TSC
        + urllib.parse.quote("大三下/数值分析/hw/习题课/第三次习题课课件.pdf"),
        "sha256": "4989b58a828ff869e6e653bb31e40e71bca3c871db20fd12b2df91af77a31e2c",
        "bytes": 1776535,
    },
    {
        "doc_id": "jy_os_ch2",
        "file": "jy_os_ch2.pdf",
        "class": "handout",
        "title": "操作系统课程讲义（第 2 章）",
        "source": "https://github.com/iamxiatian/course_os pdf/ch2.pdf",
        "license": "公开课程仓库，公开可下载",
        "url": "https://raw.githubusercontent.com/iamxiatian/course_os/master/pdf/ch2.pdf",
        "sha256": "039cdd0f00f54ebdc70a25f2e399d773b6d4886f1d93ddaecd4663e6f64fc7f8",
        "bytes": 1008331,
    },
    {
        "doc_id": "scan_fubian",
        "file": "scan_fubian.pdf",
        "class": "scan",
        "title": "复变函数引论 手写笔记（影印扫描件）",
        "source": "https://github.com/PKUanonym/REKCARC-TSC-UHT 大二上/复变函数引论/exam/杨大伯/笔记/",
        "license": "学生自建课程资料仓库，公开可下载",
        "url": RAW_TSC
        + urllib.parse.quote("大二上/复变函数引论/exam/杨大伯/笔记/复变笔记by马玉冰(处理后).pdf"),
        "sha256": "aa439ebbe88c22b0f589e6f8c0f8a9ff624419989e6ebd44ace1873358512bd2",
        "bytes": 33569267,
    },
]


def sha256_of(path: pathlib.Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            data = fh.read(chunk)
            if not data:
                break
            digest.update(data)
    return digest.hexdigest()


def download(url: str, dest: pathlib.Path, retries: int = 3) -> None:
    last = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ss-spike-corpus"})
            with urllib.request.urlopen(req, timeout=240) as resp, open(dest, "wb") as fh:
                while True:
                    block = resp.read(1 << 20)
                    if not block:
                        break
                    fh.write(block)
            return
        except Exception as exc:
            last = exc
    raise RuntimeError(f"下载失败 {url}: {type(last).__name__}: {last}")


def fetch(dest: pathlib.Path, force: bool = False) -> list[dict]:
    dest.mkdir(parents=True, exist_ok=True)
    report = []
    for item in MANIFEST:
        target = dest / item["file"]
        if force or not target.exists():
            download(item["url"], target)
        actual = sha256_of(target)
        ok = actual == item["sha256"]
        size = target.stat().st_size
        report.append(
            {
                "doc_id": item["doc_id"],
                "file": item["file"],
                "class": item["class"],
                "title": item["title"],
                "source": item["source"],
                "license": item["license"],
                "url": item["url"],
                "sha256_expected": item["sha256"],
                "sha256_actual": actual,
                "bytes": size,
                "verified": ok,
            }
        )
        print(f"[{'OK ' if ok else 'BAD'}] {item['doc_id']:14s} {size/1048576:7.2f} MB  {actual[:16]}", flush=True)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="抓取 SPIKE-2 中文 PDF 语料")
    parser.add_argument("--dest", default="scripts/v0-spikes/corpus")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--manifest-out", default=None)
    args = parser.parse_args(argv)
    dest = pathlib.Path(args.dest)
    report = fetch(dest, force=args.force)
    manifest_path = pathlib.Path(args.manifest_out) if args.manifest_out else dest / "corpus_manifest.json"
    manifest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if not all(entry["verified"] for entry in report):
        print("语料校验失败：sha256 不匹配，终止。", file=sys.stderr)
        return 1
    print(f"语料就绪：{dest}（清单 {manifest_path}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
