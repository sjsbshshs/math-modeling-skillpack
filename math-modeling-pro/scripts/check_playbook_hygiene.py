"""Playbook 卫生检查：防止"历史赛题答案"被当作本题靶值。

背景：`references/playbooks/` 的案例小节含历年赛题的具体结果数值（如 2023A 定日镜
总输出 60.12 MW）。这些数值对 agent 有害——不是被"抄"，而是被当作**量级校准的靶值**。
本脚本把该约定固化为可执行的机器门，规则如下：

1. case_isolation  含历史赛题解的小节必须位于文件末尾的隔离区
                   （标题 `## 附：历史赛题案例参考（后置隔离区）`）之内，且该区前有 `---` 分隔线。
2. answer_marking  隔离区内的"历史结果数值"行必须带标记 `[<年份题号> 历史答案｜禁止作为本题靶值]`。
3. guard_present   隔离区必须含统一护栏（禁止作为靶值 / 禁止复刻结构）。
4. method_history  `## 方法应用史（仅参考）` 只允许出现"题号 + 方法名"，出现具体数值结果即失败
                   （该小节在正文，agent 一定会读到）。

退出码 0 = 通过；1 = 有 FAIL；2 = 配置错误。
用法: python check_playbook_hygiene.py [--playbooks <目录>] [--strict]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "references" / "playbooks"
ISOLATION_TITLE = "附：历史赛题案例参考（后置隔离区）"
CASE_KEYS = ("解题示例", "方法应用史走查", "获奖论文方法参考")
MARK_RE = re.compile(r"\[[^\]]{0,24}历史答案｜禁止作为本题靶值\]")
GUARD_KEYS = ("禁止作为本题靶值", "禁止将其作为本题的靶值")
HEAD_PAT = re.compile(r"^##(?!#)\s*(.+)$", re.M)

# "结果数值"：2+ 位小数、坐标对、或带工程单位/金额的数值
NUM_RE = re.compile(
    r"(?:"
    r"\d+\.\d{2,}"
    r"|\(\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\)"
    r"|[-−]?\d+(?:\.\d+)?\s*(?:MW|kW|m/s|km/h|海里|万元)"
    r")"
)
# "结果性措辞"：只有同时出现这些词与数值，才认定为"历史答案"，需要标记。
# 单纯"含数字"会把公式系数、题给参数、求解器区间全部误报。
RESULT_WORDS = (
    "最优", "最大", "最小", "总输出", "总时长", "得分", "利润", "收率", "时长",
    "效率为", "结果为", "结论", "碰撞发生", "均衡解", "失败概率", "拟合优度",
    "守约率", "R²", "R2=",
)
# 与题目数值无关的行（阈值、求解器参数、题给条件、量级直觉、算法设置）不参与判定
EXEMPT = ("P<0.05", "P=0.", "P <", "MIPGap", "TotalCredit", "Bernoulli", "rand >=",
          "x_0", "base_price", "base_cost", "步长", "阈值", "自由度", "置信水平",
          "给定", "额定", "不超过", "\\geq", "\\leq", "与物理直觉对比", "量级",
          "U(", "C(8", "种方案", "次迭代", "种群", "惩罚", "约束")


def sections(text: str) -> list[tuple[str, str, int]]:
    marks = list(HEAD_PAT.finditer(text))
    out: list[tuple[str, str, int]] = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append((m.group(1).strip(), text[m.start():end], text[: m.start()].count("\n") + 1))
    return out


def check_file(path: Path) -> tuple[list[str], list[str]]:
    fails: list[str] = []
    notes: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    secs = sections(text)

    isolation = [(t, b, ln) for t, b, ln in secs if t.startswith("附：历史赛题案例参考")]
    if not isolation:
        fails.append("case_isolation: 缺少后置隔离区（历史案例未隔离）")
        return fails, notes

    iso_title, _iso_body, iso_line = isolation[0]
    # 隔离区 = 该标题起至文件末尾（案例小节已降级为 ###，不再是独立 ## 小节）
    iso_body = text[text.find(iso_title):]
    if not any(k in iso_body for k in GUARD_KEYS):
        fails.append("guard_present: 隔离区缺少统一护栏文本")
    # 1. 隔离区必须自成一节并位于文件末尾（其后不得再有 ## 小节）
    idx = secs.index(isolation[0])
    after = [t for t, _, _ in secs[idx + 1:]]
    if after:
        fails.append(f"case_isolation: 隔离区之后仍有小节 {after}（应为文件末尾）")
    # 2. 隔离区前需有分隔线
    if "---" not in text[: _offset(text, iso_title)]:
        notes.append("case_isolation: 隔离区前未找到 `---` 分隔线（建议补）")
    # 3. 案例小节应已降级并收进隔离区
    zone = text[text.find(iso_title):]
    in_zone = [t for t in CASE_KEYS if re.search(rf"^###\s*{re.escape(t)}", zone, re.M)]
    leaked = [t for t in CASE_KEYS if re.search(rf"^##(?!#)\s*{re.escape(t)}", zone, re.M)]
    if leaked:
        fails.append(f"case_isolation: 以下案例小节未降级，仍是 ## 同级 -> {leaked}")
    notes.append(f"隔离区内案例小节 {len(in_zone)}/{len(CASE_KEYS)} 类：{in_zone}")
    # 5. 未标记的"历史答案"行：需同时具备 结果性措辞 + 数值
    unmarked = []
    for offset, line in enumerate(iso_body.splitlines()):
        if not NUM_RE.search(line):
            continue
        if not any(w in line for w in RESULT_WORDS):
            continue
        if any(e in line for e in EXEMPT):
            continue
        # 公式/变量的解释句（"其中 X 是…"）不是结果陈述
        if line.lstrip().startswith(("其中", "设 ", "记 ", "式中")):
            continue
        if not MARK_RE.search(line):
            unmarked.append((iso_line + offset, line.strip()))
    for ln, line in unmarked:
        fails.append(f"answer_marking: L{ln} 含历史结果数值但未标记 -> {line[:80]}")

    # 6. 正文里的"方法应用史（仅参考）"谱系小节（只查 ## 直属的列表内容；
    #    其下的 ### Step 正文属于方法说明，不含本题结果，不参与判定）
    for title, body, ln in secs:
        if not title.startswith("方法应用史（仅参考）"):
            continue
        first_sub = body.find("\n###")
        scope = body if first_sub < 0 else body[:first_sub]
        for offset, line in enumerate(scope.splitlines()):
            if NUM_RE.search(line) and not line.lstrip().startswith(">"):
                fails.append(f"method_history: L{ln + offset} 谱系小节出现具体数值 -> {line.strip()[:80]}")

    notes.append(f"隔离区含 {len(in_zone)} 个案例小节，"
                 f"标注 {len(MARK_RE.findall(iso_body))} 处历史答案标记")
    return fails, notes


def _offset(text: str, title: str) -> int:
    idx = text.find(title)
    return idx if idx >= 0 else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--playbooks", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--strict", action="store_true", help="把 notes 也视为失败")
    args = ap.parse_args()

    if not args.playbooks.is_dir():
        print(f"playbooks 目录不存在: {args.playbooks}", file=sys.stderr)
        raise SystemExit(2)

    all_fails: dict[str, list[str]] = {}
    all_notes: dict[str, list[str]] = {}
    for f in sorted(args.playbooks.glob("*.md")):
        fails, notes = check_file(f)
        if fails:
            all_fails[f.name] = fails
        all_notes[f.name] = notes

    print(f"检查 {len(list(args.playbooks.glob('*.md')))} 个 playbook\n")
    for name in sorted(all_notes):
        status = "FAIL" if name in all_fails else "PASS"
        print(f"  [{status}] {name}")
        for note in all_notes[name]:
            print(f"          · {note}")
        for fail in all_fails.get(name, []):
            print(f"          ✗ {fail}")

    total = sum(len(v) for v in all_fails.values())
    print(f"\n合计 FAIL {total} 项")
    if args.strict and any(all_notes.values()):
        print("（--strict：notes 也计入失败）")
        total += sum(len(v) for v in all_notes.values())
    raise SystemExit(0 if total == 0 else 1)


if __name__ == "__main__":
    main()
