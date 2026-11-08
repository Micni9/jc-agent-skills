---
name: todo-tracking
description: 把工作中發現但未處理的問題記錄到專案根目錄的 TODO.md，並用腳本做 CRUD。當你發現 bug、風險、規格矛盾、待確認事項、技術債，或使用者說「先記下來」「之後再處理」「記錄 TODO」「列出現有 TODO」「關閉/刪除 TODO 項目」時使用。Log unhandled issues discovered during work into the project TODO.md with a script for create, list, update, close, and delete.
---

# Todo Tracking

把「發現了但這次不處理」的問題寫進專案根目錄的 `TODO.md`，讓它們不會隨著對話消失。

## 核心規則

1. **只記錄，不修改**。記錄問題時不要順手改程式碼。修不修由使用者決定。專案規則（`AGENTS.md`）另有規定者從其規定。
2. **只記真實問題**。必須是你實際看到、可指出位置的東西，不要寫猜測或「可能可以更好」的建議清單。
3. **先查重**。寫入前先 `list -Status all`，同一個位置的同一個問題不要重複記錄；已有項目就 `update` 補充說明。
4. **位置要可追**。`-Location` 用 `相對路徑:行號`，相對於專案根目錄。
5. **不主動 commit**。`TODO.md` 是專案檔案，未經使用者要求不要提交。
6. **專案要求自動記錄時直接寫**。若專案規則（`AGENTS.md` 或本機 instructions 檔）規定發現問題即記錄，不用先問使用者；與當前任務無關的問題只記錄、不修正。

## 何時記錄

符合任一條就記：

- 讀程式碼時發現的 bug、空值未檢查、錯誤的欄位、複製貼上的殘留。
- 前後不一致：文件寫 A、程式做 B；同一個概念有兩種實作。
- 缺少的防護：無稽核、無權限檢查、無例外處理、無邊界檢查。
- 使用者要求「先跳過」「之後再說」「這個先不修」的項目。
- 你無法在不確定的前提下完成的待確認事項（例如「需向 PM 確認欄位定義」）。

不要記：

- 你已經在這次修改中修掉的東西。
- 風格偏好、命名喜好這類沒有具體影響的意見。
- 需要大量脈絡才看得懂的模糊描述（先寫清楚再記）。

## 流程

1. 確認目標檔案：執行 `path`，看 `TODO.md` 會落在哪個目錄（預設是最近的 `.git` 上層目錄）。
2. 查重：`list -Status all`。
3. 決定優先級（見下表）。
4. 用 `add` 寫入，至少給 `-Title` 與 `-Location`，`-Note` 說明現象與為什麼是問題。
5. 回報使用者：記了什麼、ID 是多少、在哪個檔案。

## 優先級

| 級別 | 判斷標準 |
| --- | --- |
| `P0` | 資料錯誤、資料遺失、安全漏洞、正式環境會壞。 |
| `P1` | 功能行為與預期不符，使用者會遇到，但目前有 workaround。 |
| `P2` | 特定條件下才觸發的錯誤、缺少的防護、不一致的實作。 |
| `P3` | 技術債、可讀性、重複程式碼、缺測試。 |

不確定就用 `P2`。不要全部標 `P1`，那等於沒有優先級。

## 腳本

位置：`scripts/todo.ps1`（相對於本 SKILL.md）。

```powershell
$todo = "$HOME/.config/opencode/skills/todo-tracking/scripts/todo.ps1"

# PowerShell 5.1
powershell -NoProfile -ExecutionPolicy Bypass -File $todo <command> [args]

# PowerShell 7
pwsh -NoProfile -ExecutionPolicy Bypass -File $todo <command> [args]
```

Windows 以外或沒有 PowerShell 時，直接依下方格式手動編輯 `TODO.md`。

### 指令

| 指令 | 用途 | 範例 |
| --- | --- | --- |
| `path` | 印出 `TODO.md` 的絕對路徑 | `todo.ps1 path` |
| `init` | 建立 `TODO.md`（已存在則不覆蓋） | `todo.ps1 init` |
| `add` | 新增項目，自動配發 ID | `todo.ps1 add -Title "..." -Priority P1 -Location "src/a/B.java:42" -Note "..."` |
| `list` | 列出項目，預設只列未完成 | `todo.ps1 list`、`todo.ps1 list -Status all`、`todo.ps1 list -Priority P0` |
| `show` | 顯示單一項目全文 | `todo.ps1 show TODO-0003` |
| `update` | 修改欄位 | `todo.ps1 update TODO-0003 -Priority P0 -Fix "..."` |
| `done` | 標記完成並寫入完成日期 | `todo.ps1 done TODO-0003` |
| `reopen` | 取消完成 | `todo.ps1 reopen TODO-0003` |
| `remove` | 刪除項目 | `todo.ps1 remove TODO-0003` |

### 參數

- `-Title`：一句話描述問題（必填於 `add`）。
- `-Priority`：`P0` / `P1` / `P2` / `P3`，預設 `P1`。
- `-Location`：`相對路徑:行號`。
- `-Note`：現象與原因。
- `-Impact`：不修的後果。
- `-Fix`：建議做法。
- `-Status`：`open`（預設）/ `done` / `all`，只用於 `list`。
- `-TodoFile`：指定檔案，覆寫自動偵測（可給相對或絕對路徑）。
- `-Json`：`list` 輸出 JSON 陣列，方便程式處理。

`add` 會自動填 `發現` 為當天日期；`done` 會填 `完成`。ID 取現有最大值加一。

## TODO.md 格式

```markdown
# TODO

> 未處理問題清單。agent 於工作中發現問題時記錄，不自行修改。
> 格式固定，請使用 `scripts/todo.ps1` 增刪改。
> 手動編輯時，補充說明請放在項目的縮排清單內，例如 `  - 位置: path:line`。

- [ ] TODO-0001 [P1] 匯入端點缺稽核策略
  - 位置: src/main/java/com/pollex/fm/aop/log/strategy/AuditLoggingFactory.java:20
  - 說明: factory 找不到策略時回傳 null，aspect 未檢查空值
  - 影響: 匯入操作不留稽核紀錄
  - 建議: 新增 DataExchangeImportLoggingStrategy
  - 發現: 2026-11-04
- [x] TODO-0002 [P2] AnswerDetail 使用 getAnswerId
  - 位置: src/main/java/com/pollex/fm/service/strategy/AnswerDetailExchangeStrategy.java:36
  - 說明: 疑似應為 getId()
  - 發現: 2026-11-04
  - 完成: 2026-11-05
```

規則：

- 標題行：`- [ ] TODO-NNNN [Pn] 標題`；完成時 `[ ]` 改成 `[x]`。
- 縮排說明行：`  - 欄位: 值`，欄位限 `位置`、`說明`、`影響`、`建議`、`發現`、`完成`。
- 每個項目之間空一行（腳本輸出時不空行，兩者都可解析）。
- 寫入時項目依 ID 數字排序；無法識別的縮排行與檔案尾端其他段落會原樣保留。

## 腳本不可用時

直接編輯 `TODO.md`，遵守上面格式：

- 新增：選最大的 `TODO-NNNN` 加一，補上 `- 位置:`、`- 說明:`、`- 發現:`。
- 完成：`[ ]` 改 `[x]`，加 `- 完成: yyyy-MM-dd`。
- 刪除：整塊移除，不留空行殘骸。

寫完後用 `list -Status all`（若腳本可用）確認解析正常。

## 回報格式

記錄後告訴使用者：

- 記了幾個項目、ID 各是什麼。
- `TODO.md` 的完整路徑。
- 若項目需要決策（例如「要現在修還是排後面」），直接問。
