# 開發環境設定

## 環境

- OS: Ubuntu 22.04（透過 WSL2 on Windows）
- Python: 3.11（系統內建 `/usr/bin/python3.11`）
- 套件管理: [uv](https://docs.astral.sh/uv/)（安裝在 `~/.local/bin/uv`）

## 重要：必須在 WSL 內執行

專案位於 WSL 檔案系統，**所有指令都必須透過 WSL 執行**，否則會遇到路徑或權限問題：

```bash
wsl -d Ubuntu-22.04 bash -lc "cd /home/joseph/archery-score-reader && <指令>"
```

`bash -lc` 是必要的（login shell），確保 `~/.local/bin/uv` 在 PATH 中。

## 首次設定

```bash
wsl -d Ubuntu-22.04 bash -lc "cd /home/joseph/archery-score-reader && uv sync"
```

如果 `.venv` 有殘留的 Windows Python 連結，先刪再重建：

```bash
wsl -d Ubuntu-22.04 bash -lc "cd /home/joseph/archery-score-reader && rm -rf .venv && uv venv --python 3.11 && uv sync"
```

## 執行 Python 程式碼

```bash
wsl -d Ubuntu-22.04 bash -lc "cd /home/joseph/archery-score-reader && uv run python -c 'print(1)'"
```

## 執行測試

`pytest` 在 WSL-on-Windows 掛載路徑下沒有執行權限，必須用 `python -m pytest`：

```bash
wsl -d Ubuntu-22.04 bash -lc "cd /home/joseph/archery-score-reader && uv pip install 'pytest>=8.0' && uv run python -m pytest tests/ -v"
```

## 執行 CLI

```bash
wsl -d Ubuntu-22.04 bash -lc "cd /home/joseph/archery-score-reader && uv run python -m score_reader.cli --help"
```

## 執行 Shell Scripts

```bash
wsl -d Ubuntu-22.04 bash -lc "cd /home/joseph/archery-score-reader && bash scripts/run_detection_workflow.sh"
```

## 常見問題

| 問題 | 原因 | 解法 |
|------|------|------|
| `uv: command not found` | 沒用 login shell | 用 `bash -lc` |
| `Permission denied` 跑 pytest | WSL 掛載的 .venv/bin 沒執行權限 | 用 `python -m pytest` |
| `VIRTUAL_ENV=. does not match` | Windows 的 uv 搶先執行 | 確保透過 `wsl -d` 執行 |
