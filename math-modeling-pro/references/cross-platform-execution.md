# 跨平台执行与 TeX/PDF 工具

## 原则

- 先发现环境，再选择命令；不要假设 Bash、PowerShell、固定盘符或 PATH。
- 尊重项目 `AGENTS.md`、现有运行脚本和用户指定解释器。
- 路径含空格或非 ASCII 字符时使用结构化参数和绝对路径，避免拼接 shell 字符串。
- 不为下载资料修改持久代理或系统路由；使用当前环境提供的检索 skill 或一次性代理包装器。

## Windows / PowerShell

优先使用 `scripts/compile_paper.ps1`：

```powershell
& "<skill>\scripts\compile_paper.ps1" -PaperDirectory "<project>\论文" -MainTex "论文.tex"
```

脚本在 PATH（以及 `C:\texlive`、`D:\texlive`）中发现 `xelatex`，执行双遍编译，并在日志出现
`Overfull/Underfull`、字体警告、未解析引用或 `Rerun` 警告时失败；若 `xelatex` 不在 PATH，可传 `-TexBin`。
它只负责编译与日志门，不做 PDF 渲染。

Stage 5 的页面渲染抽检需要单独调用 PDF 工具（`pdftoppm`、`pdftocairo`、`pdftotext`、`pdfinfo`、
`pdffonts`）；这些工具通常随 TeX Live、Poppler 或发行版包提供，与编译脚本相互独立。

## Linux / macOS

使用参数化的本地命令执行两遍：

```text
xelatex -interaction=nonstopmode -halt-on-error 论文.tex
xelatex -interaction=nonstopmode -halt-on-error 论文.tex
```

用 `rg`（或不可用时使用 `grep`）检查日志。不要把示例包装成固定 Bash 脚本，除非项目本身采用 Bash。

## PDF 交叉检查

- `pdfinfo`：页数、A4、加密和元数据；中文路径下若大小异常，使用文件系统 API 复核。
- `pdftotext -layout`：章节完整性、连续页码、匿名关键词和引用文本。
- `pdffonts`：字体嵌入；数学扩展字体可能没有 Unicode 映射，但仍必须嵌入。
- `pdftoppm`：渲染抽检页；日志干净不能替代视觉检查。

至少查看摘要、正文第一页、正文最后两页、复杂公式页、宽表页、代表性图页、参考文献/附录边界和最后一页。
