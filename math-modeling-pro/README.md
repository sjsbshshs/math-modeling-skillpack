# Math Modeling Pro

入口见 `SKILL.md`。当前版本采用 Stage 1--6：题目与数据审计、证据与模型选择、实现及模型否决门、论文、编译视觉检查、独立验收与提交。

主要可执行工具：

- `scripts/compile_paper.ps1`：Windows/TeX Live 双遍编译与日志门。
- `scripts/audit_project.py`：PDF、ZIP、匿名属性、字体、页码、大小和哈希的通用检查。
- `scripts/check_paper_consistency.py`：论文↔结果三层一致性比对（清单自洽、清单↔结果文件、清单↔PDF）与代码注释章节引用 lint。
- `scripts/create_run_manifest.py`：记录 Python/系统/TeX 工具版本，并为指定输入与代码生成 SHA-256 清单。
- `scripts/smoke_test_template.py`：对 latex-template 做编译烟测（复用 audit_project 的 PDF 检查）。

官方规则、模型质量门和跨平台说明分别位于：

- `references/official-compliance.md`
- `references/quality-gates.md`
- `references/paper-consistency.md`
- `references/innovation-mechanisms.md`
- `references/cross-platform-execution.md`
- `references/validation-and-contribution.md`
- `references/data-and-reproducibility.md`

模板与方法资料是候选工具，不能替代当届官网规则和项目级模型验证。
