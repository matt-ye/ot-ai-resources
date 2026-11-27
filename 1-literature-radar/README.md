# 文獻雷達：每月自動找新論文、去重、請 AI 先篩一輪、開成一張工作單

**一句話**：你寫好關鍵字，它每月自動去 Europe PMC（免費的醫學論文索引，收 PubMed、PMC 與預印本）找新論文，去掉重複的，請 AI 依你寫的判準先分成「保留」與「篩掉」，再把結果開成一張 GitHub Issue（工作單）給你讀；沒有 AI 金鑰也能跑，只是變成全部列出。

## 你需要先準備

| 項目 | 說明 |
|---|---|
| Python 3.9 以上 | 免費，到 python.org 下載安裝。Windows 安裝時請勾選「Add python.exe to PATH」。這個專案只用 Python 內建功能，不需要再裝任何套件 |
| 這個資料夾 | 整個 `1-literature-radar` 資料夾複製到自己電腦 |
| 終端機 | Windows 用 PowerShell；Mac 用「終端機」（Terminal）。終端機＝輸入文字指令的視窗 |
| GitHub 帳號（只有 B 段需要） | 免費 |
| AI 金鑰（選填） | 金鑰＝通行密碼，讓程式代你呼叫 AI 服務。支援 NVIDIA NIM、Groq、Cloudflare Workers AI 三家，擇一即可。這三家都提供免費額度，條件會變動，申請前請看官網說明。Cloudflare 的金鑰請只給 Workers AI 的權限 |

**金鑰等於密碼**：不要貼進聊天、不要寫進會上傳的檔案、不要傳給別人。

## 資料夾地圖

```
1-literature-radar/
  scripts/        主程式（literature_watch.py）、AI 篩選（llm_triage.py）、重試（http_retry.py）、金鑰檢查（check_keys.py）、表單轉主題（pico_topic.py；各框架規則在 topic_frameworks.py）
  config/         關鍵字設定檔；README.md 逐欄解釋怎麼寫
  advanced/       進階流程：AI 讀事實、程式對照帳本（失智症專用示範；一般人不用看）
  examples/       示範報告與離線測試用的假資料
  tests/          離線測試
  .github/workflows/literature-radar.yml    GitHub 自動執行的排程範本
  .github/workflows/check-keys.yml          金鑰檢查（只能手動執行）
  .github/workflows/radar-topic-*.yml       主題表單：試搜提案、核准後套用（見 C0）
  .github/ISSUE_TEMPLATE/radar-topic*.yml   六種問題框架的主題表單（見 C0）
  .env.example    金鑰欄位範本（只有變數名，沒有值）
```

## A 在自己電腦跑（不用金鑰）

目標：不註冊任何東西，先看到一份報告長什麼樣。

1. **打開終端機，進到專案資料夾。**
   - Windows：在檔案總管開啟 `1-literature-radar` 資料夾，點上方網址列、輸入 `powershell` 後按 Enter。
   - Mac：開啟「終端機」，輸入 `cd `（cd 後面有一個空格），把資料夾從 Finder 拖進視窗，按 Enter。
   - 預期：視窗的路徑列最後是 `1-literature-radar`。沒看到：重做一次。
2. **確認 Python 可用。** 貼上 `python --version`（Mac 若出現找不到，改用 `python3 --version`，之後所有 `python` 都換成 `python3`；Windows 若找不到，改用 `py --version`，之後也都換成 `py`）。
   - 預期：出現 `Python 3.9` 以上的版本號。
   - 沒看到：Python 沒裝好或沒進 PATH，重新安裝並勾選 Add to PATH，再開一個新的終端機視窗。
3. **跑離線測試**（確認程式本身沒壞，不連網）。貼上：
   `python -m unittest discover -s tests`
   - 預期：最後一行是 `OK`。
   - 沒看到：把整段輸出貼給 AI 請它看；通常是 Python 版本太舊。
4. **離線看一份報告**（用存好的假資料，不連網）。貼上：
   `python scripts/literature_watch.py --config config/literature-watch.ot.json --fixture examples/mock_epmc_response.json`
   - 預期：螢幕印出中文報告，有五個主題（第五個在假資料裡沒有論文，所以是空的）、最後一行「共 9 篇候選待讀」，並提到 1 篇重複紀錄被略過。
   - 沒看到：確認終端機位置在專案根目錄（有 `scripts` 資料夾的那一層）。
5. **真的去檢索一次**（會連網到 Europe PMC，不用金鑰）。貼上：
   `python scripts/literature_watch.py --config config/literature-watch.ot.json --seen-file seen.json --out report.md`
   - 為什麼加 `--seen-file seen.json`：這個檔案記住已經列過的論文，下次執行就不會重複。
   - 預期：資料夾裡多出 `report.md` 和 `seen.json`；用任何文字編輯器打開 `report.md`，開頭那句寫著「未使用 AI 篩選：所有候選都列出」。再跑一次同一行指令，會看到「沒有新的……都已經報告過」。
   - 沒看到：若報告出現「【無法檢查】」，是連網失敗，看 D 段。
6. **（選填）加上 AI 篩選。**
   1. 申請一組金鑰（在服務商網站上做，名稱見上表）。
   2. 把 `.env.example` 複製成 `.env`：Windows 貼 `copy .env.example .env`；Mac 貼 `cp .env.example .env`。
   3. 用文字編輯器打開 `.env`，在你申請的那一家後面填上金鑰（等號後面不要加空格或引號）。存檔請選純文字、UTF-8，檔名不要被加上 `.txt`。
   4. 貼上：`python scripts/literature_watch.py --config config/literature-watch.ot.json --triage --seen-file seen.json --out report.md`
      （如果上一步已經執行過、`seen.json` 記住了這些論文，想重看效果請先刪掉 `seen.json`。）
   - 預期：報告的 AI 那一行寫出實際回答的模型名稱，各主題下出現「AI 篩掉 N 篇」的收合區塊。
   - 沒看到：如果寫的是「沒有找到任何金鑰」，檢查 `.env` 是否在專案根目錄、金鑰是否貼對；如果是「所有模型都失敗」，看 D 段。
   - 隱私提醒：開啟 AI 篩選時，論文的標題與公開摘要會送到你選的 AI 服務。這個流程只適合公開文獻；不要拿來處理未發表或有保密要求的文字。

## B 放上 GitHub 每月自動跑

目標：你什麼都不用做，每月 1 號收到一張 Issue。

1. **建一個新 repo（GitHub 上的專案資料夾）。** 登入 GitHub → 右上角「+」→ New repository → 取名（例如 `my-literature-radar`）→ 選 Private（論文清單不想公開就選這個）→ 建立。
   - 為什麼不用 Fork（複製別人的 repo）：Fork 預設會關閉 Issues 和排程，容易卡住。
2. **上傳檔案。**
   > **上傳前先檢查**：資料夾裡如果有 `.env`（裡面是你的金鑰）、`seen.json`、`report.md`，**先移到別的地方再上傳**。網頁上傳不會自動略過它們。如果不小心把金鑰傳上去了，立刻到服務商網站撤銷那把金鑰，再建一把新的；只刪掉檔案沒有用，歷史紀錄裡還在。

   要讓 repo 的**最外層**直接有 `scripts/`、`config/`、`.github/` 這幾個資料夾，不是多包一層 `1-literature-radar/`。
   - 做法一：新 repo 頁面點「uploading an existing file」，把資料夾**裡面**的所有東西拖進去，按 Commit changes。
   - 注意：`.github` 是隱藏資料夾，Mac 在 Finder 按 Command+Shift+句點 才看得到，Windows 在檔案總管「檢視 → 顯示 → 隱藏的項目」打勾。若拖不進去，用做法二。
   - 做法二（`.github` 專用）：repo 頁面 Add file → Create new file，檔名欄輸入 `.github/workflows/literature-radar.yml`（打到斜線會自動變成資料夾），把本資料夾同名檔案的內容整份貼上，按 Commit changes。
   - 預期：repo 首頁看得到 `scripts`、`config`、`.github` 等資料夾。
   - 沒看到：點進 `.github/workflows/` 確認有 `literature-radar.yml`；沒有 workflow 檔就不會有任何自動執行。
3. **建立你要用的設定檔。** GitHub 自動執行時讀的是 `config/literature-watch.json`。Add file → Create new file，檔名欄輸入 `config/literature-watch.json`，把 `config/literature-watch.ot.json`（或你改好的檔案）的內容整份貼上，Commit。
4. **確認 Issues 有開。** repo 的 Settings → General → Features → 「Issues」要打勾。
5. **（選填）設定 AI 金鑰。** Settings → Secrets and variables → Actions → New repository secret。名稱要和 `.env.example` 一樣（步驟詳見根目錄 README「API 金鑰一律不上傳」；`NVIDIA_API_KEY`、`GROQ_API_KEY`，Cloudflare 兩個都要設：`CF_ACCOUNT_ID` 和 `CF_API_TOKEN`），值貼你的金鑰。
   - 不設也能跑，報告會寫「沒有找到任何金鑰」並全列。
   - 設好之後，先照 D0 手動跑一次「Check AI keys」，確認每一家都能用。
6. **手動跑第一次。** 點上方 Actions → 若看到「I understand my workflows, go ahead and enable them」就按下去 → 左邊點 Literature radar → 右邊 Run workflow → Run workflow。
   - 預期：約 1 到 3 分鐘後出現綠色打勾；Issues 分頁多一張「文獻雷達 2026-11：N 篇候選」，內容就是報告。
   - 沒看到：點進紅色打叉的那次執行，看哪一步失敗（見 D 段）。
7. **之後每月 1 號 06:00（世界標準時間，台灣 14:00）自動執行。** 要改頻率就改 workflow 檔裡 `cron:` 那一行，並把設定檔的 `days_window` 改成比間隔多約 15 天。
   - **排程不保證準時。** GitHub 官方說明排程可能延遲，負載高時（尤其整點）甚至會整次跳過；講者實測曾晚 5～6 小時，新建的 repo 也可能好幾個小時都還沒開始排。所以第一次一定要照第 6 步手動跑；當天沒看到新 Issue，就再手動跑一次。已經報過的論文不會再報（程式會讀舊 Issue 去重）；但每跑一次都會開一張新 Issue，多出來的「0 篇候選」那張直接關掉即可。
   - **公開 repo 60 天沒有活動，排程會被自動停用**（GitHub 官方規定；官方沒有定義什麼算「活動」，也沒寫私人 repo 是否適用）。停用後到 Actions → 左邊點 Literature radar → 按 **Enable workflow** 就能恢復；修改 `cron:` 那一行也會重新啟用。
   - 從別人的 repo **Fork** 過來的，排程預設是關的，要照上一點手動啟用。
   - 排程只在預設分支（通常是 `main`）上的 workflow 檔生效，時間一律是世界標準時間（UTC）。

## C 換成你的題目

**最簡單：填主題表單（不用碰 JSON）。** 見下方「C0」。想自己改設定檔，照 1～5 步。

### C0 用表單新增主題（GitHub 上）

**先選對表單**：不同的問題要用不同的框架描述；用錯框架，表單會逼你硬填不存在的欄位（例如盛行率題目沒有「介入」）。

| 你想追的問題 | 表單 | 放進檢索式（求找得全） | 只寫進判準（求篩得準） |
|---|---|---|---|
| 某介入、治療有沒有效 | 介入效果（PICO） | P 對象、I 介入 | C 對照、O 結果、研究設計 |
| 某狀況有多少人有（盛行率、發生率） | 盛行率／發生率（CoCoPop） | 病況、族群，加流行病學詞 | 情境（國家、場域、年代）、指標 |
| 某暴露或危險因子和結果有沒有關聯 | 暴露與風險（PEO／PECO） | P 族群、E 暴露（O 是明確疾病或事件時也放） | C 比較組、O 結果、研究設計 |
| 某檢測或篩檢工具準不準 | 診斷準確度（PIRD） | 指標檢測、目標診斷 | 參考檢測、族群；**不加研究設計濾鏡** |
| 評估工具的信度、效度、反應性 | 測量特性（COSMIN） | 構念、族群、工具類型、測量特性詞，**四項都放** | 要看的測量特性 |
| 當事人的經驗、感受、意義 | 經驗與感受（PICo） | 族群、關注的現象 | 情境、研究類型 |

為什麼這樣分：檢索式只放作者一定會寫在題名、摘要的元素，對照與結果通常不檢索（Cochrane Handbook 4.4.2）；診斷準確度研究不建議加研究設計濾鏡（Leeflang 2008）；測量特性回顧要四個要素都檢索（COSMIN，Prinsen 2018）；盛行率用 CoCoPop、經驗用 PICo、暴露用 PEO 出自 JBI 的回顧方法學（Munn 2018 整理成十型問題）。其他框架（範疇回顧的 PCC、預後的 PFO、服務與政策的 SPICE／ECLIPSE 等）之後再加。


1. **（人★）填表單。** repo 上方 Issues → New issue → 依上表選一張「雷達主題：…」表單。中文填即可，必填欄位有標記。
   - 只搜標題時把所有元素全部用 AND 連起來，幾乎會找不到東西，所以每張表單只把上表「放進檢索式」那幾項轉成檢索式，其餘寫進這個主題自己的 AI 判準。
   - 程式依表單的欄位判斷是哪一種框架（不看標題），留言會寫出這個框架哪些放進檢索式、哪些放進判準。
2. **（LLM＋程式）約 1～3 分鐘後出現一則留言。** 內容有：AI 寫的檢索式、判準、AI 對檢索式的說明、試搜篇數（最近 45 天、最近一年）與最新 5 篇題目，以及 AI 建議的 MeSH 詞是否真的存在（向 NCBI 查證，只給你參考同義詞，不放進檢索式）。
   - 檢索式只允許 `TITLE:`、`ABSTRACT:` 欄位，括號與引號要成對；不合格的不會被提出。
   - 最近一年 0 篇、或 45 天就超過 40 篇，留言會明白警告。Europe PMC 語法錯時不會報錯，只會回 0 篇，所以 0 篇一定要看。
   - 想修改：直接編輯這張 Issue 的內容，會重新產生一則留言。
3. **（人★）看過覺得可以，加上 `核准` 標籤。** 只有對 repo 有寫入權限的人能加標籤，所以這一步就是權限檢查。
4. **（程式）約 1 分鐘後再出現一則留言**：「已套用……按這裡建立 PR」。程式把主題寫進設定檔、推到新分支，**不直接改 main，也不自動合併**。
5. **（人★）點連結建立 PR，看差異，自動測試通過後合併。** 下個月的雷達就會用新主題。

注意：

- 只有 repo 擁有者、組織成員與協作者開的表單會觸發 AI。這是公開 repo，不讓陌生人用到你的金鑰；別人想用，Fork 到自己帳號、設自己的金鑰。
- 第一次使用前要有兩個標籤：`雷達主題提案` 與 `核准`（Issues → Labels → New label）。
- 範本資料夾裡的 `.github/ISSUE_TEMPLATE/radar-topic.yml` 與 `.github/workflows/radar-topic-*.yml`，要和 `literature-radar.yml` 一起複製到你 repo 的根目錄才會生效（B 段）。
- 程式在 `scripts/pico_topic.py`；本機也能用：`python scripts/pico_topic.py propose --body-file 表單.md --config config/literature-watch.json --out 留言.md`（表單格式照 `tests/test_pico_topic.py` 裡的 `FORM`）。

### 自己改設定檔

1. 複製 `config/literature-watch.template.json`，改名（例如 `my-topic.json`）。每個欄位的意思見 `config/README.md`。
2. 寫 `topics`：每個主題一個 `label`（顯示名稱）和一句 `query`（查詢句）。先到 europepmc.org 的搜尋框貼上查詢句，一個月新增幾篇到幾十篇是合理範圍。
3. 寫 `rubric`（保留與篩掉的判準）。寫法見 `config/README.md`。
4. 在自己電腦跑一次，指令中的 `--config` 換成你的檔名：
   `python scripts/literature_watch.py --config config/my-topic.json --triage --out report.md`
   - 預期：報告裡的主題名稱是你的；打開「AI 篩掉」區塊，抽查有沒有被誤殺的好論文，有的話把 rubric 放寬再跑。
5. 滿意後，把檔案內容貼到 GitHub 的 `config/literature-watch.json`（B 段第 3 步），按 Commit。下次執行就用新題目。

### 怎麼請 AI 幫你改設定檔

把下面整段貼給任何聊天式 AI（貼之前把方括號內的內容換成你的），並把 `config/literature-watch.template.json` 的內容一起貼上。

```
我要設定一個每月自動找新論文的工具。它用 Europe PMC 的查詢語法，設定檔是 JSON。
我的研究／教學主題是：[用一兩句話寫，例如「社區長者的跌倒預防」]
我想追蹤的子題（每個會變成一個主題）：[列 2 到 4 個]
我只想收的研究類型：[例如隨機對照試驗、系統性回顧；對象是誰；看哪些結果指標]
我不想收的：[例如研究計畫書、個案報告、與介入無關的]

請依下面貼上的範本，幫我寫出完整的 JSON：
1. topics：每個子題一個，id 用英文小寫加底線，label 用繁體中文，query 用 Europe PMC 語法。
   請用 TITLE:(...) 限定標題，同義詞用 OR，片語加雙引號，不同概念用 AND。
   JSON 裡的雙引號請寫成 \"。
2. rubric：用英文寫，先寫 KEEP 什麼，再寫 DROP 什麼，不用寫輸出格式。
3. 查詢句請不要用你不確定的語法；不確定的地方直接告訴我，我會到 europepmc.org 自己測。
4. 最後用白話列出每個查詢句「會找到什麼、可能漏掉什麼」。
```

AI 寫的查詢句一定要自己拿到 europepmc.org 測過，不要直接相信；AI 可能把語法寫錯，或寫出實際上找不到東西的詞。

## D 壞掉了怎麼看

先看報告本身：它會自己說哪裡出問題。再看下面對應的段落。要看詳細紀錄時：GitHub 的 Actions 頁 → 點最近一次執行 → 點紅色或有警告的那一步展開。

### D0 剛設好金鑰：每一家都能用嗎？
- **為什麼要另外檢查**：雷達依序試 NVIDIA NIM → Groq → Cloudflare，第一家成功就不往下試。所以備援的金鑰平常不會被呼叫到，貼錯了也看不出來，要等第一家出問題那天才發現。重跑雷達也測不到：已經報過的論文會被去重，沒有新論文就不會呼叫 AI。
- **GitHub 上**：Actions → 左邊點 **Check AI keys** → Run workflow。約 1 分鐘後點進這次執行，Summary 會有一張表：每一家寫「能用」（加上實際回答的模型）、「失敗」（加上錯誤類型）或「沒設定」。有設定的任何一家失敗，這次執行會是紅叉。
- **自己電腦上**：在 `1-literature-radar` 資料夾打開終端機，貼上 `python scripts/check_keys.py`（Mac 用 `python3`）。它讀 `.env` 裡的金鑰，結果直接印在畫面上。
- 送出的是一個虛構的論文題目，不含任何真實資料。金鑰與帳號 ID 不會出現在輸出裡；錯誤訊息裡若剛好含有，也會被遮成 `<CF_ACCOUNT_ID>` 這類名稱。
- 「失敗」怎麼辦：先看說明欄。寫「只設了一半」就補上缺的那一個（Cloudflare 兩個都要設）；寫 `HTTPError` 多半是金鑰貼錯或過期，重新貼一次；其他情況見 D1。

### D1 免費模型下架了（報告出現「所有模型都失敗」）
- **現象**：AI 那一行寫「【警告】已要求 AI 篩選，但所有模型都失敗」，報告仍然列出全部論文，只是沒有篩選。
- **為什麼會發生**：免費模型常常無預告下架或改名。這個程式不把模型型號寫死，每次先問服務商「你現在有哪些模型」再挑；挑不到可用的，才會失敗。
- **怎麼處理**（由簡到難）：
  1. 先重跑一次（可能只是暫時忙線，或超過免費額度的每分鐘上限）。
  2. 檢查金鑰是否過期、是否貼錯：照 D0 跑一次金鑰檢查。要重貼的話：GitHub 上 Settings → Secrets。
  3. 多設另一家的金鑰。三家會依序嘗試，多一家就多一條退路。
  4. 到服務商網站的模型清單，看有哪些文字模型可用，把名稱釘住：GitHub 的 Settings → Secrets and variables → Actions → Variables，新增 `GROQ_MODEL`（或 `NIM_MODEL`、`CF_AI_MODEL`），值填完整模型名稱。本機則寫在 `.env`。
  5. 更根本的修法：打開 `scripts/llm_triage.py`，找 `_PREFER`，在對應服務商那一行加上新模型名稱的片段；可請 AI 協助。
- **重要**：沒有 AI 時整個流程仍然可用，只是你要自己讀完全部候選。不必急著當天修好。

### D2 查詢全部失敗（報告出現「不完整」和「無法檢查」）
- **現象**：報告最上面有粗體的「【不完整】……個主題無法檢查」，各主題下寫「【無法檢查】」加原因。
- **原因怎麼讀**：
  - `HTTP 429`、`HTTP 503`、`HTTP 502`：Europe PMC 暫時太忙或限流。程式已自動重試三次，仍失敗，過幾個小時重跑即可。
  - `URLError`、`TimeoutError`、`ConnectionResetError`：網路問題。
  - `HTTP 400`：查詢句有語法錯誤（括號沒成對、引號沒成對）。把該主題的 `query` 貼到 europepmc.org 看有沒有錯誤訊息。
  - `JSONDecodeError`（`ValueError` 的一種）：Europe PMC 回的內容不是預期格式，通常是暫時性的。
- **一定要補跑**：搜尋範圍只比月報多約兩週，沒檢查到的論文如果超過這段重疊，下個月就掃不到了。報告會告訴你「下個月的搜尋範圍從哪一天開始」。補跑方法：GitHub 的 Actions → Literature radar → Run workflow；本機就再跑一次指令。

### D3 報告字句的意思
| 報告上的字句 | 意思 | 你要做什麼 |
|---|---|---|
| `N 篇新，保留 K 篇` | 這個主題有 N 篇沒看過的新論文；AI 保留 K 篇，其餘收合 | 讀保留的，抽查收合的 |
| `N 篇新`（沒有「保留」） | 沒開 AI 篩選，N 篇全部列出 | 全部讀 |
| `保留 0 篇` 加收合區 | 有新論文，但 AI 全判為不收 | 打開收合區確認沒有誤殺 |
| `沒有新的：最近 N 天有 M 篇，但都已經報告過……` | 查詢成功、也有論文，但這些在過去的報告或別的主題已經列過 | 不用做什麼 |
| `最近 N 天沒有符合的論文` | 查詢成功，真的沒有找到 | 若連續好幾個月都是這句，查詢句可能太窄，到 europepmc.org 測試 |
| `【無法檢查】原因` | 這個主題的查詢失敗，**不代表沒有新論文** | 看 D2 |
| `【上限】只掃描了最新 N 篇（共 M 篇）` | 這個主題命中數超過 `max_per_topic`，較舊的 M−N 篇**沒有**被看過 | 調高 `max_per_topic`，或把查詢句寫得更精確 |
| `未使用 AI 篩選：所有候選都列出` | 你沒有要求 AI 篩選 | 正常 |
| `沒有找到任何金鑰，所以全部列出、沒有篩選` | 要求了 AI 篩選，但沒設金鑰 | 設金鑰，或接受全列 |
| `AI 篩選：由 某某/模型名 判斷` | AI 真的判斷了，模型名是實際回答的那個 | 正常 |
| `所有模型都失敗` | 要求了 AI 但每一家都失敗，沒有任何篩選 | 看 D1 |
| `這次沒有新論文需要判斷` | 沒有新論文，AI 沒事做；不是壞掉 | 正常 |
| `沒有抓到任何論文可以判斷` | 所有查詢都失敗，AI 沒有東西可判 | 看 D2 |
| `略過：N 篇在更早的報告列過` | 去重生效 | 正常 |
| `略過：N 篇是重複紀錄` | 同一篇在 Europe PMC 出現兩筆，或同時符合多個主題 | 正常 |
| `讀不到舊的 Issue` | 去重所需的舊紀錄讀不到，這個月可能出現上個月已看過的論文 | 檢查 workflow 是否有 `issues: write` 權限、標籤是否仍叫 `literature-radar` |
| `設定檔沒有 rubric` | 開了 AI 篩選但沒寫判準，只篩掉明顯離題的 | 補寫 rubric |

### D4 其他常見狀況
- **沒有出現 Issue**：到 Actions 看那次執行。常見原因：repo 的 Issues 沒打開（B 段第 4 步）；排程被停用（B 段第 7 步）；workflow 檔不在 `.github/workflows/`。
- **Issue 建立失敗，訊息提到內容太長**：GitHub 單張 Issue 約 6 萬字元上限。調低 `max_per_topic` 再跑。
- **設定檔錯誤**：程式會用中文指出哪裡錯，最常見是少逗號、最後一項後面多了逗號、查詢句裡的雙引號沒有寫成 `\"`。可把整個檔案貼到任何 JSON 檢查網站，或請 AI 幫忙找。
- **本機報告出現亂碼**：用支援 UTF-8 的編輯器開（VS Code、記事本新版）；用 `--out report.md` 寫成檔案比直接印在螢幕上穩。

## 哪裡用 LLM、哪裡一定要人看（human in the loop）

- **用 LLM 的地方只有一個**：`--triage` 的保留／篩掉，依你寫的 `rubric` 判斷標題與摘要。檢索、去重、組報告都是普通程式。
- **一定要人看**：
  1. 保留的論文，打開原文確認。AI 看的只是標題與摘要，會誤判。
  2. 「AI 篩掉」收合區，每個月至少抽查幾篇。被篩掉的論文不會再出現。
  3. 查詢句與 rubric 要由你定稿，並在新題目上線前親自試跑。
- AI 的判斷不是證據；報告上的理由只是模型的一句簡述。

## 限制

- 只查 Europe PMC，沒有收錄的期刊或資料庫查不到；也不下載全文，不處理付費牆。
- 查詢只比對標題（`TITLE:`）時，標題沒寫關鍵字的論文會漏掉；這是用漏掉換低雜訊的取捨。
- 免費 AI 的額度、速度和模型都可能變動；沒有保證某家某月一定能用。
- AI 會判錯，準不準取決於 rubric 寫得多具體。
- 這個工具找的是「新發表的論文候選」，不能取代系統性文獻搜尋。
- 進階流程見 `advanced/README.md`，裡面的圖層是失智症專用示範。

## 授權

程式 MIT（見 `LICENSE`）、文件 CC BY-NC 4.0。
