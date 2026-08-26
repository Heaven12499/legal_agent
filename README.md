# 智能合同审查 RAG Agent

面向求职面试的法律 RAG 项目，以**合同审查**为核心。检索核心全手写（不用 LangChain），agent 循环手写（不用 LangGraph），语料全部来自官方原文，回答引用不编造。

语料 = **8 部法律原文条文 1023 条**（5 部劳动/社保法 395 + 民法典合同编 526 + 合同编通则解释 69 + 买卖合同解释 33），不含任何虚构内容。

```
"上传《房屋租赁合同》→ 请审查这份合同"
   └─ agent 循环（手写 while + function calling）
        ├─ 识别风险条款：押金一律不退 / 甲方单方免责 / 违约金过高
        ├─ retrieve("格式条款 免除责任 无效")    → 民法典497条
        ├─ retrieve("免责条款 故意 重大过失")    → 民法典506条
        ├─ retrieve("违约金 过分高于损失 调整")  → 民法典585条 + 通则解释65条
        └─ 答案：逐条风险报告，每条引真实法条
           └─ M6 引用校验：所有引用逐条核对语料存在（反幻觉）
```

## 目录结构

```
corpus/                 # 语料 + 派生索引（全部官方原文）
  *.txt                 # 8 部法律清洗后原文（劳动/社保 5 部 + 合同编 + 2 司法解释）
  chunks.json           # 切分产物（1023 chunk，gitignored，可重建）
  chunks.faiss          # 向量索引（gitignored，可重建）
core/                   # 检索与引用核心（全手写）
  chunking.py           # 一条法条 = 一个 chunk
  embeddings.py         # bge-small-zh-v1.5 本地向量化（零网络依赖）
  retriever.py          # FAISS 向量检索（IndexFlatIP）
  bm25.py               # BM25 词法检索（jieba 分词）
  hybrid.py             # 双路 RRF 融合
  citations.py          # M6 引用校验：抽「《法》第X条」核对语料，反幻觉
  fileparse.py          # 合同上传解析（.docx/.pdf/.txt → 纯文本）
  docx_export.py        # M8 修订版合同导出 .docx（python-docx）
agent/                  # 手写 agent 循环（LLM = DeepSeek）
  llm.py                # OpenAI 兼容客户端单例 + .env 加载
  tools.py              # retrieve 工具 schema + 执行器
  prompts.py            # system prompt：合同类型分流 / 审查流程 / 引用纪律
  loop.py               # ~40 行 while 循环
  revise.py             # M8 修订 agent：只改风险条款 + 修改清单（依据经 M6 校验）
  session.py            # 会话存储：SQLite 持久化（标准库 sqlite3）
sample_contracts/       # M7 评测埋点合同（4 份，含金标风险点）
scripts/
  verify_retrieval.py   # 检索验收（11/11 命中）
  verify_citations.py   # M6 引用校验验收（8/8 通过）
  eval_review.py        # M7 评测：确定性引用召回率
  verify_revise.py      # M8 修订守卫：修订不编造条号（0 未核实）
main.py                 # FastAPI 纯 API 后端（/api/* + CORS；演示模式托管前端 dist）
cli.py                  # CLI 入口，与 web 共用 agent.loop.run
frontend/               # Vue 3 + Vite 前端（前后端分离）
  src/components/       # Sidebar / MessageBubble / TraceDetails / Welcome / ConfirmDialog
data/                   # SQLite 会话库 sessions.db（gitignored）
```

## 快速开始

```bash
pip install -r requirements.txt            # 清华镜像
python scripts/download_model.py           # 拉 bge 模型到 models/
python -m core.chunking                    # 生成 chunks.json（语料已入库可跳过）
python scripts/verify_retrieval.py         # 检索验收：11/11
python scripts/verify_citations.py         # 引用校验验收：8/8
python -X utf8 scripts/verify_revise.py    # M8 修订守卫：修订不编造条号

# 复制 .env.example 为 .env，填入 DEEPSEEK_API_KEY
python cli.py "试用期一般多久"             # agent 端到端（CLI）

# ---- Web（前后端分离）----
cd frontend && npm install && npm run dev   # 前端 5173，/api 代理到 8000
python main.py                              # 后端 API 在 127.0.0.1:8000
# 演示（单进程）：cd frontend && npm run build && python main.py → 开 http://127.0.0.1:8000

# ---- M7 评测（每份合同真实调 DeepSeek；--runs 调重复次数）----
python -X utf8 scripts/eval_review.py       # 期望：risk_recall ≈ 90%
```

## 设计决策

### 检索：为什么向量 + BM25 双路，为什么 RRF 融合

两路互补的动机：
- **向量（bge-small-zh）**：语义联想，"换说法"也能懂；但短口语查询时分数挤在一起、噪声混入。
- **BM25（jieba 分词）**：词面精确匹配，"仲裁时效/经济补偿"一字不差就能命中；但不懂同义改写。

两路各取所长：BM25 漏掉的说法向量能兜住，向量模糊的地方 BM25 的精确术语能兜住。

**RRF（Reciprocal Rank Fusion）而不是分数加权求和**，因为两路分数量纲不同不可比——向量是余弦相似度（0~1），BM25 是无界原始分。直接加权要么偏心某一路，要么得先给两边做归一化（凭空引入超参数）。RRF 只依赖排名不依赖分数：

```
fusion_score(i) = Σ_source 1 / (rrf_k + rank(source, i))
```

一个 chunk 在任一单路排得靠前，融合分就高。典型 `rrf_k = 60`（论文常用值）。

### 为什么 BM25 要用 jieba 分词

BM25 是词级别的。中文不分词，"经济补偿"就散成"经""济""补""偿"，既匹配不上"补偿"，也会被不相干单字带偏。jieba 切成词后，查询和条文在"词"上对齐。

### 为什么 agent 循环手写（不用 LangGraph）

参考项目用 LangGraph 把「LLM 调用 → 工具执行 → 回填 → 再调用」封装成图/状态机；这里就是一个 ~40 行 while 循环（`agent/loop.py`），每一步显式、可打断、可打印 trace。三个理由：

1. **透明**：循环里每轮调了什么工具、传了什么 query、返回了什么，trace 全记录，能直接展示「违约金太高 → 违约金 过分高于损失 调整」这个改写怎么在循环里发生的。
2. **可控**：`max_rounds` 硬上限防止 LLM 无限检索；工具执行失败也能把错误喂回 LLM。
3. **零依赖**：只靠 openai SDK 的 chat.completions，没有隐藏的状态管理。

### 为什么查询改写不设单独模块

常见 RAG 把"query rewrite"做成一个独立模块（prompt 改写后再检索一次）。这里改写不是单独步骤，而是 agent 循环里**以检索结果为条件**的自然过程：检索一次落空/不充分 → LLM 自己决定换法律术语再检。因为"要不要改写、改写成什么样"取决于前一次检索的结果，静态改写模块做不到这个动态性。

### 为什么检索核心不用 LangChain

M1~M2 的向量化、FAISS、BM25、RRF 全是标准库 + 原生库手写，零 LangChain。理由：检索管线就 1000 余条语料的规模，手写更可控、可解释、可复现；面试也能讲清楚每一步在干什么。

### Web 架构：前后端分离 + SQLite 持久化 + 不做登录

三个决策都围绕同一句话——**这是技术 demo，把复杂留给核心问题**（检索 + agent）：

- **前后端分离（Vue 3 + Vite）**：后端 FastAPI 只出 JSON（`/api/*` + CORS），前端独立 Vite 工程。
  开发时前端 5173 经 Vite proxy 把 `/api` 代理到 8000（免 CORS）；演示时 `npm run build` 出
  `frontend/dist/`，后端检测到该目录存在即静态托管（SPA），单进程一条命令跑起来。前端刻意不引
  marked.js 等 markdown 库，`markdown.js` 手写 ~40 行（先 escapeHtml 防 XSS 再逐行渲染）。
- **SQLite 持久化会话（标准库 `sqlite3`）**：会话不再存内存 dict（重启即空），落盘
  `data/sessions.db`，历史会话侧栏重启不丢。刻意用标准库而非 ORM/第三方——零依赖，且每个 SQL
  都讲得清楚。公开接口不变（`get_history/append/clear/list_sessions`），agent 核心零改动。
- **不做登录**：单用户 demo 里，登录的权限隔离 / 用户管理价值体现不出来，只会让演示多一步。
  安全叙事交给前端 `escapeHtml` 防 XSS、API key 只存 `.env`（gitignored）、以及环境变量优先级
  bug 的修复（`.env` 用直接覆盖而非 `setdefault`，否则 shell 预置的 key 会盖掉项目配置）。

### 为什么 DeepSeek 而不是 Claude

agent 的 LLM 用 DeepSeek（OpenAI 兼容接口 `api.deepseek.com`，模型 `deepseek-chat`），支持 function calling。走 OpenAI 兼容协议所以用 openai SDK；base_url/key/model 全 env 可配，换网关换模型只改 `.env` 不动代码。

### M6：引用校验（反幻觉）

agent 答案里每处「《法律名》第X条」都会被 `core/citations.py` 抽出来，逐条核对是否真实存在于语料（按规范法名 + 序数，兼容中文/阿拉伯条号、法名别名归一）。核对不过就喂一次纠错指令让 LLM 改用检索到的真实条文，最后给答案追加 ✅/⚠️ 校验脚注。**绝不静默通过编造引用**——这是「绝不虚构」红线在 agent 层面的落地，也是面试能讲"反幻觉"的点。

### M7：确定性引用召回率评测

`scripts/eval_review.py` 用 4 份埋点合同（`sample_contracts/`）测合同审查：每份跑完整 agent，抽引用与金标法条比对。指标全确定性（复用 citations，无裁判 LLM，可复现）：

- **risk_recall**：随机单次运行里，风险点被引到金标法条的比例（主指标）
- **article_recall**：金标法条被引到过的比例
- **article_precision**：引用里属于金标的比例

当前基线（每份 × 3 次聚合）：**risk_recall 90% · article_recall 94%**。LLM 采样有随机性，单次偶发"检索后没给引用"的空答案，故每份跑多轮聚合取均值；金标法条在启动时逐一核验必须真实存在于语料，否则拒绝运行。

### M8：修订版合同导出（Word）

审查完还能产出**修订版合同**：`agent/revise.py` 把原合同 + M5 审查报告喂给 LLM，**只改写已识别且可给真实法条依据的风险条款，其余一字不改**，输出「修订版全文 + 修改说明表（原条款/修订后/依据）」。每条依据复用 M6 校验，核不到就如实标注 ⚠️（不静默放行编造）。前端审查气泡上有「导出修订版 Word」按钮，后端 `POST /api/chat/sessions/{sid}/revise-docx` 用 python-docx 生成 .docx 下载。

`scripts/verify_revise.py` 是修订管线的「绝不编造」守卫：对 4 份埋点合同跑修订，断言修改清单里 0 条依据未核实（`--runs` 聚合消除 LLM 随机性，默认 2 次，PASS）。

## 三条红线（防翻车）

1. **法条/案例必须官方真实**：语料只来自官方原文（人大网/最高法/人社部），评测金标法条必须能在语料中核验到，虚构判例或条号是面试死穴。埋点合同是**输入样本**，可自由编写埋风险，但不触碰法条真实性。
2. **key 只放 `.env`**：真实 `DEEPSEEK_API_KEY` 只写 `.env`（gitignored）；`.env.example` 是模板，只留占位符（它会被提交，泄 key 是安全事故）。
3. **改语料必须重建索引**：chunks.json 变了就删 `corpus/chunks.faiss` 再跑验收——向量下标与 chunks 列表下标一一对应（下标即主键），直接 load 旧索引会对不齐、静默出错。顺序：`python -m core.chunking` → `rm corpus/chunks.faiss` → `python scripts/verify_retrieval.py`。

## 里程碑

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M1 | 语料切分 / 向量化 / FAISS 检索 | ✅ |
| M2 | BM25 词法检索 + RRF 混合检索 | ✅ |
| M3 | 手写 agent 循环 + 查询改写（DeepSeek） | ✅ |
| M4 | Web + 多轮记忆 + 前后端分离（Vue 3 + Vite）+ SQLite 持久化 | ✅ |
| M5 | 合同审查 + 合同上传（前端）+ 按合同类型分流检索 | ✅ |
| M6 | 引用校验（反幻觉）+ 消息操作（复制/修改/重新生成）+ 合同纳入会话历史 | ✅ |
| M7 | 评测：确定性引用召回率（4 份埋点合同，risk_recall 90%） | ✅ |
| M8 | 修订版合同导出（Word）+ 修订守卫（不编造条号） | ✅ |
