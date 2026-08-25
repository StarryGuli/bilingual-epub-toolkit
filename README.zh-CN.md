<p align="center">
  <img src="https://raw.githubusercontent.com/StarryGuli/bilingual-epub-toolkit/main/assets/readme/hero.svg" width="100%"
       alt="Bilingual EPUB Toolkit —— 两本单语 EPUB 进，一本对照书出，译文糊住，点一下才显示">
</p>

<p align="center">
  <a href="https://epub.starry-files.duckdns.org"><b>在线试用</b></a> ·
  <a href="./README.md">English</a> ·
  <a href="#安装">安装</a> ·
  <a href="#一条命令先试试">先试试</a> ·
  <a href="#已知限制">限制</a>
</p>

读一本外语书通常只有两个选择：读原文，然后不停查词；或者读译本，然后学不到什么。
这个工具做的是第三种——生成一本 EPUB，每段原文下面紧跟着它的译文，默认糊住，
点一下才显示。

任意标准 EPUB 都能处理，任意语言对。全程在本机运行，文件不上传到任何地方。

## 什么都不用装，直接试

**[epub.starry-files.duckdns.org](https://epub.starry-files.duckdns.org)**
跑的就是这套代码。把两本 EPUB 拖进去，合并好的书就出来了。

那是一台很小的个人服务器，当 demo 用就好：单文件上限 25 MB，按来源地址限流，
上传的和生成的东西 30 分钟后自动删除，别人也下载不到你做的书。真要干活，
或者书本身你就不想传到别人机器上，那就装到本地跑——这份文档剩下的部分讲的就是这个。

## 一条命令先试试

仓库里带了两本示例书，不用先去找书：

```bash
bilingual-epub merge --a examples/sample-en.epub --b examples/sample-fr.epub --out demo.epub
```

把 `demo.epub` 拖进苹果图书，或任何支持 EPUB 3 的阅读器：一段英文，下面跟着糊住的
法语译文，点一下显示，再点一下收回。

示例书是**为这个仓库现写的原创短文**，不是真书，没有版权问题。见
[`examples/`](./examples/)。

## 安装

```bash
pip install bilingual-epub-toolkit
```

要做中文繁简转换（依赖 opencc）：

```bash
pip install "bilingual-epub-toolkit[chinese]"
```

装好之后有三个命令：

| 命令 | 是什么 |
| --- | --- |
| `bilingual-epub` | 命令行，三个子命令 `merge` / `split` / `remerge` |
| `bilingual-epub-tui` | 终端向导，一步步问你，不用记参数 |
| `bilingual-epub-web` | 本地网页，可以直接把书拖进去，不用填路径 |

三个都支持中英文界面，跟随系统语言。想强制指定就用 `--lang zh` 或 `--lang en`。

## 三个操作

### merge —— 两本单语书合成一本

```bash
bilingual-epub merge \
  --a english.epub --b french.epub --out bilingual.epub \
  --blur-side b --blur 0.25em
```

**糊不糊是可选的。** 不想要点按效果、就想要纯对照排版：

```bash
bilingual-epub merge --a english.epub --b french.epub --out plain.epub --no-blur
```

要的话，`--blur-side` 填 `a` 或 `b`，`--blur` 接受任意 CSS 长度，建议用 `em`，
因为它会跟随读者的字号缩放。书名和作者默认拼接两侧原书的元数据，用 `--title` /
`--author` 覆盖。

合并的同时做繁简转换：

```bash
bilingual-epub merge --a en.epub --b zh-hant.epub --out out.epub \
  --convert-side b --convert tw2sp
```

### split —— 把一本双语书拆回单语书

```bash
bilingual-epub split --in bilingual.epub --out-dir ./split/ --langs en,fr
```

哪一段属于哪种语言，是读每个块级元素的 `lang` 属性判断的。不传 `--langs` 就把
识别到的语言全部拆出来。

### remerge —— 换个风格重做一本已有的双语书

```bash
bilingual-epub remerge --in old.epub --out new.epub --blur-side a --blur 0.35em
```

内部就是先拆再合，一步完成。适合换模糊程度、换糊哪一侧，或者把别处来的双语书
收编成这个工具的点按显示风格。

## 原理

要解决两个问题：章节边界在哪，以及哪一段对应哪一段。

**章节**从 EPUB 自己身上读——`META-INF/container.xml` → OPF → manifest/spine，
标准流程。章节边界靠扫描全书出现过的标题层级，挑出那个"像章节一样反复出现"的层级，
所以不需要为每本书手写一张内部文件名对照表。

**对齐**用 Gale–Church：基于段落长度的统计模型，动态规划求解，标题共现时加一个
奖励分，让章节起点起到锚定作用。除了常见的 1:1，也能处理翻译时被拆开或合并的段落。

输出里每个块都带 `lang` 属性——这正是 `split` 能把 `merge` 精确还原回去的原因。

点按显示用的是 CSS `:target` 加一小段渐进增强脚本，两者都不支持的阅读器会退化成
普通的可见文字，不会坏掉。

## 已知限制

- **不支持 DRM。** 加密的 EPUB（大多数正版商店买的书）解压出来是密文，工具会报
  "提取不到任何正文"然后停下。
- **章节识别依赖标题标签。** 一本从头到尾没用过 `<h1>`–`<h6>` 的书会退化成整本
  一章。内容不丢，但没有分章。
- **对齐是统计模型，不是语义理解。** 段落长度和标题共现都是启发式信号。两个版本
  之间有增删或重组的书，配对会有偏差；合并结束后打印的分章表里有 1:1 占比，可以
  据此自己判断质量。
- **`split` 依赖逐段的 `lang` 标注。** 这个工具自己合出来的书一定能干净拆开；
  别处来的双语书很多没有逐段标语言，那种情况下所有内容会落进同一个桶，等于拆不开。

## 书只有一种语言怎么办

没有第二个版本可以合并，那就做一个出来。两条路子产出的译文都跟原文**结构完全平行**
——同样的块、同样的顺序——所以后面合并出来是 100% 一对一，而不是两个独立出版的版本
那种九成左右。

### 让你自己的编码 agent 去翻

这条**完全不需要 API key**：agent 用的是你已经在付的订阅额度。

```bash
bilingual-epub skill            # 写出 .claude/skills/bilingual-epub/SKILL.md
```

然后直接让你的 agent 把这本书做成双语版就行。skill 会告诉它怎么导出文本、翻译、
再装回去。也可以从[线上那台](https://epub.starry-files.duckdns.org/skill)直接下载这个文件。

底层就是三条命令，手动也能用：

```bash
bilingual-epub export-text --in book.epub --out book.json
# ……把 book.json 翻译成 translated.json……
bilingual-epub import-text --export book.json --text translated.json \
    --out book.zh.epub --lang zh
```

译文可以是字符串 JSON 数组、带 `blocks` 的 JSON 对象，或者每行一段的纯文本。
块数对不上会直接报错而不是将就——少一块，后面每一段都会跟错误的原文配对。

### 或者用 API key

自己带 endpoint，账单记在你自己头上。

```bash
bilingual-epub translate --in book.epub --out book.zh.epub --to zh \
    --base-url https://api.deepseek.com/v1 --api-key "$KEY" --model deepseek-chat
```

`--dialect openai`（默认）覆盖 OpenAI、DeepSeek、月之暗面、智谱、硅基流动、
OpenRouter、Groq、Together，以及任何说 `/chat/completions` 的本地服务——Ollama、
LM Studio、vLLM。`--dialect anthropic` 走 `/v1/messages`。

- `--dry-run` 先报块数/字数/请求数，一分钱不花
- 进度存在输出文件旁边，中断之后重跑会续上，不会重复付费
- 一批返回的条数不对会重试、再对半拆、最后逐块翻——绝不将就接受
- key 也可以从 `BILINGUAL_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` 读

## 放到服务器上跑

本地网页版默认「一个可信用户、在自己电脑上」。`--public` 会把这些假设全部换掉，
用于别人能访问到的主机：

```bash
bilingual-epub-web --public --port 8799
```

这个模式下：拒绝填服务器路径（本地那个路径框能打开你自己能打开的任何文件，
放公网就是任意文件读取漏洞）、每个访客一个隔离的临时目录（谁都下载不到别人的书）、
按来源地址限流、上传上限降到 25 MB、闲置会话 30 分钟后自动清除（`--ttl` 可调）。

### 挡住机器人，但不挡住人

光靠 Cookie 和限流拦不住铁了心要刷的人：换 IP 就绕开令牌桶，跑个无头浏览器拿 Cookie
跟真人一样容易。真正抬高成本的是 Turnstile——而且跟密码不同，它对访客是零成本的，
服务照样对所有人开放。

```bash
export TURNSTILE_SITEKEY=0x...      # Cloudflare 后台 Turnstile 里拿
export TURNSTILE_SECRET=0x...
bilingual-epub-web --public
```

之后每一次任务在执行前都会向 Cloudflare 校验一次。校验是**失败即拒**的：连不上
Cloudflare 时任务直接拒绝，而不是悄悄放行。不配密钥就不渲染控件、也不做校验，
本地跑就该是这样。

## 书自己准备

这个仓库不含任何真书，`.gitignore` 里 `*.epub` 是全局排除的，只放行生成的示例书。
工具读的是你手上已经有的文件，怎么拿到那些文件是你自己的事。

## 参与开发

```bash
git clone https://github.com/StarryGuli/bilingual-epub-toolkit.git
cd bilingual-epub-toolkit
pip install -e ".[dev,chinese]"
pytest && ruff check .
```

测试用的假书是运行时用代码现造的，不往仓库里塞书文件——见
[`tests/conftest.py`](./tests/conftest.py)。覆盖 merge / split / remerge 全流程、
两种封面图格式、参数面，以及各条错误路径。

## 许可

Apache-2.0，见 [LICENSE](./LICENSE)。
