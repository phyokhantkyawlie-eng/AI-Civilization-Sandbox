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
    if metric not in frame:
        unavailable(ax,title+'\nUnavailable in this export')
        return
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
    # Compare memory only within the explicitly paired memory scenario when a
    # release suite contains other scenarios/profiles with different conditions.
    memory = completed
    if 'scenario' in completed and (completed.scenario=='social_memory').any():
        memory = completed.loc[completed.scenario=='social_memory'].copy()
    pages = {}
    fig, ax = plt.subplots(figsize=(9, 5), layout="constrained")
    comparison(ax, memory, "cooperation_rate", "Cooperation per trial · points, mean and ±1 sample SD", "shares / (shares + refusals)")
    pages["cooperation"] = fig
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), layout="constrained")
    for ax, metric in zip(axes, ("shares", "refusals")):
        comparison(ax, memory, metric, metric.title()+" · per-trial counts", "events / trial")
    pages["sharing_refusals"] = fig
    fig, ax = plt.subplots(figsize=(9, 5), layout="constrained")
    comparison(ax, completed, "survival_rate", "Survival comparison", "fraction of initial NPCs")
    pages["survival"] = fig
    fig, ax = plt.subplots(figsize=(10, 5), layout="constrained")
    plotted = False
    for i, mode in enumerate(MODES):
        trajectories = []
        for _, trial in memory.loc[memory.condition == mode].iterrows():
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
    for _, row in memory.iterrows():
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
    columns = ["seed","scenario","profile","condition","provider","requests","shares","refusals",
               "cooperation_rate","average_hunger","average_energy","invalid_actions","gemini_calls"]
    table = frame.head(20).reindex(columns=columns).copy()
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
    ax.set_title(f"{len(frame)} trials · {sum(frame.status == 'completed')} completed · first {min(20,len(frame))} shown\n"
                 "Full CSV/JSON retains every trial. SD bars describe variation, not confidence intervals.")
    pages["trial_summary"] = fig
    pages.update(evaluation_figures(completed,memory))
    return pages


def labeled_groups(frame):
    copy = frame.copy()
    scenario = copy['scenario'].fillna('food_shortage') if 'scenario' in copy else pd.Series('food_shortage',index=copy.index)
    profile = copy['profile'].fillna('baseline') if 'profile' in copy else pd.Series('baseline',index=copy.index)
    copy['group'] = scenario.str.replace('_',' ')+profile.map(lambda p:'' if p=='baseline' else ' / '+p.replace('_',' '))+' / '+copy.condition.str.replace('MEMORY_','')
    if 'simulation_seconds' in copy:
        copy['group'] += copy.simulation_seconds.map(lambda v:f' ({v:g}s)' if pd.notna(v) else '')
    return copy


def group_comparison(ax, frame, metric, title, unit):
    ax.set_title(title)
    if metric not in frame:
        unavailable(ax,'Unavailable in this export')
        return
    data = labeled_groups(frame)
    data[metric] = pd.to_numeric(data[metric],errors='coerce')
    groups = [(label,part[metric].dropna()) for label,part in data.groupby('group',sort=False)]
    groups = [(label,values) for label,values in groups if len(values)]
    if not groups:
        unavailable(ax,'Unavailable: no measured values')
        return
    for i,(label,values) in enumerate(groups):
        ax.scatter(values,[i]*len(values),alpha=.55,s=19,color='#498b85')
        ax.plot([values.mean()]*2,[i-.17,i+.17],color='black')
        if len(values)>1:
            ax.errorbar(values.mean(),i,xerr=values.std(ddof=1),fmt='none',color='black',capsize=3)
    ax.set_yticks(range(len(groups)),[textwrap.fill(label,32) for label,_ in groups],fontsize=8)
    ax.set_xlabel(unit+' · points, mean and ±1 sample SD')
    ax.grid(axis='x',alpha=.2)


def evaluation_figures(completed,memory):
    import matplotlib.pyplot as plt
    pages = {}
    fig,axes = plt.subplots(1,2,figsize=(14,7),layout='constrained')
    unavailable(axes[0],'NPC mortality survival: unavailable.\nThe game has no permanent death mechanic.\nA constant 100% would not measure survival.')
    group_comparison(axes[1],completed,'operational_availability','Operational availability (a survival proxy)','fraction of NPC-ticks not incapacitated')
    pages['survival_across_scenarios'] = fig
    fig,axes = plt.subplots(1,2,figsize=(15,7),layout='constrained')
    choices = completed.copy()
    seconds = pd.to_numeric(choices.get('simulation_seconds',pd.Series(index=choices.index,dtype=float)),errors='coerce').replace(0,float('nan'))
    for ax,metric,title in zip(axes,('gathering_decisions','hunting_decisions'),('Gathering goal selection rate','Hunting goal selection rate')):
        if metric in choices:
            choices[metric+'_rate'] = pd.to_numeric(choices[metric],errors='coerce')*60/seconds
        group_comparison(ax,choices,metric+'_rate',title,'goals / simulated minute')
    pages['gathering_hunting_choices'] = fig
    fig,axes = plt.subplots(1,2,figsize=(15,7),layout='constrained')
    meals = completed.copy()
    meals['meal_count'] = meals.get('meals_consumed',pd.Series(index=meals.index,dtype=object)).map(lambda v:sum(v.values()) if isinstance(v,dict) else float('nan'))
    seconds = pd.to_numeric(meals.get('simulation_seconds',pd.Series(index=meals.index,dtype=float)),errors='coerce').replace(0,float('nan'))
    if 'cooking_completions' in meals:
        meals['cooking_rate'] = pd.to_numeric(meals.cooking_completions,errors='coerce')*60/seconds
    meals['meal_rate'] = meals.meal_count*60/seconds
    group_comparison(axes[0],meals,'cooking_rate','Completed cooking rate','conversions / simulated minute')
    group_comparison(axes[1],meals,'meal_rate','Meal consumption rate','items / simulated minute')
    pages['cooking_consumption'] = fig
    fig,axes = plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for ax,metric,title in zip(axes,('average_hunger','average_energy'),('Memory comparison: average hunger','Memory comparison: average energy')):
        comparison(ax,memory,metric,title,'NPC-tick average (0–100)')
    pages['memory_comparison'] = fig
    fig,axes = plt.subplots(1,2,figsize=(14,6),layout='constrained')
    data = labeled_groups(completed)
    for ax,metric,title,unit in zip(axes,('wild_berries','carried_edible_items'),('Wild berry availability','Carried edible food'),('berries in bushes','berries + cooked meals (items)')):
        plotted = False
        for label,group in data.groupby('group',sort=False):
            # Hunting profiles have their own goal chart; keep resource curves
            # readable rather than pooling their unequal initial inventories.
            if 'scenario' in group and (group.scenario=='hunting_decisions').all():
                continue
            trajectories = []
            for _,row in group.iterrows():
                series = row.get('state_series')
                if isinstance(series,list) and series:
                    table = pd.DataFrame(series)
                    if metric in table:
                        trajectories.append(table.set_index('tick')[metric])
            if trajectories:
                plotted = True
                table = pd.concat(trajectories,axis=1)
                mean,sd = table.mean(axis=1),table.std(axis=1)
                line, = ax.plot(mean.index*.25,mean,label=label)
                if len(trajectories)>1:
                    ax.fill_between(mean.index*.25,mean-sd,mean+sd,color=line.get_color(),alpha=.12)
        ax.set(title=title,xlabel='Simulation seconds',ylabel=unit)
        if plotted:
            ax.legend(fontsize=7)
            ax.grid(alpha=.2)
        else:
            unavailable(ax,'Trajectory unavailable for these exports/profiles')
    fig.suptitle('Food availability · means with ±1 sample SD across seeds')
    pages['food_availability_over_time'] = fig
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
