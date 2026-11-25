# ③ 取材：拿到對的論文全文，而且知道它「對」

> 授權：程式 MIT、文件 CC BY-NC 4.0。

## 這是什麼

萃取之前要先有全文。這一階段有兩件事：**怎麼合法、有順序地拿到檔案**（見 `PDF取得SOP.md`），以及**拿到之後怎麼確認這個檔案真的是你要的那一篇、沒被撤稿**（見 `驗證四級與攔截規則.md`）。

## 你需要先準備什麼

- `01_plan/` 的專案說明書（尤其「資料分級」）。
- 論文清單：每篇至少 PMID（PubMed 編號）或 DOI（論文永久編號）。本資料夾的 `papers.csv` 是 5 篇示範清單。
- Python 3.9 以上。
- 做 `check_doi.py` 真實查詢時，需要能連網，並建議準備你自己的聯絡信箱（Crossref 禮貌使用規範建議附上，讓他們能在你的程式出問題時聯絡你）。

## 檔案

| 檔案 | 用途 |
|---|---|
| `PDF取得SOP.md` | 七層取得順序，白話版 |
| `驗證四級與攔截規則.md` | 一致／衝突／待查／無法判定，以及撤稿、勘誤、補充資料怎麼處理 |
| `papers.csv` | 5 篇示範清單（書目來自 PubMed、授權來自 Europe PMC，查證 2026-11-25；只放書目，不放全文） |
| `check_doi.py` | 輸入 DOI 清單，查 Crossref 的題名、期刊、年份、更新紀錄，輸出對照表 |
| `tests/` | 用假資料測 `check_doi.py`，不連網 |

## 逐步 SOP

1. **（程式）先確認工具能跑。** 在哪裡做：開終端機（Windows 用 PowerShell，Mac 用「終端機」），進到 `2-extraction-pipeline/03_sources`。貼上：
   `python check_doi.py tests/fake_dois.csv --offline-json tests/fake_crossref.json --out check_result.csv`
   為什麼：用假資料離線跑，確認 Python 與程式沒問題。預期看到：`查了 6 筆：一致 1、待查 1、無法判定 1、衝突 3。結果：check_result.csv`。沒看到：確認路徑，Mac 把 `python` 改成 `python3`。
2. **（程式）跑單元測試。** 貼上：`python -m unittest discover -s tests`。預期：最後一行是 `OK`。
3. **（人★）補齊 `papers.csv`。** 在哪裡做：用 Excel 或文字編輯器開。DOI 與題名請到 PubMed 頁面複製，**不要請 LLM 憑記憶補**（LLM 會編出看起來合理的 DOI）。
4. **（程式）真實查詢。** 貼上（把信箱換成你自己的）：
   `python check_doi.py papers.csv --mailto 你的信箱 --out check_result.csv`
   為什麼：確認每個 DOI 查得到、題名年份對得上、沒有撤稿紀錄。預期：產出對照表；期刊用縮寫時會標「待查」，這是提醒你看一眼，不是錯。
5. **（人★）逐列看「衝突」與「待查」。** 衝突一律先停用，查清楚再說。
6. **（程式＋人★）依 `PDF取得SOP.md` 取得全文，依 `驗證四級與攔截規則.md` 驗證每個檔案。**

## 哪裡用 LLM、哪裡一定要人

- 這一階段**不需要 LLM**，也不應該讓 LLM 補 DOI 或判斷論文是否撤稿。
- 人★：補清單、看衝突與待查、機構訂閱與館際合作（只有人能做）。

## 限制

- Crossref 沒有更新紀錄，不等於論文沒被撤稿或更正；最終以出版社頁面與 PubMed 為準。
- `check_doi.py` 讀取的更新欄位（`updated-by`、`update-to`）依 Crossref 公開的資料格式撰寫；Crossref 若調整格式，請對照其官方說明（2026-11-25 已用真實回應核對過欄位名稱，未做長期驗證）。
- 書目一律從 PubMed 或 Crossref 複製，不要請 LLM 憑記憶補。
