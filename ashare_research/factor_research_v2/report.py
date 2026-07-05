from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def formula_to_chinese(text: str) -> str:
    mapping = {
        "RET1": "1日收益",
        "RET5": "5日收益",
        "VOL_RATIO20": "20日成交量比例",
        "VOLUME_WEIGHTED_RET": "成交量加权收益",
        "TREND60": "60日趋势",
        "ADD": "相加",
        "SUB": "相减",
        "MUL": "相乘",
        "DIV": "相除",
        "NEG": "取负",
        "ABS": "取绝对值",
        "SIGN": "取方向",
        "DELTA5": "5日变化",
        "DECAY_LINEAR20": "20日线性衰减",
        "ZSCORE20": "20日标准化",
    }
    out = text
    for key, val in mapping.items():
        out = out.replace(key, val)
    return out


def write_report(run_dir: str | Path, summary: dict[str, Any]) -> None:
    run = Path(run_dir)
    lines = [
        "# 自主因子研究系统 v2 MVP 报告",
        "",
        "本报告为 historical_research_result，不是最终样本外证明，也不是投资建议。",
        "",
        "## 研究范围",
        f"- 数据区间: `{summary['research_data_start']}—{summary['research_data_end']}`",
        f"- 候选公式数量: `{summary['counts'].get('generated', 0)}`",
        f"- 快速筛选通过: `{summary['counts'].get('fast_screen_passed', 0)}`",
        f"- 完整回测数量: `{summary['counts'].get('full_backtest', 0)}`",
        "",
        "## 阶段漏斗",
    ]
    for stage in summary.get("stage_summaries", []):
        lines.append(f"- {stage['stage']}: input={stage['input_count']} passed={stage['passed_count']} rejected={stage['rejected_count']}")
    lines.extend(["", "## 候选因子评级"])
    for rec in summary.get("registry_records", []):
        lines.append(f"- `{rec['grade']}` `{rec['canonical_formula']}`: {formula_to_chinese(rec['canonical_formula'])}")
        lines.append(f"  - 风险: 仅为已见历史研究结果，可能受市场环境、成本、拥挤交易和数据修订影响。")
    lines.extend([
        "",
        "## 下一步建议",
        "- 在用户批准后扩大 candidate_count，并补全 required robustness 中的成本、持有期和分组敏感性。",
        "- 继续保持前向数据与历史研发数据隔离。",
    ])
    (run / "research_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (run / "research_report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
