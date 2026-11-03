"""Pandas/Matplotlib viewer for genuine saved experiment outputs."""
import argparse
import json
from pathlib import Path
from .characters import CHARACTERS
import textwrap

import pandas as pd

MODES = ("MEMORY_OFF", "MEMORY_ON")
COLORS = ("#b96f55", "#498b85")


def load_result(path):
    path = Path(path)
    payload = json.loads((path/"summary.json").read_text())
    if not isinstance(payload.get("trials"), list):
        raise ValueError("Missing trial rows")
    if not payload["trials"]:
        raise ValueError("No trials recorded in this experiment")
    return payload, pd.DataFrame(payload["trials"])


def unavailable(ax, message):
    ax.text(.5, .5, message, ha="center", va="center", transform=ax.transAxes, wrap=True)
    ax.set_axis_off()


def comparison(ax, frame, metric, title, unit):
    ax.set_title(title)
    available = False
    for i, mode in enumerate(MODES):
        values = pd.to_numeric(frame.loc[frame.condition == mode, metric], errors="coerce").dropna()
        if len(values):
            available = True
            ax.scatter([i]*len(values), values, color=COLORS[i], alpha=.65)
            ax.plot([i-.16, i+.16], [values.mean()]*2, color="black", linewidth=2)
            if len(values) >= 2:
                ax.errorbar(i, values.mean(), yerr=values.std(ddof=1), color="black", capsize=5)
    if not available:
        unavailable(ax, title+"\nUnavailable in this simulation")
    else:
        ax.set_xticks([0, 1], ["Memory OFF", "Memory ON"])
        ax.set_ylabel(unit)
        ax.grid(axis="y", alpha=.2)


def figures(payload, frame):
    import matplotlib.pyplot as plt
    for column in ("cooperation_rate", "shares", "refusals", "survival_rate"):
        if column not in frame:
            frame[column] = float("nan")
    completed = frame.loc[frame.status == "completed"].copy()
    pages = {}
    fig, ax = plt.subplots(figsize=(9, 5), layout="constrained")
    comparison(ax, completed, "cooperation_rate", "Cooperation per trial · points, mean and ±1 sample SD", "shares / (shares + refusals)")
    pages["cooperation"] = fig
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), layout="constrained")
    for ax, metric in zip(axes, ("shares", "refusals")):
        comparison(ax, completed, metric, metric.title()+" · per-trial counts", "events / trial")
    pages["sharing_refusals"] = fig
    fig, ax = plt.subplots(figsize=(9, 5), layout="constrained")
    comparison(ax, completed, "survival_rate", "Survival comparison", "fraction of initial NPCs")
    pages["survival"] = fig
    fig, ax = plt.subplots(figsize=(10, 5), layout="constrained")
    plotted = False
    for i, mode in enumerate(MODES):
        trajectories = []
        for _, trial in completed.loc[completed.condition == mode].iterrows():
            series = trial.get("hunger_series")
            if isinstance(series, list) and series:
                data = pd.DataFrame(series).set_index("tick")["mean_hunger"]
                trajectories.append(data)
                ax.plot(data.index, data, color=COLORS[i], alpha=.25, linewidth=.7)
        if trajectories:
            plotted = True
            table = pd.concat(trajectories, axis=1)
            mean, sd = table.mean(axis=1), table.std(axis=1)
            ax.plot(mean.index, mean, color=COLORS[i], label=mode)
            if len(trajectories) > 1:
                ax.fill_between(mean.index, mean-sd, mean+sd, color=COLORS[i], alpha=.15)
    if plotted:
        ax.set(xlabel="Simulation tick (0.25 simulated seconds)", ylabel="Mean NPC hunger (0–100)",
               title="Hunger trajectories · thin lines per trial, bands ±1 sample SD")
        ax.legend()
    else:
        unavailable(ax, "Hunger over time unavailable in this older export.\nThe scalar trial average cannot reconstruct a trajectory.")
    pages["hunger_over_time"] = fig
    fig, ax = plt.subplots(figsize=(11, 6), layout="constrained")
    records = []
    for _, row in completed.iterrows():
        trust = row.get("final_trust")
        if isinstance(trust, dict):
            for actor, targets in trust.items():
                for target, value in targets.items():
                    records.append({"condition": row.condition, "edge": CHARACTERS.get(actor, (actor, ""))[0]+" → "+CHARACTERS.get(target, (target, ""))[0], "value": value})
    if records:
        trust_frame = pd.DataFrame(records)
        table = trust_frame.pivot_table(index="edge", columns="condition", values="value", aggfunc="mean").reindex(columns=MODES)
        for i, mode in enumerate(MODES):
            values = table[mode]
            ax.barh([x+i*.35 for x in range(len(table))], values, height=.35, color=COLORS[i], label=mode)
            sd = trust_frame[trust_frame.condition == mode].groupby("edge").value.std().reindex(table.index)
            if sd.notna().any():
                ax.errorbar(values, [x+i*.35 for x in range(len(table))], xerr=sd.fillna(0), fmt="none", color="black")
        ax.set_yticks([x+.175 for x in range(len(table))], table.index)
        ax.set(xlabel="Directed trust change from neutral zero · mean ±1 sample SD", title="Relationship changes")
        ax.legend()
    else:
        unavailable(ax, "Directed trust unavailable")
    pages["trust_changes"] = fig
    fig, ax = plt.subplots(figsize=(13, 7), layout="constrained")
    ax.axis("off")
    columns = ["seed", "condition", "provider", "model", "requests", "shares", "refusals",
               "cooperation_rate", "survival_rate", "average_hunger", "invalid_actions",
               "gemini_calls", "fallback_count"]
    table = frame.reindex(columns=columns).copy()
    def cell(value):
        if pd.isna(value):
            return "Unavailable"
        if isinstance(value, float):
            return f"{value:.3g}"
        return str(value)[:22]
    table = table.map(cell)
    labels = [column.replace("_", "\n") for column in table.columns]
    artist = ax.table(cellText=table.values, colLabels=labels, loc="center", cellLoc="center")
    artist.auto_set_font_size(False)
    artist.set_fontsize(7)
    artist.scale(1, 2.2)
    ax.set_title(f"{len(frame)} trials · {sum(frame.status == 'completed')} completed\n"
                 "Small samples are descriptive. SD bars describe variation, not confidence intervals.")
    pages["trial_summary"] = fig
    return pages


def render(path, show=False):
    import matplotlib.pyplot as plt
    payload, frame = load_result(path)
    output = Path(path)/"charts"
    output.mkdir(exist_ok=True)
    pages = figures(payload, frame)
    for name, fig in pages.items():
        fig.savefig(output/(name+".png"), dpi=150)
    records = [dict(seed=r["seed"], condition=r["condition"], **decision)
               for r in payload["trials"] for decision in r.get("recent_decisions", [])]
    (output/"decisions.json").write_text(json.dumps(records, indent=2))
    pd.DataFrame(records).to_csv(output/"decisions.csv", index=False)
    if show:
        from matplotlib.widgets import Slider
        if records:
            fig, ax = plt.subplots(figsize=(12, 7))
            fig.subplots_adjust(bottom=.18)
            ax.axis("off")
            text = ax.text(0, 1, "", va="top", family="monospace", fontsize=10)
            def display(index):
                record = records[int(index)]
                content = "\n".join(f"{key}: {json.dumps(value)}" for key, value in record.items())
                text.set_text("\n".join(textwrap.fill(line, 110, replace_whitespace=False) for line in content.splitlines()))
                fig.canvas.draw_idle()
            display(0)
            if len(records) > 1:
                slider = Slider(fig.add_axes([.2, .05, .65, .03]), "Decision", 0, len(records)-1, valstep=1)
                slider.on_changed(display)
            # Keep widgets alive for the duration of the blocking viewer.
        plt.show()
    for fig in pages.values():
        plt.close(fig)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment", nargs="?", type=Path)
    parser.add_argument("--root", type=Path, default=Path("experiments"))
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()
    if args.experiment is None:
        for path in sorted(args.root.glob("*/summary.json")):
            print(path.parent)
        return 0
    try:
        print(render(args.experiment, args.show))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("Could not read results: "+type(error).__name__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
