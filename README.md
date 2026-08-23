# Inuyasha Art Workflow

这是一个面向犬夜叉漫画版、TV 版图像生成与局部编辑的 Codex 工作流仓库。它打包了可安装的 skill、参考图库、可重建目录索引，以及按任务保存的提示词、尝试记录和 QA 证据。

这不是模型权重或独立绘图应用，也不是当前 macOS 上正在运行的 live skill；它是用于迁移、验证和版本管理的可移植 package snapshot。

> [!IMPORTANT]
> 仓库可见性不等于其中官方设定图、漫画页面、TV 截图或衍生图像获得了再分发许可。任务历史还可能保留本地路径与来源信息，公开 fork、镜像或再发布前请先检查素材权利和隐私。

## 快速开始

CI 使用 Python 3.12。普通图像引用不需要 Poppler；只有直接读取 PDF 页面时才需要 `pdftoppm`。

### macOS / Linux

```sh
git clone https://github.com/juemimgcd/inuyasha-art-workflow.git
cd inuyasha-art-workflow
./setup-python-env.sh

RUN=./skill/generate-inuyasha-manga-art/scripts/run-python
"$RUN" skill/generate-inuyasha-manga-art/scripts/build_reference_index.py
"$RUN" skill/generate-inuyasha-manga-art/scripts/validate_workflow.py
```

`setup-python-env.sh` 只会创建仓库内、已忽略的 `.venv` 并安装依赖；它不会覆盖系统 Python，也不会把 package skill 安装到 Codex 的 live skill 目录。

### Windows 11 / PowerShell

建议使用短路径并避开 OneDrive 同步目录：

```powershell
git clone https://github.com/juemimgcd/inuyasha-art-workflow.git C:\src\inuyasha-art-workflow
Set-Location C:\src\inuyasha-art-workflow
Set-ExecutionPolicy -Scope Process Bypass
.\setup-windows.ps1
```

该脚本会创建仓库 `.venv`、安装依赖、备份并安装 skill 到 `$HOME\.agents\skills\generate-inuyasha-manga-art`、设置 `INUYASHA_WORKFLOW_HOME`、重建目录索引并验证工作流。完成后重启 Codex。

## 从哪里开始

- 日常生成、编辑、检索和候选验收从 [`SKILL.md`](skill/generate-inuyasha-manga-art/SKILL.md) 开始。
- 维护、迁移、归档或处理验证失败时，再读取 [`workflow-contract.md`](skill/generate-inuyasha-manga-art/references/workflow-contract.md)。
- 每个脚本都可以通过 `--help` 查看参数；完整任务生命周期以 skill 文档为准。

## 仓库内容

| 路径 | 用途 |
| --- | --- |
| `skill/generate-inuyasha-manga-art/` | 受版本控制的 package skill、脚本、测试和规则；不是本机 live runtime。 |
| `workflow/reference-workflow/` | SQLite 目录、标注、任务、尝试、提示词、QA、输出和历史溯源。 |
| `libraries/inuyahsa-official/` | 官方角色与设定参考；目录拼写为历史兼容而保留。 |
| `libraries/origin-photos/` | 精选漫画原图与 TV 截图。 |
| `libraries/selected-output/` | 用户明确选中的生成结果，用于连续性参考。 |
| `tools/sync_installed_skill.py` | 将已审阅的 live skill 文件安全同步回 package；维护前先读 [`AGENTS.md`](AGENTS.md)。 |

个人素材目录 `inuyasha-mine` 不再打包进当前仓库，也不进入活动目录索引。

## 常用维护命令

```sh
RUN=./skill/generate-inuyasha-manga-art/scripts/run-python

# 检查目录索引；新鲜时退出码为 0，过期时为 3
"$RUN" skill/generate-inuyasha-manga-art/scripts/build_reference_index.py --check

# 仅在索引过期或素材配置变化后重建
"$RUN" skill/generate-inuyasha-manga-art/scripts/build_reference_index.py

# 结构与记录验证
"$RUN" skill/generate-inuyasha-manga-art/scripts/validate_workflow.py

# 完整单元测试
.venv/bin/python -m unittest discover \
  -s skill/generate-inuyasha-manga-art/tests -v
```

Windows 安装完成后使用已安装的 PowerShell launcher：

```powershell
$skill = "$HOME\.agents\skills\generate-inuyasha-manga-art"
& "$skill\scripts\run-python.ps1" "$skill\scripts\build_reference_index.py" --check
```

结构验证通过只表示目录、规则和记录一致，不代表生成图像已经通过视觉质量评审。初始上传时的历史验证结果保存在 [`VALIDATION.md`](VALIDATION.md)，不要把其中的旧数量当作当前状态。

## 可移植性与环境变量

- SQLite 目录包含机器路径；首次 clone、换机器或移动仓库后应重建。
- 历史 task/attempt JSON 是 append-only 证据，不应为迁移而重写；仍在配置中的旧根路径由 aliases 处理。
- launcher 会对显式但不可用的 Python 直接报错，不会静默切换到另一个环境。

| 变量 | 作用 |
| --- | --- |
| `INUYASHA_BOOTSTRAP_PYTHON` | 仅为 `setup-python-env.sh` 指定用于创建 `.venv` 的 Python。 |
| `INUYASHA_PYTHON` | 为单次 launcher 调用指定已有且包含 Pillow 的解释器，适合临时 worktree。 |
| `INUYASHA_WORKFLOW_HOME` | skill 被复制到仓库外时，指向这个 package 根目录。 |
| `INUYASHA_WORKFLOW_ROOT` | 只覆盖生成任务和目录数据的位置，不改变 package 根目录。 |

## 自动化

- `Cross-platform workflow` 会在 push 和 pull request 上使用 Python 3.12，分别验证 Windows、macOS 和 Ubuntu。
- 合入 `main` 的 pull request 会把浮动标签 `latest` 移到执行时的 `main`。`latest` 不是不可变版本；需要可复现引用时请固定 commit SHA。

## 数据与权利边界

历史任务可能仍保留已经移除的 `/Users/jquery/Documents/inuyasha-mine` 路径作为当时实际使用来源的证据；这不表示对应二进制仍在当前仓库树中。

官方设定图、漫画页面和 TV 截图的权利仍归各自权利人。生成结果及其来源记录也应按实际用途单独审查；本仓库的工作流结构不授予第三方素材的再分发许可。
