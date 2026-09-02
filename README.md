# 面向合同初审的可追溯法律检索 RAG 系统

产品演示名称：**合同审查助手**

面向合同法务初审场景：上传合同或直接提问，系统定位待核查条款，通过混合检索找到相关法律原文，并输出带证据引用的风险说明。项目聚焦 RAG 的检索质量、证据可追溯性与可复现评测，不直接生成、替换或签署合同。

合同初审的实际难点不是“能否生成一段回答”，而是能否把合同中的具体条款稳定地映射到可核验的法律依据。为此，系统使用查询改写、向量 + BM25 混合检索、相邻法条扩展和引用校验，解决术语表达差异、关联法条遗漏与法条引用不可追溯的问题。

> **核心链路**：合同条款 → Query Rewrite → Hybrid Retrieval（Vector + BM25 + RRF）→ Evidence Whitelist → Citation Verification → Limited Reflection → Offline Eval
>
> **当前基线**：8 份埋点合同｜27 个风险点｜19 条独立金标法条｜风险点召回率 **80%**｜法条召回率 **98%**｜引用校验确定性用例 **8 / 8** 通过。完整口径见[评测结果](#3-评测结果)。

---



## 1. 功能特性

- **合同条款核查**：从合同中定位违约金、格式条款、竞业限制等待核查条款，逐项检索并展示相关法条原文。
- **法律问答**：针对劳动、合同、买卖等法律问题提问，基于检索到的官方法条回答。
- **证据白名单 + 引用校验**：首轮强制检索，最终答案中的每处「《法律名》第X条」不仅核对是否存在于语料，还必须来自本轮 retrieve / lookup_article 的证据集合；未通过时触发有限纠错，仍无法核实则明确标记，不静默放行。校验同时兼容「民法典585条」等紧凑写法，并对条号真实但复述内容可能偏离原文的情况给出人工核对提示。
- **可复现回归评测**：以带金标法条的埋点合同测引用召回率；金标校验、引用抽取和指标计算均为确定性，端到端结果通过多轮运行汇总，降低 LLM 采样波动的影响。
- **多轮对话 + 会话持久化**：前端可复制 / 修改 / 重新生成消息，SQLite 落盘会话历史，重启不丢。
- **多用户登录与会话隔离**：用户名+密码（argon2 哈希）+ JWT 登录；会话按用户隔离互不可见，跨用户读不到、改不到、删不到他人合同。开放注册 + 初始用户，历史匿名会话启动时自动迁移到初始用户名下。

---

## 2. 产品边界与解决范围

系统解决的是法务初审中的“从合同条款快速定位到可信法律依据”，而非自动决策或代替法务。处理链路如下：

```text
在线审查：合同条款 / 法律问题 → Query Rewrite → Hybrid Retrieval → Evidence Whitelist → Citation Verification → Limited Reflection → 人工参考结论
离线验证：埋点合同 + 金标法条 → Eval（检索、引用与纠错指标）
```

输出用于辅助人工判断：

- 提供相关法律依据、风险解释和供人工参考的处理建议；
- 不把模型生成内容直接写回原合同；
- 不自动作出合同有效性、胜诉概率或最终谈判条件等专业结论；
- 检索不到直接依据时明确说明，不用模型常识补造法条。

因此项目的工程重点是单智能体的查询改写、工具调用、混合检索、引用核验和离线评测，而不是工作流拆分或自动合同生成。

---

## 3. 评测结果

评测集由 8 份埋点合同组成，覆盖采购、租赁、技术服务、劳动、软件许可、借款、装修施工和劳务派遣合同，共 27 个风险点、19 条独立金标法条。金标法条会在评测启动时先与本地语料逐条核对，缺失即拒绝运行。

### 主链路评测

下表为当前 8 份合同的完整基线。每份合同重复运行 3 次：`risk_recall` 按各风险点在 3 次运行中的命中率计算，`article_recall` 与 `article_precision` 按 3 次运行的引用并集计算。

| 指标 | 含义 | 当前基线（8 份合同，`--runs 3`，2026-09） |
|---|---|---:|
| risk_recall | 每个金标风险点至少命中一条对应法条的平均比例 | 80% |
| article_recall | 金标法条被输出引用覆盖的比例 | 98% |
| article_precision | 输出引用中属于金标法条的比例 | 42% |
| 引用校验用例 | 法条存在性、旧法名、张冠李戴、重复引用等确定性用例 | 8 / 8 通过 |

> **口径提示：80% 与 94% 为不同统计口径，不进行前后效果比较。** 主链路 `risk_recall` 统计各风险点在 3 次运行中的平均命中率；反思专项的 `risk_recall` 统计 3 次运行引用并集的覆盖情况。
>
> **如何解读 `article_precision 42%`：非金标引用不等于错误引用。** 相邻法条扩展和补充性法律依据同样会被记为非金标引用，因此该指标用于监控“额外引用倾向”，不代表引用真实性、法律回答准确率或生产环境表现。

该评测用于回归验收和工程链路验证，不代表生产环境的法律意见准确率或泛化能力。

### 引用纠错专项评测

反思专项复用同一批 8 份合同，从 `run()` 的 `reflection_stats` 统计触发、修复和残留问题。当前基线（`--runs 3`）为：**反思触发率 17% · invalid 修复率 50% · 反思后 invalid 均值 0.08 · risk_recall 94%**。

反思只由不存在或张冠李戴的 invalid 引用触发；suspect（条号真实但复述可能偏离原文）残留均值约 6，主要受句尾引用忠实度窗口限制，系统仅标注并提示人工核对。

---

## 4. 效果演示

### 审查结果示例

![房屋租赁合同风险审查报告](docs/screenshots/img.png)

示例中，系统基于本轮检索到的《民法典》第五百八十五条和合同编通则解释第六十五条，识别每日 1% 违约金的风险，并给出可核验的处理建议。

### 核心检索链路（示意）

```
"上传《房屋租赁合同》→ 请核查合同中的风险条款"
   └─ 单智能体 RAG 循环（while + function calling）
        ├─ 识别风险条款：押金不退 / 甲方免责 / 违约金过高 / 单方解除权 / 管辖约定
        ├─ retrieve("格式条款 免除责任 无效")    → 民法典497条
        ├─ retrieve("免责条款 人身损害 无效")    → 民法典506条（配套 712 条维修义务）
        ├─ retrieve("违约金 过分高于损失 调整")  → 民法典585条 + 通则解释65条
        └─ 答案：逐条风险报告（6 个风险点），每条引真实法条
           └─ 引用校验：6 处条号全部核实存在，3 处复述偏离原文提示人工核对
```

---

## 5. 快速开始

### 环境要求

- Docker Desktop（Windows / macOS）或 Docker Engine + Compose Plugin（Linux）
- DeepSeek API Key（填入 `.env`）

### Docker 启动（推荐）

```powershell
# 复制环境变量模板，并填写 DEEPSEEK_API_KEY、INIT_PASSWORD、JWT_SECRET
Copy-Item .env.example .env

# 首次构建并启动；首次运行会下载约 95 MB 的向量模型、生成索引
docker compose up --build
```

打开 http://127.0.0.1:8000 。会话数据与模型分别保存在 Docker volume 中，停止或重建容器不会丢失；停止服务使用 `docker compose down`。

常用命令：

```powershell
docker compose up -d             # 后台启动
docker compose logs -f app       # 查看首次模型下载 / 索引构建进度
docker compose down              # 停止并移除容器（保留数据和模型 volume）
docker compose down -v           # 连同会话数据和模型一并删除
```

### 本地开发（可选）

如需运行前端热更新或调试 Python，可使用本地 Python 3.12、Node.js 18+ 和 Conda：

```powershell
conda create --prefix .\.venv python=3.12 pip -y
conda activate .\.venv

# 安装依赖（二选一）
python -m pip install -r requirements.txt
# 国内网络较慢时改用：
# python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

确认当前解释器后再准备模型与索引：

```bash
python --version                            # 应为 Python 3.12.x
python -m backend.scripts.download_model   # 拉 bge 模型到 models/
python -m backend.app.rag.chunking         # 生成 chunks.json（语料已入库可跳过）

# 复制 .env.example 为 .env，填入 DEEPSEEK_API_KEY
python -m backend.app.cli "试用期一般多久" # agent 端到端（CLI）

# ---- Web（前后端分离）----
cd frontend
npm install && npm run dev                  # 前端 5173，/api 代理到 8000
# 另开终端并回到项目根目录：
python -m backend.app.api                   # 后端 API 在 127.0.0.1:8000

# 演示（单进程）：
cd frontend && npm run build
cd .. && python -m backend.app.api          # → 开 http://127.0.0.1:8000

# 首次启动会自动建初始用户（INIT_USERNAME/INIT_PASSWORD，未设则生成随机密码并打印），
# 并把历史未归属会话迁移到其名下；也可直接在前端注册新账号。
```

---

## 6. 架构 / 设计

### 核心链路（优先阅读）

```text
合同条款
  → Query Rewrite
  → Hybrid Retrieval（Vector + BM25 + RRF）
  → 相邻法条扩展
  → Evidence Whitelist
  → Citation Verification
  → Limited Reflection（仅 invalid 引用）
  → 带证据的人工参考结论

离线：埋点合同 + 金标法条 → Eval
```

### Hybrid Retrieval：向量 + BM25 双路，RRF 融合

- **向量（bge-small-zh）**：语义联想，"换说法"也懂；短口语查询时噪声混入。
- **BM25（jieba 分词）**：词面精确匹配，"仲裁时效/经济补偿"一字不差；不懂同义改写。

RRF 只依赖排名不依赖分数（两路分数量纲不同不可比），一个 chunk 在任一单路排靠前融合分就高：

```
fusion_score(i) = Σ_source 1 / (rrf_k + rank(source, i))   # 典型 rrf_k = 60
```

**两条可选增强**（都不改动默认行为）：
- **相邻法条上下文扩展**（默认开启）：命中一条后把同法相邻条（序数 ±1）也拼进给 LLM 的上下文——法律条文高度关联（如 585 违约金常要和 584/586 配套引用），单条 chunk 里 LLM 看不到邻居。主命中 labels/trace 不受影响。
- **reranker 精排**（P1，默认关闭）：设置 `RERANK=1` 且安装 `BAAI/bge-reranker-base` 后，对 RRF 融合的 top-20 用 bge-reranker 打分取 top-5；模型不可用则静默回退 RRF。

### Query Rewrite 与工具调用

一个 while 循环（`backend/app/agent/loop.py`），由同一 Agent 根据当前证据决定继续检索、精确查条文或生成回答。每一步显式、可打断、可打印 trace：
**透明**（trace 记录每轮工具调用与查询改写过程）、**可控**（`max_rounds` 硬上限防无限检索）。

### Evidence Whitelist、Citation Verification 与 Limited Reflection

答案生成后先由 `verify_citations` 校验：最终引用既要真实存在于本地语料，也必须来自本轮 `retrieve` / `lookup_article` 的证据集合。仅当存在「条号不存在 / 张冠李戴」(invalid)
时才带反馈让 agent 按 JSON 重写，再校验，至多 `REFLECT_MAX_ROUNDS` 轮（`response_format=json_object`
强约束，解析 `fixed_answer`）。刻意**不为 suspect（条号真但复述偏离）触发反思**——真实运行 agent
已很少编造，suspect 又多源于 `check_faithfulness` 对结构化答案（表格/列表）的误报，为它调 LLM 重写
性价比低；这类只由 `annotate` 如实标注 ⚠️，不静默通过、也不烧 token。反思轮次记入 trace，
修复率由 `eval_reflection.py` 量化。

### 工程化补充

以下能力服务于可用性、可维护性和安全性，不改变上述核心 RAG 链路。

- **长会话上下文管理**（`backend/app/agent/context.py`）：多轮 history 超上限时，把最旧轮次压成一条
  「对话摘要」（`MAX_HISTORY_MESSAGES`/`KEEP_RECENT_MESSAGES` env 可调），再接最近若干轮；
  待审查合同走独立注入，永不被裁剪。短会话零影响。
- **工具注册表 + 结构化输出**（`backend/app/agent/tools.py`）：工具做成 `TOOL_SCHEMAS`/`TOOL_EXECUTORS`
  注册表，新增工具零改动 loop。第二个工具 `lookup_article` 按「法律名+条号」从语料精确查一条
  法条原文（数据真实不虚构），供反思阶段复核可疑引用，与 `check_faithfulness` 形成闭环。


#### Web 架构：前后端分离 + SQLite 持久化

- 后端 FastAPI 只出 JSON（`/api/*` + CORS），前端独立 Vite 工程。开发时 Vite proxy 免 CORS；演示时托管 `frontend/dist/` 单进程运行。markdown 渲染先 escapeHtml 防 XSS 再逐行渲染。
- SQLite 落盘会话（标准库 `sqlite3`），历史侧栏重启不丢；公开接口不变，agent 核心零改动。
- 安全：前端 `escapeHtml` 防 XSS，API key 只存 `.env`（gitignored），且 `.env` 直接覆盖而非 `setdefault`，避免 shell 环境变量污染配置。



## 7. 语料范围与已知限制

### 语料范围

当前语料包含 8 部公开法律与司法解释，按“一个法条一个 chunk”切分，共 1023 个条文块：

- 《民法典》合同编；
- 《最高人民法院关于适用〈中华人民共和国民法典〉合同编通则若干问题的解释》；
- 《最高人民法院关于审理买卖合同纠纷案件适用法律问题的解释》；
- 《劳动法》《劳动合同法》《劳动合同法实施条例》；
- 《社会保险法》《劳动争议调解仲裁法》。

文本来源记录在各语料文件开头，主要来自国家法律法规数据库与中国人大网等公开官方渠道。语料文件和构建产物均保存在 `corpus/`，可通过 `python -m backend.app.rag.chunking` 重建索引。

### 已知限制

- 当前不含案例库、地方性法规、部门规章及跨法域材料；
- 法律更新需要人工更新语料并重建索引，不具备自动追踪最新修法的能力；
- 输出是检索辅助结论，复杂事实认定、争议策略和最终法律意见仍应由专业人员判断。

---

## 8. 目录结构

```
frontend/               # Vue 3 + Vite 前端
backend/                 # Python 后端
  app/
    api.py               # FastAPI API + 演示模式 SPA 托管
    cli.py               # CLI 入口，与 Web 共用 backend.app.agent.loop.run
    agent/               # Query Rewrite、工具调用、LLM 循环与 Reflection
    rag/                 # 检索、切分、向量化、RRF 与引用校验
    infra/               # 鉴权与 SQLite 会话存储
    services/            # 合同文件解析与 .docx 导出
  scripts/               # 数据准备、验收与离线评测（见第 10 节）
corpus/                 # 语料 + 派生索引（8 部官方原文，1023 条）
sample_contracts/       # 评测埋点合同（8 份、27 个风险点、19 条独立金标法条）
data/                   # SQLite 会话库 sessions.db（gitignored）
```

---

## 9. 技术栈 / 依赖

| 层       | 技术                                         |
|----------|----------------------------------------------|
| 检索     | FAISS · BM25 + jieba · RRF                   |
| 向量模型 | bge-small-zh-v1.5（本地，零网络依赖）        |
| 编排     | 单智能体 while 循环 + OpenAI function calling |
| LLM      | DeepSeek API                                 |
| 后端     | FastAPI + Uvicorn + SQLite（标准库 sqlite3） |
| 前端     | Vue 3 + Vite                                 |

---

## 10. 测试 / 验收

```bash
python -m backend.scripts.verify_retrieval          # 检索验收：13 个固定金标查询命中
python -m backend.scripts.verify_citations          # 引用 + 本轮证据白名单验收
python -m backend.scripts.verify_session_contract   # 普通追问保留合同、显式移除才清空
python -X utf8 -m backend.scripts.eval_review --dry # 只校验金标与测试集，不调用 LLM
python -X utf8 -m backend.scripts.eval_review       # 评测：确定性引用召回率（--runs 调重复次数）
python -X utf8 -m backend.scripts.eval_reflection   # 评测：引用反思触发、修复与残留情况
```

前三项为确定性验收；两项 `eval_*` 评测调用 LLM，默认每份合同重复运行 3 次，并在启动时校验全部金标法条。评测集、指标口径和当前基线统一见第 3 节。
