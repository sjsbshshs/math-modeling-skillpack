# 数学建模技能包（math-modeling-skillpack）

> 一套**审计式（audit-first）**的数学建模竞赛 AI Agent 技能包：可复现求解工作流 + 基于 **44 篇国奖论文逐篇核验**的行文风格规范，覆盖 CUMCM 国赛与 MCM/ICM 美赛。

![License](https://img.shields.io/badge/License-MIT-blue) ![Works with](https://img.shields.io/badge/works_with-Claude_Code_%7C_Codex_%7C_ZCode-green) ![Contests](https://img.shields.io/badge/contests-CUMCM_%7C_MCM%2FICM-orange)

## 为什么是这一套

现在 GitHub 上的数模 skill 不少，本仓库的差异化在三点：

1. **风格规范有证据链**：`cumcm-paper-style` 的写作/润色/自查规则逐篇核验自 2021–2025 年官方展示的 **44 篇国奖论文原文**，不是凭经验写的"感觉像获奖论文"。
2. **审计式质量门**：不是"生成完就交"。SHA-256 运行清单、论文↔结果↔代码三层一致性机检、提交前独立审计（匿名性、页码、字体、大小、哈希），每一步可复现、可检查。
3. **工作流 + 风格配套**：从选题、赛题与数据审计、模型选择、可复现求解，到论文生成、LaTeX 编译视觉检查、提交前验收，一条链路两个 skill 互相引用。

与同类项目对比（定位速览，星数以各仓库页面为准，整理于 2026-10）：

| 仓库 | 亮点 |
|---|---|
| **本仓库** | 44 篇国奖论文逐篇核验的风格规范 + 审计式质量门 + 工作流/风格双 skill |
| [XiaoMaColtAI/math-modeling-skill](https://github.com/XiaoMaColtAI/math-modeling-skill) | 三阶段工作流（建模分析 / Python·MATLAB 编程 / DOCX 论文） |
| [Lupynow/math-modeling-skills](https://github.com/Lupynow/math-modeling-skills) | 国赛 CUMCM、美赛 MCM/ICM 全题型一条龙工具链 |
| [handsomeZR-netizen/mathmodel-skill](https://github.com/handsomeZR-netizen/mathmodel-skill) | harness-agnostic，适配 Claude Code 等多客户端，覆盖三竞赛 |
| [jihe520/MathModelAgent](https://github.com/jihe520/MathModelAgent) | 独立 Agent，自动产出可提交论文 |

## 30 秒安装

两个 skill 互相引用，**请一起装**。技能目录按客户端区分：

| 客户端 | 用户级技能目录 |
|---|---|
| Claude Code | `~/.claude/skills/` |
| ZCode | `~/.agents/skills/` |
| Codex CLI | `~/.codex/skills/` |
| 其他支持 `SKILL.md` 的 Agent | 对应的 skills 根目录 |

macOS / Linux / Git Bash：

```bash
git clone --depth 1 https://github.com/sjsbshshs/math-modeling-skillpack.git
cp -R math-modeling-skillpack/math-modeling-pro math-modeling-skillpack/cumcm-paper-style ~/.claude/skills/   # 换成你的技能目录
rm -rf math-modeling-skillpack   # 可选：清理克隆
```

Windows PowerShell：

```powershell
git clone --depth 1 https://github.com/sjsbshshs/math-modeling-skillpack.git
Copy-Item -Recurse math-modeling-skillpack\math-modeling-pro, math-modeling-skillpack\cumcm-paper-style "$HOME\.claude\skills\"
Remove-Item -Recurse -Force math-modeling-skillpack   # 可选
```

> **注意**：要把两个 skill **文件夹本身**放进技能目录（目录下第一层直接是 `SKILL.md`），不要把整个仓库原样塞进去——多数客户端只扫描技能目录的第一层子目录。

装好后重启会话即可：

- 对 Agent 说 **"开始求解 / 分析赛题 / 生成论文"** → 触发 `math-modeling-pro` 主工作流；
- 说 **"按国奖风格写 / 论文自查 / 摘要润色"** → 触发 `cumcm-paper-style` 风格技能。

## Demo（制作中）

正在用本技能包对一道 CUMCM 真题做端到端运行（赛题审计 → 建模求解 → 论文 → 提交前审计），完成后在 [demo/](demo/) 附论文 PDF 与过程记录，可直接对照"这套 skill 到底能产出什么"。

## 环境要求

- **Python 3.10+** 及科学计算栈：`numpy`、`scipy`、`pandas`、`matplotlib`（求解与机检脚本均基于 Python）。
- **论文编译**：XeLaTeX（TeX Live 或 MiKTeX）。Windows 下用 PowerShell 7 运行 `math-modeling-pro/scripts/compile_paper.ps1` 进行双遍编译与日志门检查；非 Windows 平台需自行用 xelatex 双遍编译。
- **中文字体已内置**：思源宋体（SIL OFL 开源许可）位于 `math-modeling-pro/latex-template/fonts/`，无需在系统安装。
- `references/code-templates/matlab/` 下的 MATLAB 模板**仅为只读方法对照**，不参与求解，请勿执行。

## 仓库结构

```
├── README.md
├── LICENSE
├── math-modeling-pro/        # 主工作流 skill
│   ├── SKILL.md              # 入口
│   ├── latex-template/       # 国赛 LaTeX 模板（含内置字体）
│   ├── references/           # 方法手册、playbook、论文写作指南、代码模板
│   └── scripts/              # 机检与编译脚本
├── cumcm-paper-style/        # 行文风格 skill
│   ├── SKILL.md              # 入口
│   └── references/templates.md  # 国奖句式模板库
└── demo/                     # 端到端示例（制作中）
```

## English

**math-modeling-skillpack** is an audit-first AI agent skill pack for math-modeling contests (CUMCM / MCM-ICM): a reproducible solve-and-verify workflow plus a paper-writing style guide verified against **44 official national-prize papers (2021–2025)**.

Two skills, designed to be installed together:

- **`math-modeling-pro`** — end-to-end workflow (Stage 0–6): problem & data audit → evidence-based model selection → reproducible solving with quality gates (SHA-256 run manifests, three-way paper↔results↔code consistency checks) → paper generation → LaTeX compile & visual check → independent pre-submission audit.
- **`cumcm-paper-style`** — CUMCM paper style guide: phrasing templates and style-audit rules verified line-by-line against the 44 official prize-winning papers.

**Install** (any agent that reads `SKILL.md`): copy both folders into your user-level skills directory — `~/.claude/skills/` (Claude Code), `~/.agents/skills/` (ZCode), or `~/.codex/skills/` (Codex) — so that each folder sits directly under it, then restart the session. Say *"开始求解"* (start solving) to trigger the workflow, or *"论文自查"* (paper self-review) for the style skill.

**Requirements**: Python 3.10+ with numpy/scipy/pandas/matplotlib; XeLaTeX (TeX Live or MiKTeX). Source Han Serif fonts (SIL OFL) are bundled — no system font setup needed.

An end-to-end demo on a real CUMCM problem (paper PDF + run logs) is in progress and will be published under [demo/](demo/).

## 开源许可 / License

代码与文档以 [MIT License](LICENSE) 发布；内置思源宋体字体遵循其自身的 SIL Open Font License。

## 免责说明 / Disclaimer

模板与方法资料是候选工具，不能替代当届官网规则和项目级模型验证；赛前请以竞赛官方当届发布的规则与格式规范为准。
Templates and reference materials are candidate tools, not a substitute for the current year's official rules or project-level model validation.
