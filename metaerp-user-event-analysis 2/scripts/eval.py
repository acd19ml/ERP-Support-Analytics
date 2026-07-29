# -*- coding: utf-8 -*-
"""
分类效果评测 v3 —— 混淆矩阵驱动的 spec 迭代

前提：一个 Excel 同时含工单原文 + 人工审核金标列（列名在 config.yaml 的 eval.gold_columns 配置）。

子命令：
  sample  从金标 Excel 分层抽样出 开发集/测试集（按专题×L1 分层，测试集封存少动）
  score   用 results.jsonl（classify.py 的输出）对比金标：三维度准确率 + 混淆矩阵 + 边界字段统计
  agree   两份 results.jsonl 的一致率（temperature=0 跑两遍；不一致 = spec 有歧义，改 spec 不是调 prompt）

典型迭代循环：
  sample（一次）→ classify.py run 开发集 → score → 看混淆矩阵最大的错误对 → 改 spec.md 对应边界段落 → 重跑 → score
"""
import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd
import yaml

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"
DIMS = [("topic", "专题"), ("l1", "L1"), ("l2", "L2"), ("solution_class", "解决方案")]


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_results(path) -> dict:
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            if "error" not in rec:
                out[rec["ticket_id"]] = rec
    return out


def norm(v):
    v = "" if v is None else str(v).strip()
    return None if v in ("", "nan", "None", "null", "--") else v


def cmd_sample(args, cfg):
    df = pd.read_excel(args.gold, dtype=str).fillna("")
    gold = cfg["eval"]["gold_columns"]
    strata = df[gold["topic"]].str.cat(df[gold["l1"]], sep="|")
    dev_parts, test_parts = [], []
    for _, g in df.groupby(strata):
        g = g.sample(frac=1, random_state=42)
        n_dev = max(1, round(len(g) * args.dev_frac))
        dev_parts.append(g.iloc[:n_dev])
        test_parts.append(g.iloc[n_dev:n_dev + max(1, round(len(g) * args.test_frac))])
    dev, test = pd.concat(dev_parts), pd.concat(test_parts)
    dev.to_excel(args.out_dev, index=False)
    test.to_excel(args.out_test, index=False)
    print(f"开发集 {len(dev)} 条 → {args.out_dev}\n测试集 {len(test)} 条 → {args.out_test}（封存，仅大版本时使用）")


def confusion_report(pairs, dim_name, top_k=8):
    total = len(pairs)
    correct = sum(1 for g, p in pairs if g == p)
    print(f"\n== {dim_name} == 准确率 {correct}/{total} = {correct / total:.1%}" if total
          else f"\n== {dim_name} == 无可对比样本")
    errs = Counter((g, p) for g, p in pairs if g != p)
    if errs:
        print(f"  Top 错误对（金标 → 预测）：")
        for (g, p), n in errs.most_common(top_k):
            print(f"    {g}  →  {p} ： {n} 次")


def cmd_score(args, cfg):
    df = pd.read_excel(args.gold, dtype=str).fillna("")
    gold_cols = cfg["eval"]["gold_columns"]
    id_spec = cfg["excel"]["columns"]["ticket_id"]
    id_col = id_spec.get("name_override") or next(
        (c for c in id_spec["candidates"] if c in df.columns), None)
    if not id_col:
        raise SystemExit(f"金标文件中找不到工单号列，候选 {id_spec['candidates']}")
    preds = load_results(args.results)

    boundary_pairs, missing, diff_rows = [], 0, []
    per_dim = {k: [] for k, _ in DIMS}
    for _, row in df.iterrows():
        rec = preds.get(str(row[id_col]))
        if not rec:
            missing += 1
            continue
        row_diffs = []
        for key, pred_field in DIMS:
            g, p = norm(row[gold_cols[key]]), norm(rec.get(pred_field))
            if g is not None:  # 对照标签为空的维度不计入
                per_dim[key].append((g, p or "（null）"))
                if g != (p or "（null）"):
                    row_diffs.append(pred_field)
        boundary_pairs.append((bool(rec.get("边界")), not row_diffs))
        if row_diffs:
            d = {id_col: row[id_col], "分歧维度": ",".join(row_diffs)}
            for key, pf in DIMS:
                d[f"{pf}-对照"] = norm(row[gold_cols[key]]) or ""
                d[f"{pf}-本系统"] = norm(rec.get(pf)) or ""
            d["本系统依据"] = rec.get("依据", "")
            d["边界"] = "是" if rec.get("边界") else ""
            d["裁决结果"], d["裁决备注"] = "", ""  # 人工填：对照对/本系统对/都不对/spec歧义
            diff_rows.append(d)

    if getattr(args, "dump_diff", None) and diff_rows:
        # 拼回工单原文列（若对照文件里有），裁决时不用来回翻表
        text_cols = [c for c in ("标题", "事件标题", "问题描述", "事件描述",
                                 "解决方案", "处理方案") if c in df.columns]
        diff_df = pd.DataFrame(diff_rows).merge(
            df[[id_col] + text_cols], on=id_col, how="left")
        diff_df.to_excel(args.dump_diff, index=False)
        print(f"分歧清单 {len(diff_rows)} 条已导出 → {args.dump_diff}"
              f"（逐条填[裁决结果]列；裁决对分歧标签时建议遮住来源做盲审）")

    print(f"金标 {len(df)} 条，其中 {missing} 条无预测结果（未跑或失败）")
    for key, field in DIMS:
        confusion_report(per_dim[key], field)

    # 边界字段有效性：边界=true 的错误率应显著高于 false，否则该字段没起到复核导流作用
    for flag in (True, False):
        subset = [ok for b, ok in boundary_pairs if b == flag]
        if subset:
            err = 1 - sum(subset) / len(subset)
            print(f"\n边界={flag}：{len(subset)} 条，整单错误率 {err:.1%}")
    caught = sum(1 for b, ok in boundary_pairs if b and not ok)
    all_err = sum(1 for _, ok in boundary_pairs if not ok)
    if all_err:
        print(f"边界标记召回：全部 {all_err} 条错单中被标为边界的 {caught} 条 ({caught / all_err:.1%})"
              f" —— 偏低则收紧 spec 第〇章 0.3 的边界触发条件")


def cmd_agree(args, cfg):
    a, b = load_results(args.a), load_results(args.b)
    common = sorted(set(a) & set(b))
    if not common:
        raise SystemExit("两份结果无共同工单号")
    diff_ids = []
    for tid in common:
        if any(norm(a[tid].get(f)) != norm(b[tid].get(f)) for _, f in DIMS):
            diff_ids.append(tid)
    rate = 1 - len(diff_ids) / len(common)
    print(f"共同 {len(common)} 条，一致率 {rate:.1%}，不一致 {len(diff_ids)} 条")
    for tid in diff_ids[:20]:
        diffs = [(f, norm(a[tid].get(f)), norm(b[tid].get(f)))
                 for _, f in DIMS if norm(a[tid].get(f)) != norm(b[tid].get(f))]
        print(f"  {tid}: {diffs}")
    if diff_ids:
        print("不一致条目通常意味着 spec 判据存在歧义 —— 优先修订 spec.md 对应段落，而非调 prompt 技巧")


def main():
    p = argparse.ArgumentParser(description="MetaERP 分类效果评测")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("sample")
    sp.add_argument("--gold", required=True, help="含人工金标列的 Excel")
    sp.add_argument("--dev-frac", type=float, default=0.08)
    sp.add_argument("--test-frac", type=float, default=0.06)
    sp.add_argument("--out-dev", default="data/interim/dev.xlsx")
    sp.add_argument("--out-test", default="data/interim/test.xlsx")

    sp = sub.add_parser("score")
    sp.add_argument("--gold", required=True,
                    help="含对照标签列的 Excel（真金标，或产品经理等另一系统的标签）")
    sp.add_argument("--results", required=True, help="classify.py 产出的 results.jsonl")
    sp.add_argument("--dump-diff", default=None,
                    help="导出分歧清单 Excel（含双方标签+本系统依据+空白裁决列），供人工逐条裁决")

    sp = sub.add_parser("agree")
    sp.add_argument("--a", required=True)
    sp.add_argument("--b", required=True)

    args = p.parse_args()
    cfg = load_config()
    {"sample": cmd_sample, "score": cmd_score, "agree": cmd_agree}[args.cmd](args, cfg)


if __name__ == "__main__":
    main()
