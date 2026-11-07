# 大外校园智能问答助手（RAG）

给校内制度、通知、新闻套一层"能问答"的界面：**FastAPI + Chroma + DeepSeek + 原生前端**。
支持流式回答、引用可追溯、深色模式、登录页，以及**只更新变动文件的增量索引**。

当前知识库：**64 篇文档 / 258 个片段**，全部抓自学校官网（2026-11-08）。

---

## 一、30 秒跑起来

```bash
cd ~/Desktop/个人项目测试/DUFL-QA
bash start.sh          # 首次会自动建 .venv、装依赖、生成 .env
```

浏览器打开 <http://127.0.0.1:8000>，点「以游客身份进入」即可提问。
要用真模型回答，在 `.env` 里填 `DEEPSEEK_API_KEY`（或用 `python scripts/set_key.py` 从剪贴板写入）。

**在 VS Code 里**：打开文件夹 → 按 `F5` 选「启动服务（带热重载）」，等价于上面的命令。

---

## 二、目录结构

```
DUFL-QA/
├── app/                        后端（约 900 行，一个文件一件事）
│   ├── config.py               所有可调参数，全部来自 .env
│   ├── main.py                 路由：/ 页面、/api/chat(SSE)、/api/health、/api/rebuild
│   ├── store.py                核心：解析 → 切分 → 建索引 → 混合检索 → 增量更新
│   ├── prompt.py               系统提示词、引用格式、无命中话术
│   └── llm.py                  DeepSeek 客户端（OpenAI 兼容，流式）
├── data/                       知识库原文，按栏目分目录
│   ├── 01-学校概况/            5 篇
│   ├── 02-院系专业/            3 篇
│   ├── 03-教务与选课/         12 篇
│   ├── 04-学籍与转专业/        3 篇
│   ├── 05-考试与成绩/          2 篇
│   ├── 06-实践与竞赛/          3 篇
│   ├── 07-奖助学金/            1 篇
│   ├── 08-国际交流/            8 篇
│   ├── 09-校园生活/            4 篇
│   ├── 10-新闻动态/           20 篇
│   ├── 11-数字大外/            1 篇
│   └── 12-就业与深造/          2 篇
├── scripts/
│   ├── build_index.py          索引命令行：--full 全量 / --incremental 增量
│   ├── crawl_dlufl.py          从官网抓资料，转 Markdown（可反复运行补抓）
│   ├── tidy_titles.py          整理抓取后的文件名（去掉面包屑标题、站点后缀）
│   ├── clean_nav.py            洗掉正文里混入的站点导航 / 页脚
│   ├── eval.py                 检索评测：36 条问题，算 Recall@1 / Recall@k / MRR
│   ├── fix_paths.py            项目搬家后修 .venv 里写死的绝对路径
│   └── set_key.py              安全写入 API key（读剪贴板、自动补 sk- 前缀）
├── storage/                    索引产物，可删，删了重建
│   ├── chunks.json             所有片段（BM25 用）
│   ├── manifest.json           每个文件的 mtime/大小 + 它产生的片段 id（增量依据）
│   └── chroma/                 向量库
├── web/
│   ├── index.html              单页前端：登录页 + 对话页 + 深色模式
│   └── assets/                 校徽、登录背景图
├── .vscode/                    开箱即用的调试/任务配置
│   ├── launch.json             F5 启动服务、调试重建脚本
│   ├── tasks.json              ⌘⇧B：增量更新 / 全量重建 / 抓资料 / 起服务
│   └── settings.json           解释器指向 .venv，排除缓存目录
├── start.sh                    一键启动
├── requirements.txt
└── .env.example                配置模板
```

---

## 三、资料怎么来、怎么扩

### 1. 自动抓官网（已抓 64 篇）

```bash
python scripts/crawl_dlufl.py            # 抓全部栏目，约 3-5 分钟
python scripts/crawl_dlufl.py --limit 3  # 每个栏目只抓 3 篇
```

- 只抓公开页面，不登录、不绕过权限，跳过 pdf/doc 附件
- 已存在的同名文件会跳过，所以**可以反复运行补抓**
- 新增的栏目在 `scripts/crawl_dlufl.py` 顶部的 `SEEDS` 里加一行即可

### 2. 手工放文件

把 `.md` / `.txt` 丢进 `data/<栏目>/` 即可，一个文件算一篇文档，**文件名就是引用里显示的来源**。

### 3. 更新索引（增量）

三种方式，效果一样：

```bash
python scripts/build_index.py --incremental     # 命令行
```
- 页面右上角「更新索引」按钮（按住 Option 点击 = 全量重建）
- VS Code `⌘⇧B` → 增量更新索引

改一个文件只重算那一篇，未改动的片段一条都不动（实测 258 段全库 7.7s，增量 1.1s）。

---

## 四、想改什么，改哪里

| 我想…… | 改哪 | 怎么改 |
| --- | --- | --- |
| 加资料 | `data/<栏目>/` | 放 `.md`/`.txt` → 点「更新索引」 |
| 改回答风格 / 引用格式 / 兜底话术 | `app/prompt.py` | 改 `SYSTEM_PROMPT`、`NO_HIT_ANSWER` |
| 切分粒度 | `.env` | `CHUNK_SIZE=400`、`CHUNK_OVERLAP=80`（改完要 `--full` 重建） |
| 召回条数 | `.env` | `TOP_K=4`（喂给模型的段数）、`RECALL_N=15`（每路召回） |
| 换模型 / 换供应商 | `.env` | `DEEPSEEK_MODEL`、`DEEPSEEK_BASE_URL`（多数要带 `/v1`） |
| 中文检索更准 | `.env` + 一条命令 | `pip install sentence-transformers` → `EMBED_PROVIDER=st` |
| 检索算法（加 rerank） | `app/store.py` | `Index.search()` 末尾接一层重排 |
| 界面配色 / 布局 | `web/index.html` | 顶部 `:root` 是浅色变量，`html[data-theme="dark"]` 是深色 |
| 登录逻辑 | `web/index.html` | `#login-form` 的 `onsubmit`；现在是前端演示，不发请求 |
| 端口 | `.env` | `PORT=8000` |

---

## 五、代码怎么读（按这个顺序，20 分钟）

1. **`app/main.py`**：4 个接口。重点看 `chat()` 里的 4 个分支（无命中 / 无 key / 正常 / 异常）。
2. **`app/store.py`**：`scan_files` 比对文件 → `build_chunks` 切分 → `Index.rebuild/update` 建索引 → `Index.search` 检索。
3. **`app/prompt.py`**：片段被拼成 `【1】来源：xxx` 塞进 system prompt，所以模型会写 `[1]`。
4. **`app/llm.py`**：20 行，`AsyncOpenAI(...).chat.completions.create(stream=True)`。
5. **`web/index.html`**：`ask()` 解析 SSE；`md()` 把 Markdown 渲染成 HTML 和角标。

---

## 六、三个可以拿去讲的技术点（都是真做的）

1. **片段带标题上下文**
   每个 chunk 记 `文件 · 小节`，索引时拼进去。不做这件事，问"最近有什么大事"召回的是"学科建设"——因为事件段落里不会重复出现"大事"两个字。

2. **双路召回 + 加权融合**
   向量（Chroma）+ BM25（jieba 分词）各取 15 条，用 `1/rank` 加权融合，向量权重 0.45（Chroma 自带的是英文小模型，中文不可靠）。试过 RRF(k=60)，中文场景下关键词的强信号会被抹平，改成 1/rank 后才稳。

3. **增量索引**
   `manifest.json` 存每个文件的 `mtime + size` 和它产生的片段 id。更新时只对新增/修改/删除的文件做向量化，其余原样保留；BM25 在内存里全量重算（258 段约 30ms，可忽略）。

---

## 七、实测数据（本机 M 系列 Mac）

| 项目 | 数值 |
| --- | --- |
| 全量建库 | 64 篇 → 258 段，**7.7s** |
| 增量（无变化） | **1.1s**，新增 0 / 修改 0 |
| 增量（改 1 篇） | **1.3s**，修改 1 |
| 首字响应 | **1.1–1.2s**（deepseek-chat） |
| 单次问答成本 | 约 **¥0.002–0.004** |
| 磁盘占用 | 项目 532MB（`.venv` 528MB）+ Chroma 模型缓存 167MB |
| 运行内存 | 进程约 **23MB** |

---

## 八、常见问题

- **页面打不开（404）**：先 `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/`，不是 200 说明 `web/index.html` 不在了或服务没起。`git status` 能看到文件是否被误删，`git checkout -- web/index.html` 可恢复。
- **改了页面但浏览器还是旧的**：浏览器会缓存，按 **⌘⇧R** 强制刷新。
- **`Load failed` / 图片不显示**：别用 `file://` 双击打开页面，用 http://127.0.0.1:8000 。前端已做兜底（`file://` 时自动指向本地接口、图片失败显示占位），但仍建议走服务地址。
- **报 401 / api key invalid**：key 少了 `sk-` 前缀最常见（正版 35 位）。用 `python scripts/set_key.py` 会自动补。
- **报 404**：`DEEPSEEK_BASE_URL` 少了 `/v1`。
- **`向量索引不可用，已降级为纯 BM25`**：模型没下载成功，功能仍可用。
- **端口占用**：`lsof -i :8000`，或 `.env` 改 `PORT`。
- **把项目文件夹移动/改名之后**：① `python scripts/fix_paths.py` 修 venv 里的绝对路径；② 重启服务（`Ctrl+C` 再 `bash start.sh`）；③ VS Code 重新打开新路径。数据不会丢，git 和历史都在文件夹里跟着走。

---

## 九、还没做的（讲"后续规划"时用）

- 评测集：攒 30 条问题算准确率，把"88%"变成可复现的数字
- 多轮指代消解：现在只把历史拼进 prompt，没做 query 改写
- 权限：不同学院看到不同资料
- 部署：现在只跑在本机 127.0.0.1

---

## 十、检索评测（36 条问题）

`eval/questions.jsonl` 是我按栏目挑的 36 条典型问题，每条标注"应该命中哪篇文档"（同一个问题有多篇文档都能回答的，允许写多个）。

```bash
python scripts/eval.py            # 只测检索，不花 token，约 3 秒
python scripts/eval.py --show 5   # 打印失败样例，调参时看
```

当前结果（`TOP_K=4`）：

| 指标 | 数值 | 含义 |
| --- | --- | --- |
| Recall@1 | 77.8%（28/36） | 第一名就命中正确文档 |
| **Recall@4** | **100%（36/36）** | 前 4 段里一定包含正确文档 |
| MRR | 0.856 | 正确文档平均排在第 1.17 位 |
| 平均检索耗时 | 83 ms | 向量 + BM25 双路 + 融合 |

**这是"检索命中率"，不是"回答准确率"。** 简历里请写前者——回答质量还取决于模型和提示词，说成准确率会被追问。

调参记录（都是实测过的）：
- 纯 RRF（k=60）→ 中文场景关键词信号被抹平，改用 `1/rank` 加权
- 只分词 → "学院" 与 "日本语学院" 分词粒度不同召不回，补中文二元组
- 新闻稿词频噪声大 → 新闻类文档（`10-` 开头）检索降权 0.5
- "学院/保研/推免"这类口语与公文用词不一致 → 查询侧做同义词扩展
