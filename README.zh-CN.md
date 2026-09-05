<p align="center">
  <img src="https://raw.githubusercontent.com/StarryGuli/bilingual-epub-toolkit/main/assets/readme/hero.svg" width="100%"
       alt="Bilingual EPUB Toolkit —— 两本单语 EPUB 进，一本对照书出，译文糊住，点按显示">
</p>

<p align="center">
  <a href="https://epub.starry-files.duckdns.org"><b>在线试用</b></a> ·
  <a href="./README.md">English</a> ·
  <a href="#安装">安装</a> ·
  <a href="#用法">用法</a> ·
  <a href="#翻译">翻译</a> ·
  <a href="#已知限制">已知限制</a>
</p>

<p align="center">
  <a href="https://pypi.org/project/bilingual-epub-toolkit/"><img alt="PyPI 版本" src="https://img.shields.io/pypi/v/bilingual-epub-toolkit"></a>
  <img alt="License: Apache-2.0" src="https://img.shields.io/badge/license-Apache--2.0-blue">
  <img alt="Python 3.9+" src="https://img.shields.io/badge/python-3.9%2B-blue">
  <img alt="仅依赖 lxml" src="https://img.shields.io/badge/dependencies-lxml-lightgrey">
</p>

生成对照式双语 EPUB：每一段原文下面紧跟它的译文，默认糊住，点一下才显示。

支持任意标准 EPUB、任意语言对。章节结构和段落配对都从文件本身推导，不需要为每本书
单独配置。全部处理在本地完成。

- **merge** 把两个单语版本合成一本对照书
- **split** 把对照书按语言拆回单语书
- **remerge** 用不同参数重新生成已有的对照书
- **translate** 缺的那一侧可以用模型 API 翻，也可以交给编码 agent 翻
- 命令行、终端向导、本地网页三种界面，中英双语

## 安装

```bash
pip install bilingual-epub-toolkit
```

中文繁简转换需要 opencc：

```bash
pip install "bilingual-epub-toolkit[chinese]"
```

需要 Python 3.9 或更高版本。运行时只依赖 lxml。

装好后有三个命令：

| 命令 | 界面 |
| --- | --- |
| `bilingual-epub` | 命令行 |
| `bilingual-epub-tui` | 终端向导，逐项询问，不用记参数 |
| `bilingual-epub-web` | 本地网页，可拖拽文件 |

界面语言跟随系统 locale，也可以用 `--lang en` / `--lang zh` 指定。

## 快速开始

仓库自带两本示例书：

```bash
bilingual-epub merge --a examples/sample-en.epub --b examples/sample-fr.epub --out demo.epub
```

用苹果图书或任意 EPUB 3 阅读器打开 `demo.epub` 即可。示例书是为这个项目现写的原创
短文，不涉及任何第三方版权。不想安装可以直接用
[epub.starry-files.duckdns.org](https://epub.starry-files.duckdns.org)；
那台上传上限 25 MB，文件 30 分钟后自动删除。

<p align="center">
  <img src="https://raw.githubusercontent.com/StarryGuli/bilingual-epub-toolkit/main/assets/readme/demo.gif" width="100%"
       alt="选好两本 EPUB、上传、合并，最后是按章的对齐统计表">
</p>

## 用法

### merge

把两个单语版本合并：

```bash
bilingual-epub merge \
  --a english.epub --b french.epub --out bilingual.epub \
  --blur-side b --blur 0.25em
```

| 参数 | 作用 |
| --- | --- |
| `--blur-side a\|b` | 哪一侧糊住、点按才显示（默认 `b`） |
| `--no-blur` | 纯对照排版，两侧都不糊 |
| `--blur` | CSS 长度，用 `em` 会跟随阅读器字号缩放 |
| `--title`、`--author` | 覆盖自动拼接的书名和作者 |
| `--convert-side`、`--convert` | opencc 转换，例如 `--convert-side b --convert tw2sp` |

每次合并后会按章打印一张表，报告有多少段是一对一配上的。

### split

按语言把对照书拆开：

```bash
bilingual-epub split --in bilingual.epub --out-dir ./split/ --langs en,fr
```

段落归属读的是每个块的 `lang` 属性。不带 `--langs` 就把识别到的语言全部拆出来。

### remerge

用不同参数重新生成已有的对照书：

```bash
bilingual-epub remerge --in old.epub --out new.epub --blur-side a --blur 0.35em
```

等价于先 split 再 merge。也可以把别处来的双语书转成这个点按显示的形式。

## 翻译

只有一个版本时，另一侧可以生成出来。两条路子产出的译文都与原文块数、顺序一致，
因此随后的合并能把每一段精确配对。

### 交给编码 agent

装一个 skill，让 Claude Code 这类 agent 会用这个工具，
用已有的订阅额度翻译，不走按量计费的 API：

```bash
bilingual-epub skill      # 写出 .claude/skills/bilingual-epub/SKILL.md
```

skill 文件也可以从[线上那台](https://epub.starry-files.duckdns.org/skill)下载。

底层命令可以直接用：

```bash
bilingual-epub export-text --in book.epub --out book.json
# 把 book.json 翻译成 translated.json
bilingual-epub import-text --export book.json --text translated.json \
    --out book.zh.epub --lang zh
```

`import-text` 接受字符串 JSON 数组、带 `blocks` 的 JSON 对象，或每行一段的纯文本。
块数与原文对不上的文件会被拒绝。

### 用模型 API

```bash
bilingual-epub translate --in book.epub --out book.zh.epub --to zh \
    --base-url https://api.deepseek.com/v1 --api-key "$KEY" --model deepseek-chat
```

| 参数 | 作用 |
| --- | --- |
| `--dialect openai` | `/chat/completions`；OpenAI、DeepSeek、月之暗面、智谱、硅基流动、OpenRouter、Groq、Together、Ollama、LM Studio、vLLM（默认） |
| `--dialect anthropic` | `/v1/messages` |
| `--dry-run` | 只报块数、字数、请求数，不发送任何请求 |
| `--batch-size` | 每次请求发多少段（默认 20） |
| `--cache` | 进度文件，中断后重跑会从这里续上 |

凭据也可以通过 `BILINGUAL_API_KEY`、`OPENAI_API_KEY`、`ANTHROPIC_API_KEY` 提供。
返回块数不对的批次会重试、再对半拆分，绝不原样接受。

## 自建部署

网页界面默认面向 localhost 上的单个可信用户。`--public` 会切换成适合共享主机的形态：

```bash
bilingual-epub-web --public --port 8799
```

公开模式拒绝填写服务器端路径、隔离每个访客的文件、按来源地址限流、上传上限 25 MB、
闲置会话 30 分钟后清除（`--ttl` 可调）。

可以启用 Cloudflare Turnstile 过滤自动化流量，同时保持服务对所有人开放：

```bash
export TURNSTILE_SITEKEY=0x...
export TURNSTILE_SECRET=0x...
bilingual-epub-web --public
```

启用后每个任务在执行前都会校验；连不上 Cloudflare 时任务会被拒绝。不配密钥则不渲染
控件、也不做校验。

## 工作原理

章节边界通过读取 EPUB 的 container、OPF、manifest 和 spine 定位，再挑出以章节频率
反复出现的那个标题层级。

段落配对使用 Gale–Church 对齐：基于长度的统计模型，用动态规划求解，并对共现的标题
加权，让章节起点锚定整个序列。既处理一对一，也处理翻译中被拆分或合并的段落。

输出的每个块都带 `lang` 属性，这正是 `split` 能够逆转 `merge` 的原因。点按显示由
CSS `:target` 配合一小段渐进增强脚本实现，两者都不支持时会退化为直接显示。

## 已知限制

| 限制 | 表现 |
| --- | --- |
| DRM 加密文件 | 加密 EPUB 提取不到正文，工具会报告并停止 |
| 没有标题的书 | 退化成单章。正文不丢，但没有章节划分 |
| 统计对齐 | 增删或重构过内容的版本配对不完美，打印的表格会报告实际比例 |
| 未标注语言的双语书 | `split` 依赖逐段的 `lang` 属性，缺少时无法拆分 |

除生成的示例书外，本仓库不包含任何 EPUB，`*.epub` 已在 gitignore 中排除。

## 开发

```bash
git clone https://github.com/StarryGuli/bilingual-epub-toolkit.git
cd bilingual-epub-toolkit
pip install -e ".[dev,chinese]"
pytest && ruff check .
```

测试用的 EPUB 由代码现场构造，不往仓库里放书，见
[`tests/conftest.py`](./tests/conftest.py)。覆盖三个操作的端到端流程、两种封面图格式、
针对桩 API 的翻译往返、公开模式的会话隔离与限流，以及各条错误路径。

测试范围和约定见 [CONTRIBUTING.md](./CONTRIBUTING.md)。

## 许可

Apache-2.0，见 [LICENSE](./LICENSE)。
