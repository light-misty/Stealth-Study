# ss GUI (React + Tauri)

ss 服务器的一个薄客户端（OpenAI 兼容 API + WS 事件/审批流）。
同一套代码在浏览器（开发模式）和 偷偷学 桌面应用中运行。

## 首次运行：引导 Python 后端

新检出时没有可运行的服务器——创建以下两种流程都需要的 venv
（从仓库根目录执行）：

```bash
bash packaging/setup_dev_env.sh   # → .venv (server + aisuite)
```

## 运行方式（浏览器，两个终端）

1. **启动服务器**（需要环境中已配置模型 Key，例如 `OPENAI_API_KEY` ——
   或稍后应用的设置中添加），从仓库根目录执行：
   ```bash
   ./.venv/bin/stealthstudy-server --cwd /path/to/your/project --port 8765
   ```
2. **启动 UI：**
   ```bash
   cd surfaces/gui
   npm install      # 首次运行时
   npm run dev      # → http://localhost:5173
   ```

打开 http://localhost:5173。UI 会与 `http://127.0.0.1:8765` 通信（可通过
`VITE_COWORKER_HTTP` / `VITE_COWORKER_WS` 覆盖）。请在 Vite 之前启动服务，
以便 UI 从 `<state-dir>/sidecar-8765.token` 读取每次启动的令牌；如果服务重启，
请同步重启 Vite。

## 从源码运行桌面应用

Tauri 外壳包裹相同的 UI，并自行管理 Python 服务器——无需单独的终端。
它需要 Rust 工具链（`rustup`）和引导步骤中的 venv；在开发模式下，它会自动
找到 `.venv/bin/stealthstudy-server` 路径下的服务器。

```bash
cd surfaces/gui
npm install        # 首次运行时
npm run tauri dev  # 构建外壳、启动窗口、启动服务器
```

## 测试

```bash
npx tsc --noEmit && npx vitest run   # 类型检查 + 单元测试
npx playwright test                  # 端到端隔离测试（mock /v1 + WS，无需 Python）
```
