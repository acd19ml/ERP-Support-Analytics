# -*- coding: utf-8 -*-
"""
桑基图生成 v3：专题 → L1 → 解决方案

已内置四个历史坑的处理：
1. 节点按名称去重（同名合并为一个节点，避免 dataIndex 索引错乱）
2. 过滤 source==target 自环流
3. link 的 source/target 一律对齐去重后的节点名（不悬空）
4. 独立 HTML 输出，不在 shell 内联代码（PowerShell 安全）

IT/外部类五专题无 L1/解决方案，作为一级端点直接展示（不产生后续流）。
"""
import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd
import yaml

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"

HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>html,body{{margin:0;height:100%;}}#c{{width:100%;height:100%;}}</style></head>
<body><div id="c"></div>
<script>
var chart = echarts.init(document.getElementById('c'));
chart.setOption({{
  title: {{text: '{title}', left: 'center', textStyle: {{fontSize: {font_title}}}}},
  tooltip: {{trigger: 'item', triggerOn: 'mousemove'}},
  series: [{{
    type: 'sankey',
    left: {left}, right: {right}, top: 80, bottom: 40,
    nodeWidth: {node_width},
    emphasis: {{focus: 'adjacency'}},
    data: {nodes},
    links: {links},
    label: {{fontSize: {font_node}}},
    lineStyle: {{color: 'gradient', curveness: 0.5}}
  }}]
}});
window.addEventListener('resize', function(){{chart.resize();}});
</script></body></html>
"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="已分类的 Excel（finalize 输出）")
    p.add_argument("--output", required=True, help="输出 HTML 路径")
    p.add_argument("--title", default="MetaERP 用户事件工单分类流向")
    args = p.parse_args()

    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    out_cols = cfg["excel"]["out_columns"]
    sk = cfg["sankey"]

    df = pd.read_excel(args.input, dtype=str).fillna("")

    def norm(v):
        v = str(v).strip()
        return v if v and v not in ("nan", "None", "null", "--") else None

    flows = Counter()
    node_names = []  # 保序去重
    seen = set()

    def add_node(name):
        if name not in seen:
            seen.add(name)
            node_names.append(name)

    for _, row in df.iterrows():
        topic = norm(row.get(out_cols["topic"]))
        if not topic:
            continue
        add_node(topic)
        l1 = norm(row.get(out_cols["l1"]))
        sol = norm(row.get(out_cols["solution_class"]))
        if l1:
            add_node(l1)
            if topic != l1:  # 坑2：过滤自环
                flows[(topic, l1)] += 1
            if sol:
                add_node(sol)
                if l1 != sol:
                    flows[(l1, sol)] += 1

    nodes = [{"name": n} for n in node_names]  # 坑1：唯一名称即唯一节点
    links = [{"source": s, "target": t, "value": v}
             for (s, t), v in flows.items()
             if s in seen and t in seen]  # 坑3：不悬空

    html = HTML_TEMPLATE.format(
        title=args.title, left=sk["left"], right=sk["right"],
        node_width=sk["node_width"], font_node=sk["font_size_node"],
        font_title=sk["font_size_title"],
        nodes=json.dumps(nodes, ensure_ascii=False),
        links=json.dumps(links, ensure_ascii=False))
    Path(args.output).write_text(html, encoding="utf-8")
    print(f"桑基图已生成：{args.output}（{len(nodes)} 节点，{len(links)} 流），浏览器打开即可")


if __name__ == "__main__":
    main()
