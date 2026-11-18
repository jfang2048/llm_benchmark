"""Join Home Lab runs measured with one protocol on the same machine."""
import argparse
import json
import shutil
import tempfile
from pathlib import Path

from .home_report import load_fit, read_run

MODEL_SETTINGS = ("cohorts", "disable_reasoning_for")


def protocol(manifest):
    return {key: value for key, value in manifest["settings"].items() if key not in MODEL_SETTINGS}


def merge_runs(runs, output):
    if len(runs) < 2:
        raise ValueError("supply at least two source runs")
    if output.exists():
        raise ValueError("output must be a new directory")

    base, *_ = read_run(runs[0])
    settings = dict(base["settings"])
    models, arms, provenance = [], set(), []
    headers, files, storage = None, [], None
    fit_metadata, fit_rows = None, []
    fields = ("tasks_sha256", "gpu", "platform")
    for path in runs:
        manifest = base if path == runs[0] else read_run(path)[0]
        if protocol(manifest) != protocol(base) or any(manifest[k] != base[k] for k in fields):
            raise ValueError("run uses a different protocol, fixture set, or hardware environment")
        new = {m["arm"] for m in manifest["arms"]}
        if arms & new:
            raise ValueError(f"duplicate deployments: {', '.join(sorted(arms & new))}")
        arms.update(new)
        models.extend(manifest["arms"])
        provenance.extend(manifest.get("source_runs") or [{
            "source_commit": manifest["source_commit"],
            "settings_sha256": manifest["settings_sha256"],
            "arms": sorted(new),
        }])
        for key in MODEL_SETTINGS:
            settings[key] = list(dict.fromkeys(settings[key] + manifest["settings"][key]))

        path_rows = path / "requests.tsv"
        with path_rows.open(encoding="utf-8", newline="") as stream:
            header = stream.readline()
        if headers is not None and header != headers:
            raise ValueError("request files use different headers")
        headers = header
        files.append(path_rows)
        probe = path / "storage.json"
        if probe.exists():
            if storage is not None and probe.read_bytes() != storage.read_bytes():
                raise ValueError("runs contain different storage probes")
            storage = probe
        fit_path = path / "fit.json"
        if fit_path.exists():
            fit = json.loads(fit_path.read_text(encoding="utf-8"))
            rows = fit.pop("rows")
            if fit_metadata is not None and fit != fit_metadata:
                raise ValueError("context probes use different settings")
            fit_metadata = fit
            fit_rows.extend(rows)

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        stage = Path(temporary) / "run"
        stage.mkdir()
        shutil.copyfile(runs[0] / "tasks.jsonl", stage / "tasks.jsonl")
        if storage:
            shutil.copyfile(storage, stage / "storage.json")
        with (stage / "requests.tsv").open("w", encoding="utf-8", newline="") as target:
            target.write(headers)
            for file in files:
                with file.open(encoding="utf-8", newline="") as source:
                    source.readline()
                    shutil.copyfileobj(source, target)
        combined = {key: base[key] for key in fields}
        combined.update(settings=settings, arms=models, source_runs=provenance)
        (stage / "manifest.json").write_text(json.dumps(combined, indent=2) + "\n", encoding="utf-8")
        read_run(stage)
        if fit_metadata is not None:
            fit = dict(fit_metadata, rows=fit_rows)
            fit_path = stage / "fit.json"
            fit_path.write_text(json.dumps(fit, indent=2) + "\n", encoding="utf-8")
            load_fit(fit_path, combined)
        stage.rename(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("runs", nargs="+", type=Path)
    args = parser.parse_args()
    try:
        merge_runs(args.runs, args.output)
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
