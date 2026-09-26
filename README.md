# 数学建模技能包（math-modeling-skillpack）

本仓库包含两个配合使用的 AI Agent 技能（skill），面向数学建模竞赛（CUMCM 国赛 / MCM-ICM 美赛）：

| 目录 | 用途 |
|---|---|
| `math-modeling-pro` | 端到端竞赛工作流（Stage 0–6）：选题、赛题与数据审计、模型选择、可复现求解与质量门、论文生成、LaTeX 编译与视觉检查、提交前独立审计 |
| `cumcm-paper-style` | 国赛论文行文风格规范：基于 2021–2025 年官方展示的 44 篇国奖论文逐篇核验的写作 / 润色 / 风格审计指南 |

两者互相引用，**请一起安装**。安装后对 Agent 说"开始求解 / 分析赛题 / 生成论文"即可触发主工作流；说"按国奖风格写 / 论文自查 / 摘要润色"触发风格技能。

## 安装

把 `math-modeling-pro` 和 `cumcm-paper-style` 两个文件夹**完整**复制到你的 Agent 技能目录（例如 `~/.agents/skills/`，或所用客户端的用户级 skills 目录），重启会话即可被识别。

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
│   ├── README.md
│   ├── WORKPLAN.md
│   ├── latex-template/       # 国赛 LaTeX 模板（含内置字体）
│   ├── references/           # 方法手册、playbook、论文写作指南、代码模板
│   └── scripts/              # 机检与编译脚本
└── cumcm-paper-style/        # 行文风格 skill
    ├── SKILL.md              # 入口
    └── references/templates.md  # 国奖句式模板库
```

## 开源许可

代码与文档以 [MIT License](LICENSE) 发布；内置思源宋体字体遵循其自身的 SIL Open Font License。

## 免责说明

模板与方法资料是候选工具，不能替代当届官网规则和项目级模型验证；赛前请以竞赛官方当届发布的规则与格式规范为准。
