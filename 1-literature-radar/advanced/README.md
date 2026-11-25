# advanced/：進階流程「AI 讀事實、程式對照帳本」

**一句話**：不問 AI「這篇值不值得收」，而是讓 AI 只把摘要讀成幾個事實（講的是哪個數字、哪一年的資料、哪個國家、用哪份資料庫），再由一段寫死的規則拿這些事實去比對「你現在手上用的資料」，並把比對理由寫在報告上。

> **注意：這個資料夾裡的圖層是失智症研究專用的示範。**
> `ledger.dementia-example.json` 裡的「失智症盛行率、輕度認知障礙、PM2.5、風險比」只是範例，來源與年份是示範填法，不代表任何真實專案。你要用，必須把整份帳本換成自己研究要追的數字（見下面 C 段）。
> 這個流程只適合「你手上有一張清單，記錄每個數字用的是哪份資料、哪一年」的人，例如追蹤流行病學統計數字的更新。如果你只是想每月掃一遍新論文，**請用根目錄 README 的預設流程**，不要用這個。

## 為什麼需要它

預設流程把判準寫在設定檔的 `rubric` 裡，叫 AI 判斷保留或篩掉。這在「判準只看論文本身」時很好用（例如只收隨機對照試驗）。
但如果問題是「這篇比我現有的資料更新嗎」，AI 不知道你現有什麼，常會留下「論文是新的、資料卻是舊的」或「換了作者、用的仍是同一份資料庫」的論文。
所以把工作拆開：AI 只讀事實；比較交給程式；你更新帳本，判斷就跟著更新。

## 你需要先準備

- 已能跑根目錄 README 的 A 段（在自己電腦跑過一次預設流程）。
- 一份你自己的帳本（見下）。
- 至少一組 AI 金鑰：這個流程**沒有金鑰就不會判斷**（全部列出，跟預設流程一樣的退路）。

## 檔案

| 檔案 | 用途 |
|---|---|
| `literature_watch_ledger.py` | 進階版的執行入口，選項和 `scripts/literature_watch.py` 完全相同 |
| `facts.py` | 叫 AI 把摘要讀成事實；題目裡的「圖層」清單由你的帳本自動產生 |
| `triage_rules.py` | 事實與帳本的比對規則（純程式，不連網、不用 AI） |
| `ledger.dementia-example.json` | **失智症專用的示範帳本**，要換成你自己的 |
| `config.dementia-example.json` | 示範設定檔，多一個 `ledger` 欄位指向帳本 |
| `tests/` | 離線測試 |

## SOP

### A 在自己電腦跑
1. **在哪做**：終端機（Windows 用 PowerShell、Mac 用 Terminal），位置在專案根目錄（有 `scripts/` 和 `advanced/` 的那一層）。
2. 先確認規則沒壞，貼上：`python -m unittest discover -s advanced/tests`
   預期最後一行是 `OK`。沒看到：把整段輸出貼給 AI 請它協助看。
3. 設好金鑰（見根目錄 README 的 A 段第 6 步），貼上：
   `python advanced/literature_watch_ledger.py --config advanced/config.dementia-example.json --triage --seen-file seen.json --out report.md`
   這一步會連網、並把論文標題與摘要送到你設定的 AI 服務。預期產生 `report.md`，AI 那一行寫「AI 只讀出論文的事實……由 某某 讀取」。
4. 打開 `report.md`：被收合的論文旁邊有「比對理由」，例如 `data 2010 <= KR in use ... (2018)`，意思是這篇的資料年份不比你帳本裡的新。

### B 放上 GitHub 每月自動跑
把根目錄 `.github/workflows/literature-radar.yml` 裡執行的那一行，從
`python scripts/literature_watch.py --config config/literature-watch.json ...`
改成
`python advanced/literature_watch_ledger.py --config advanced/config.json ...`
（其餘參數照舊），並把你改好的設定檔與帳本放在 `advanced/` 底下。其他步驟與根目錄 README 的 B 段相同。

### C 換成你自己的帳本
帳本是一個 JSON 檔，分三塊：

1. `layers`：你要追的每一個「數字」是一個圖層。每個圖層寫：
   - `key`：英文代號，小寫加底線。
   - `description`：一句英文，說這個圖層是哪種數字（AI 靠這句判斷論文屬於哪個圖層）。
   - `measures`：這個圖層接受哪幾種數字（例如 `prevalence`、`incidence`、`relative_risk`、`share`、`exposure`）。論文報告的數字種類不在清單內，就判為不相關。
   - `rules`（選填）：這個圖層的特殊規定，可用的有三個：
     `need_representative`（預設 true：只有能代表整個國家或地區的樣本才算）、
     `exclude_methods`（這類資料來源不能用，例如 `["administrative"]`）、
     `require_method`（只有這種方法才算，例如 `"meta_analysis"`）。
2. `defaults`：每個圖層你現在用的資料，寫 `source`（資料名稱）和 `year`（資料涵蓋的年份，如 `2019-2023`）。
3. `overrides`（選填）：某個國家有比較細的資料時，用兩位國碼（如 `KR`）覆蓋預設。

改完後：
- 把設定檔的 `ledger` 指到你的帳本（路徑相對於設定檔所在資料夾）。
- 設定檔的 `topics` 換成你的查詢句（寫法見 `config/README.md`）。
- 設定檔裡不需要 `rubric`，進階流程不用它。
- 先用 `--fixture` 或真實跑一次，確認被保留的論文真的是「比帳本新」。

## 哪裡用 LLM、哪裡一定要人看

- **LLM**：只做「把摘要讀成事實」。事實可能讀錯（年份、國家、資料來源），尤其摘要沒寫清楚時。
- **程式**：比對規則是固定的，同樣事實一定得到同樣結論。
- **一定要人看**：保留下來的每一篇都要打開原文確認資料年份與來源；被收合的也請抽查，看理由是否合理。帳本本身由你維護，帳本寫錯，判斷就跟著錯。

## 限制

- 帳本裡的「資料年份」是你自己登記的，程式不會幫你查證。
- 用兩個資料庫「名稱裡有相同的關鍵字」來判斷是不是同一份資料；名稱寫法差很多時會判不出來，退回比較年份。
- AI 沒有金鑰或全部失敗時，不會判斷，只會全列並明寫。
- 國碼只支援兩位字母的 ISO 3166-1 alpha-2。

授權：程式 MIT、文件 CC BY-NC 4.0。
