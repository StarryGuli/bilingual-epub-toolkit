# bilingual-epub-toolkit (原 chatter-bilingual)

通用双语 EPUB 工具，三个操作：

1. **merge** — 两本单语 EPUB（任意书、任意语言对）→ 一本双语 EPUB（英文/A 语言在上，
   B 语言译文紧跟在下、默认模糊，点一下显示，再点一下收回）
2. **split** — 一本双语/多语 EPUB → 按语言拆成独立的单语 EPUB
3. **remerge** — 已有的双语 EPUB → 拆开重新合并成新的双语 EPUB（换模糊程度、
   换糊哪一侧、换转换方式，或者把别处来的双语书转成这个工具的风格）

对齐算法是 Gale-Church 长度模型动态规划（跟原来一样），章节边界靠**自动识别标题
层级**切分——不再需要为每本书手写"这本书内部文件叫什么名"的对照表，所以能处理
任意标准 EPUB，不只是某一本特定的书。

## 这次做了什么

上一版（还在 [contrib/legacy_chatter_build.py](./contrib/legacy_chatter_build.py) 里，保留作存档）
只认识《Chatter》这一本书两个具体版本的内部文件名，换本书直接报错。这次把"认书"
这部分整个换掉：

- 新增 [epub_io.py](./bilingual_epub/epub_io.py)：通用 EPUB 读写——照 `META-INF/container.xml`
  → OPF → manifest/spine 的标准流程读任意 EPUB，不猜文件名。
- 新增 [align_engine.py](./bilingual_epub/align_engine.py)：段落提取 + Gale-Church 对齐（跟原来
  逻辑一致）+ **自动章节切分**——扫一遍全书出现的标题标签，挑一个"反复出现的最高
  层级"当章节边界，不用手写章节表。
- 新增 [merge.py](./bilingual_epub/merge.py)：通用合并引擎，替代原来 `build.py` 里那张写死的
  `CHAPTERS` 表。
- 新增 [split.py](./bilingual_epub/split.py)：按每个块级元素的 `lang`/`xml:lang` 属性归属拆书。
- 原来的 `build.py` 变成 [cli.py](./bilingual_epub/cli.py)，三个子命令的入口；
  [webui.py](./bilingual_epub/webui.py) 加了三个标签页对应三个操作。
- 整体收进 `bilingual_epub/` 包，可以 `pip install`，也可以直接从仓库跑。

**测试方式**：因为手头没有真实的多语言书，用代码现造了两套完全不同形状的假书
（不同章节数、不同标题层级、只有一侧有封面、英法而非英中语言对）验证 merge 全流程、
split 全流程、remerge 全流程，以及 opencc 转换和 `--blur-side none` 关闭模糊的
路径。过程中真的揪出并修了一个 bug：章节标题曾经被渲染两遍（一遍作为"公告式"大
标题、一遍又出现在正文对照里），且公告式标题没打 `lang` 属性——导致 split 时
不但内容重复，法语标题还被错误地并入了英语桶。现在改成标题只在正文对照里出现
一次，配合正确的语言标签，split/merge 互相验证通过。

## 已知限制

- **不认 DRM。** 加密的 EPUB（大多数正版商店买的书）解压后 OPF 里引用的资源是
  密文，读不出正文，会在"提取不到任何正文段落"这一步报错退出，不会崩溃但也
  处理不了。
- **章节边界靠标题标签猜。** 如果一本书从头到尾一个 `<h1>`-`<h6>` 都没用
  （非常不规范的排版），会退化成整本书当一章处理——内容不丢，但没有分章。
- **对齐是统计模型，不是语义理解。** 段落长度、标题共现是启发式信号，长段落
  被错误拆分合并的书（或者两个版本增删内容较多的书），配对可能有偏差——原来
  Chatter 那次实测正文约 93% 是干净的 1:1，可以作为大致预期。
- **split 靠 `lang` 属性，不是万能的。** 这个工具自己合并出的书一定能被正确拆开
  （每个块都打了 `lang=`）；别处来的双语书如果没有逐段标注语言（很多排版精美的
  双语书确实没有），split 会把整本书归到一个语言桶，等于拆不开。

## 用法

装好之后有三个命令：`bilingual-epub`（CLI）、`bilingual-epub-tui`（终端向导）、
`bilingual-epub-web`（网页版）。

```bash
pip install bilingual-epub-toolkit            # 基本功能
pip install "bilingual-epub-toolkit[chinese]" # 额外装 opencc，只有 --convert 才需要
```

不想装、想直接从仓库跑也行——把下面所有 `bilingual-epub` 换成
`python3 -m bilingual_epub.cli` 即可（需要自己先 `pip install lxml`）：

```bash
git clone https://github.com/StarryGuli/bilingual-epub-toolkit.git
cd bilingual-epub-toolkit
pip install -e ".[chinese]"
```

### 最省事：双击就能用

访达里双击这两个文件之一，不用敲任何命令：

| 双击这个 | 效果 |
|---|---|
| `双击打开终端版.command` | 终端向导：一步步问你要做什么，选数字、填路径（**可以直接把 EPUB 从访达拖进窗口**），不用记参数 |
| `双击打开网页版.command` | 自动起本地服务器 **并自动打开浏览器**，三个标签页对应三个操作 |

网页版用完在终端窗口按 `Ctrl+C`（或直接关窗口）即可停止。端口默认 8799，
被占用会自动往后找，不会报 "Address already in use"。

### merge：两本单语 → 一本双语

```bash
bilingual-epub merge \
  --a english.epub --b french.epub \
  --out bilingual.epub \
  --blur-side b --blur 0.25em \
  --convert-side b --convert tw2sp    # 可选:对 B 侧做繁转简等 opencc 转换
```
`--blur-side a|b|none`（默认 b，即"跟着走的那一侧"默认被糊住）。书名/作者默认
自动拼接两侧的 OPF 元数据，也可以用 `--title`/`--author` 覆盖。

### split：一本双语 → 每种语言各一本单语

```bash
bilingual-epub split --in bilingual.epub --out-dir ./split/ [--langs en,fr]
```
不传 `--langs` 就拆出扫描到的全部语言。

### remerge：已有双语 → 新的双语（换风格/换参数，或者收编别处来的双语书）

```bash
bilingual-epub remerge --in old_bilingual.epub --out new_bilingual.epub \
  --a-lang en --b-lang fr --blur-side a --blur 0.35em
```
内部就是先 split 到临时目录，再 merge 一次，用完删掉临时文件。

### 终端向导（不想记参数就用这个）

```bash
bilingual-epub-tui
```
选操作 → 填路径 → 选选项，全程有提示。路径可以直接从访达拖进终端（会自动处理
拖拽产生的转义空格和引号）。填错路径会重问，不会崩。

### 网页界面

```bash
bilingual-epub-web                 # 起服务器并自动打开浏览器
bilingual-epub-web --no-browser    # 只起服务器，不自动开浏览器
bilingual-epub-web --port 9000     # 换端口
```
只监听 127.0.0.1；下载接口只吐这次会话里刚构建出的文件，不接受任意路径。

## 关于书本身

**这个仓库不包含任何书。** 工具处理的是有版权的 EPUB，书归出版社，不进仓库——
`.gitignore` 里 `*.epub` 是全局排除的，测试用的假书也是运行时用代码现造的
（见 [tests/conftest.py](./tests/conftest.py)），没有一个字来自真实出版物。
自己的书自己准备。

这个项目最早是为一本书写的：英文 *Chatter* (Ethan Kross) 配繁体中文译本
《強大內心的自我對話習慣》。那一版把两个具体版本的内部文件名写死在代码里，
现在保留在 [contrib/legacy_chatter_build.py](./contrib/legacy_chatter_build.py)
作为存档——它按出版社目录手工切章，跟新引擎的自动标题切分结果不完全一样。
除非你手上正好是那两个版本，否则用不上它，直接用 `bilingual-epub merge` 就行。
