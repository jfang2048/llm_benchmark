"""Build fixed, disjoint Home Lab evaluation strata."""
import argparse
import hashlib
import json
import random
from itertools import product
from pathlib import Path
from urllib.request import urlopen

REVISION = "888c33f8dd94e0c503399fd478a763c772ca0d6a"
SOURCE = "https://huggingface.co/datasets/HTW-KI-Werkstatt/LlmStructBench2"
SEED = 20261119


def source_file(cache, path):
    local = cache / path.replace("/", "-")
    if not local.exists():
        with urlopen(f"{SOURCE}/resolve/{REVISION}/{path}", timeout=90) as response:
            local.write_bytes(response.read())
    return local.read_bytes()


def external_tasks(cache):
    schemas = source_file(cache, "schemas.jsonl")
    schema_rows = list(map(json.loads, schemas.splitlines()))
    tasks = []
    checksums = {"schemas.jsonl": hashlib.sha256(schemas).hexdigest()}
    for schema_row in sorted(schema_rows, key=lambda row: row["scenario"]):
        scenario = schema_row["scenario"]
        path = f"data/{scenario}.jsonl"
        raw = source_file(cache, path)
        checksums[path] = hashlib.sha256(raw).hexdigest()
        rows = list(map(json.loads, raw.splitlines()))
        schema = json.dumps(json.loads(schema_row["json_schema"]), ensure_ascii=False, separators=(",", ":"))
        used = set()
        for tier, formatting in product(("short", "mid_short"), ("clean", "messy")):
            candidates = (row for row in rows if row["length_tier"] == tier
                          and row["formatting"] == formatting and row["object_id"] not in used)
            # A fixed digest rank avoids convenience sampling or response-based selection.
            winners = sorted(candidates, key=lambda row: hashlib.sha256(
                f"{SEED}:{row['id']}".encode()).hexdigest())[:3]
            if len(winners) != 3 or len({row["object_id"] for row in winners}) != 3:
                raise ValueError(f"insufficient unique objects: {scenario}/{tier}/{formatting}")
            for row in winners:
                used.add(row["object_id"])
                email = row["email_text"]
                text = (
                    "Extract the record in the email using the JSON Schema below. "
                    "Use exact values, preserve list order, apply the schema's field formats, "
                    "and use null for absent nullable values. Return the record itself.\n"
                    f"Schema:\n{schema}\n\nEmail:\n{email}"
                )
                tasks.append({
                    "id": "lsb2-" + row["id"], "source": "llmstructbench2",
                    "kind": "extract", "language": "en", "stratum": scenario,
                    "length_tier": tier, "formatting": formatting, "object_id": row["object_id"],
                    "prompt": text, "expected": json.loads(row["ground_truth"]),
                })
    return tasks, checksums


def fresh_case(kind, lang, i, rng):
    zh = lang == "zh"
    label = f"HL-{rng.getrandbits(40):010X}"
    count, price, filler = rng.sample(range(3, 80), 3)
    date = f"2026-11-{i + 1:02d}"
    names_en = ("Mira", "Nola", "Pavel", "Idris", "Clara", "Lena", "Inez", "Hugo")
    names_zh = ("阿禾", "小舟", "阿棠", "青岚", "阿澄", "小满", "阿松", "白露")
    who = rng.choice(names_zh if zh else names_en)
    variant = i % 4
    sensitive = []
    if kind == "extract":
        if variant == 0:
            prompt = (f"{who}订了{count}张票，每张{price}欧元。另有{filler}张免费赠票。返回购买人 buyer、付费票数 paid_count 和总价 total_eur（整数）。" if zh else
                      f"{who} booked {count} tickets at {price} euros each and received {filler} free tickets. Return buyer, paid_count and integer total_eur.")
            expected = {"buyer": who, "paid_count": count, "total_eur": count * price}
        elif variant == 1:
            prompt = (f"资产清单：{label}还有{count}件，尚未归还，库位未记。返回 asset、remaining（整数）、returned（布尔）和 shelf（缺失为 null）。" if zh else
                      f"Asset log: {label} has {count} pieces left, has not been returned, and has no shelf on record. Return asset, integer remaining, Boolean returned and shelf (null when absent).")
            expected = {"asset": label, "remaining": count, "returned": False, "shelf": None}
        elif variant == 2:
            prompt = (f"{who}确认在{date}预订{count}个位置，候补还有{filler}人。返回 guest、date（原样）、confirmed（布尔）和 seats（整数）。" if zh else
                      f"{who} confirmed a booking for {count} seats on {date}. Another {filler} people are wait-listed. Return guest, date as written, Boolean confirmed and integer seats.")
            expected = {"guest": who, "date": date, "confirmed": True, "seats": count}
        else:
            prompt = (f"工单{label}记录：计划检查{count + filler}台，今天已完成{count}台，余下待查。返回 ticket、checked、open（两个整数）。" if zh else
                      f"Ticket {label}: {count + filler} devices are on the checklist; {count} have been checked so far. Return ticket, checked and open, using integers for the two counts.")
            expected = {"ticket": label, "checked": count, "open": filler}
    elif kind == "redact":
        email = label.lower() + "@example.invalid"
        phone = f"+1-202-555-01{i:02d}"
        sensitive = ([email], [phone], [label], [email, phone])[variant]
        detail = ("，".join(sensitive) if zh else ", ".join(sensitive))
        record = (f"{who}的交接记录：{detail}；箱数 {count}。" if zh else f"Handover for {who}: {detail}; boxes {count}.")
        instruction = ("只把" + ("邮箱、电话" if variant == 3 else ("邮箱", "电话", "工单号")[variant])
                       + "替换为 [MASK]，其余字符原样保留。把结果放在 text 字段。\n" if zh else
                       f"Replace only the {('email address', 'phone number', 'ticket ID', 'email address and phone number')[variant]} with [MASK]. Preserve every other character. Return the result in text.\n")
        prompt = instruction + record
        for token in sensitive:
            record = record.replace(token, "[MASK]")
        expected = {"text": record}
    else:
        keys = ("shelf", "owner", "reserved", "count")
        vals = (f"{price:02d}-{filler:02d}", who, (i // 4) % 2 == 0, count)
        answer = dict(zip(keys, vals, strict=True))
        records = {f"HL-{rng.getrandbits(40):010X}":
                   dict(shelf=f"{rng.randrange(10, 99)}-00", owner=rng.choice(names_zh if zh else names_en),
                        reserved=bool(rng.randrange(2)), count=rng.randrange(3, 99))
                   for _ in range(7 + (i % 4))}
        records[label] = answer
        order = list(records)
        rng.shuffle(order)
        rows = "\n".join(f"{key} | {json.dumps(records[key], ensure_ascii=False)}" for key in order)
        key = keys[variant]
        cue = (f"查找编号 {label} 的记录。只返回该记录的 {key} 字段，保持 JSON 类型。" if zh else
               f"Find record {label}. Return only its {key} field, preserving the JSON type.")
        prompt = f"{cue}\n\n{rows}"
        expected = {key: answer[key]}
    task = {"id": f"holdout-{kind}-{lang}-{i+1:02d}", "source": "home_holdout",
            "kind": kind, "language": lang, "stratum": f"{kind}-{lang}", "template": variant + 1,
            "prompt": prompt, "expected": expected}
    if sensitive:
        task["sensitive"] = sensitive
    return task



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path(".agent/structbench2"))
    parser.add_argument("--tasks", type=Path, default=Path("configs/fresh_tasks.jsonl"))
    parser.add_argument("--provenance", type=Path, default=Path("configs/fresh_sources.json"))
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    external, hashes = external_tasks(args.cache)
    rng = random.Random(SEED)
    synthetic = [fresh_case(kind, lang, i, rng)
                 for kind, lang, i in product(("extract", "redact", "lookup"), ("en", "zh"), range(16))]
    tasks = external + synthetic
    if len(tasks) != 192 or len({task["id"] for task in tasks}) != 192:
        raise ValueError("incorrect corpus size or duplicate task IDs")
    args.tasks.write_text("".join(json.dumps(row) + "\n" for row in tasks), encoding="utf-8")
    metadata = {
        "dataset": "LLMStructBench2 v1.0", "dataset_url": SOURCE, "revision": REVISION,
        "authors": ["Soenke Tenckhoff", "Nicklas Jones", "Mario Koddenbrock", "Erik Rodner"],
        "license": "CC BY 4.0", "published_utc": "2026-11-10",
        "source_file_sha256": hashes, "selection_seed": SEED,
        "holdout_created_local_date": "2026-11-19",
        "task_sha256": hashlib.sha256(args.tasks.read_bytes()).hexdigest(),
    }
    args.provenance.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
