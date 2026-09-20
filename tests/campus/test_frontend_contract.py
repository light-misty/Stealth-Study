"""前后端契约守卫：前端 `campus/api.ts` 声明的端点必须全部真实存在（03 §4、04 §5）。

联调阶段暴露的最大一处缺口，正是这个文件要防的事：前端 `CAMPUS_ENDPOINTS` 声明了 74 个
端点，真实后端只挂载 63 个操作，缺的 12 个（B 组资料库、D1-D3 错题本、D7 归因、I1 人设）
前端有函数、有面板、有 i18n 文案，浏览器里点下去只有 404——而 mock 化的 e2e 因为给这些
路径编造了响应，一直显示正常。

因此这里做两件事：

* **端点集合**：把 `campus/api.ts` 的声明解析成 `(method, path)` 集合，逐个断言它落在
  `build_campus_router()` 真实注册的路由里（占位符按形状归一，`{pid}` 与 `{doc_id}` 等价）。
  反向不设断言：后端允许存在前端暂未接线的端点（例如 I5 下载由 `exportDownloadUrl` 拼 URL）。
* **鉴权头**：前端发出的头名必须是后端 `_request_authenticated` 读的那个（`x-ss-token`）。
  文档 03 §1/04 §6.1 写作 `X-StealthStudy-Token`，实现是 `X-SS-Token`，T15 已按实现为准；
  这条断言让"文档与实现的差异"不会再演化成"前端与后端的差异"。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from stealth_study.campus import routes

ROOT = Path(__file__).resolve().parents[2]
API_TS = ROOT / "surfaces" / "gui" / "src" / "campus" / "api.ts"
SERVER_APP = ROOT / "ss" / "server" / "app.py"

_ENDPOINT_ROW = re.compile(
    r'id:\s*"(?P<id>[^"]+)",\s*method:\s*"(?P<method>[A-Z]+)",\s*path:\s*"(?P<path>[^"]+)"'
)
_HEADER = re.compile(r'headers\.set\(\s*"(?P<name>X-[^"]+)"')


def frontend_endpoints() -> list[tuple[str, str, str]]:
    """`(id, method, path)` for every row of the frontend's `CAMPUS_ENDPOINTS` table."""
    source = API_TS.read_text(encoding="utf-8")
    block = source[source.index("export const CAMPUS_ENDPOINTS") :]
    return [
        (match.group("id"), match.group("method"), match.group("path"))
        for match in _ENDPOINT_ROW.finditer(block)
    ]


def backend_operations() -> set[tuple[str, str]]:
    """Every `(method, normalized path)` the router actually registers."""
    router = routes.build_campus_router(object())
    operations: set[tuple[str, str]] = set()
    for route in router.routes:
        for method in route.methods:
            operations.add((method, re.sub(r"\{[^}]+\}", "{}", route.path)))
    return operations


def test_the_frontend_actually_declares_its_endpoint_table() -> None:
    declared = frontend_endpoints()
    assert declared, f"{API_TS} 里没有解析到 CAMPUS_ENDPOINTS"
    assert len(declared) >= 70, f"端点表疑似被截断：只解析到 {len(declared)} 行"


def test_every_declared_frontend_endpoint_is_mounted_on_the_backend() -> None:
    mounted = backend_operations()
    missing = [
        f"{endpoint_id} {method} {path}"
        for endpoint_id, method, path in frontend_endpoints()
        if (method, re.sub(r"\{[^}]+\}", "{}", path)) not in mounted
    ]
    assert missing == [], "前端声明但后端未挂载的端点：" + "、".join(missing)


def test_the_frontend_never_declares_a_path_outside_the_campus_prefix() -> None:
    strays = [path for _, _, path in frontend_endpoints() if not path.startswith(routes.CAMPUS_PREFIX)]
    assert strays == [], f"campus/api.ts 声明了前缀之外的路径：{strays}"


def test_the_auth_header_matches_the_backend_middleware() -> None:
    """The frontend picks the header name in `campus/api.ts` and calls the app's own helpers."""
    source = API_TS.read_text(encoding="utf-8")
    names = {match.group("name").lower() for match in _HEADER.finditer(source)}
    assert names, "campus/api.ts 里没有解析到鉴权头"
    middleware = SERVER_APP.read_text(encoding="utf-8")
    assert 'request.headers.get("x-ss-token"' in middleware, "后端中间件读取的头名变了"
    assert names == {"x-ss-token"}, f"前端发出的鉴权头与后端不一致：{sorted(names)}"


@pytest.mark.parametrize("endpoint_id", ["A2", "B1", "C1", "D1", "F11", "G3", "H4", "I1"])
def test_a_sample_of_ids_survives_the_parse(endpoint_id: str) -> None:
    """Guard the parser itself: a regex that silently stops matching would fake a green run."""
    assert endpoint_id in {row[0] for row in frontend_endpoints()}
