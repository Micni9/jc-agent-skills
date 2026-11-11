# todo-tracking：工作中發現但未處理問題的追蹤清單

把「發現了但這次不處理」的問題寫進專案根目錄的 `TODO.md`，讓它們不會隨著對話消失。提供 `scripts/todo.ps1` 進行 CRUD，並以固定格式維護 `TODO.md`，agent 與人工都可讀寫。

> 詳細規則、優先級、記錄時機、`TODO.md` 格式請見 [SKILL.md](SKILL.md)。

---

## 檔案

| 路徑 | 說明 |
| --- | --- |
| `SKILL.md` | skill 入口：核心規則、何時記錄、優先級、腳本指令與參數、`TODO.md` 格式、回報格式 |
| `scripts/todo.ps1` | PowerShell CRUD 工具（PowerShell 5.1+ 或 pwsh 7+） |
| `scripts/todo.mjs` | 跨平台 CRUD 工具（Node.js 18+，無外部依賴；Linux / macOS / Windows） |

---

## 快速開始

```powershell
# PowerShell 5.1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/todo.ps1 <command> [args]

# PowerShell 7
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/todo.ps1 <command> [args]
```

範例：

```powershell
# 印出 TODO.md 的絕對路徑（依專案標記向上尋找）
.\scripts\todo.ps1 path

# 建立 TODO.md（已存在則不覆蓋）
.\scripts\todo.ps1 init

# 新增項目
.\scripts\todo.ps1 add -Title "匯入端點缺稽核策略" -Priority P1 `
  -Location "src/main/java/com/pollex/fm/web/rest/ExcelDataExchangeResource.java:33" `
  -Note "factory 回傳 null，aspect 未檢查空值" -Impact "匯入操作不留稽核紀錄"

# 列出未完成項目
.\scripts\todo.ps1 list

# 列出全部（含已完成）
.\scripts\todo.ps1 list -Status all

# 依優先級篩選並輸出 JSON
.\scripts\todo.ps1 list -Priority P0 -Json

# 顯示單一項目
.\scripts\todo.ps1 show TODO-0001

# 修改欄位（空字串會清除該欄位）
.\scripts\todo.ps1 update TODO-0001 -Priority P0 -Fix "新增 DataExchangeImportLoggingStrategy"

# 標記完成 / 重新開啟 / 刪除
.\scripts\todo.ps1 done TODO-0001
.\scripts\todo.ps1 reopen TODO-0001
.\scripts\todo.ps1 remove TODO-0001
```

---

## 跨平台（Node.js 18+）

```bash
node scripts/todo.mjs <command> [args]
```

範例：

```bash
node scripts/todo.mjs path
node scripts/todo.mjs init
node scripts/todo.mjs add --title "匯入端點缺稽核策略" --priority P1 --location "src/a/B.java:42" --note "factory 回傳 null"
node scripts/todo.mjs list
node scripts/todo.mjs list --status all --json
node scripts/todo.mjs show TODO-0001
node scripts/todo.mjs update TODO-0001 --priority P0 --fix "新增策略"
node scripts/todo.mjs done TODO-0001
node scripts/todo.mjs reopen TODO-0001
node scripts/todo.mjs remove TODO-0001
```

參數、環境變數（`TODO_FILE` / `TODO_ROOT`）與專案根目錄偵測規則與 `todo.ps1` 完全相同；兩者可交錯編輯同一份 `TODO.md`。

## 指令一覽

| 指令 | 用途 |
| --- | --- |
| `path` | 印出 `TODO.md` 的絕對路徑 |
| `init` | 建立 `TODO.md`（已存在則不覆蓋） |
| `add` | 新增項目，自動配發 `TODO-NNNN` ID |
| `list` | 列出項目（預設只列未完成；`-Status all`/`done`；`-Priority`；`-Json`） |
| `show` | 顯示單一項目全文 |
| `update` | 修改欄位（`-Title`/`-Priority`/`-Location`/`-Note`/`-Impact`/`-Fix`） |
| `done` | 標記完成並寫入完成日期 |
| `reopen` | 取消完成 |
| `remove` | 刪除項目 |
| `help` | 顯示使用說明 |

---

## 專案根目錄偵測

`TODO.md` 的位置依下列順序決定，第一個命中的為準（詳見 SKILL.md「專案根目錄偵測」）：

| 順序 | 來源 | 說明 |
| --- | --- | --- |
| 1 | `-TodoFile <路徑>` | 直接指定檔案；相對路徑以目前目錄為基準 |
| 2 | 環境變數 `TODO_FILE` | 同上；空字串或全空白視為未設定 |
| 3 | 環境變數 `TODO_ROOT` | 指定專案根目錄，檔案為 `<TODO_ROOT>/TODO.md` |
| 4 | 專案標記 | 從目前目錄往上，最近的含標記目錄 |
| 5 | 目前目錄 | 都沒有標記時的後備，不報錯 |

專案標記（任一即算，`.git` 是檔案也算，例如 worktree）：

`.git`、`package.json`、`pyproject.toml`、`setup.py`、`go.mod`、`Cargo.toml`、`pom.xml`、`build.gradle`、`*.sln`、`*.csproj`、`composer.json`、`Gemfile`

```powershell
$env:TODO_ROOT = "C:\repo\my-project"      # TODO.md 放到 C:\repo\my-project\TODO.md
$env:TODO_FILE = "C:\repo\docs\TODO.md"    # 直接指定檔案，優先於 TODO_ROOT
```

---

## 檔案編碼與寫入

- `TODO.md` 一律以 **UTF-8（無 BOM）、LF 換行** 寫入；讀取時接受 CRLF 與 BOM。
- 寫入採 **原子替換**（同目錄暫存檔 + rename），中斷不會留下半寫檔案。
- 內容保留 Traditional Chinese、emoji、全形標點，不產生 mojibake。

---

## 需求

- PowerShell 5.1+（`powershell.exe`）或 PowerShell 7+（`pwsh`），**或** Node.js 18+（使用 `todo.mjs`）。
- Windows / Linux / macOS 皆可執行；PowerShell 腳本在非 Windows 環境請使用 `pwsh`。

---

## 注意事項

- **只記錄，不修改**：記錄問題時不要順手改程式碼；修不修由使用者決定。
- **先查重**：寫入前先 `list -Status all`，同一位置的同一問題不要重複記錄。
- **不主動 commit**：`TODO.md` 是專案檔案，未經使用者要求不要提交。
- PowerShell 5.1 下，重新導向的 stdout 會依終端機字碼頁輸出（本機 CP950），`TODO.md` 檔案內容仍為正確 UTF-8；若需擷取中文輸出，請使用 `pwsh` 或設定 `[Console]::OutputEncoding` 為 UTF-8。
- 更多細節與 `TODO.md` 格式規範請見 [SKILL.md](SKILL.md)。