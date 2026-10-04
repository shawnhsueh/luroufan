"""Step 2: rate each restaurant's 滷肉飯 from its Google reviews with Claude.

Places whose reviews mention 滷肉飯/魯肉飯/肉燥飯 are sent to Claude with structured
outputs. By default the run uses the Message Batches API (half price, usually done
within an hour); --sync sends requests one at a time.
"""

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from typing import Literal

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request
from pydantic import BaseModel, Field, ValidationError

from . import config


class Rating(BaseModel):
    mentions: int = Field(description="Number of reviews that actually talk about this shop's 滷肉飯")
    score: float | None = Field(
        description="How good the 滷肉飯 is by these reviews, 1.0-5.0 (one decimal). "
        "Null if no review judges its taste."
    )
    summary: str | None = Field(description="What reviewers say about the 滷肉飯, Traditional Chinese, at most 30 characters")
    price: int | None = Field(description="À-la-carte 滷肉飯 price in NTD stated in a review (smallest bowl); null if none")
    price_date: str | None = Field(description="Date (YYYY-MM-DD) of the review the price came from")
    latest_mention: str | None = Field(description="Date (YYYY-MM-DD) of the most recent review that mentions the 滷肉飯")
    confidence: Literal["high", "medium", "low"]
    notes: str | None = Field(description="Anything a reviewer of this data should know, in Traditional Chinese")


SYSTEM = """You rate braised pork rice (滷肉飯) at restaurants in Taipei, Taiwan, from Google reviews, for a map.

What counts: rice topped with braised minced/diced pork in soy sauce, sold as 滷肉飯, 魯肉飯 or 肉燥飯. \
Not 爌肉飯/控肉飯 (slab pork belly), 雞肉飯, 豬腳飯, 排骨飯, or 滷肉 served without rice.

You get up to 5 reviews, each with its star rating and date.
- mentions: how many reviews say something about this shop's 滷肉飯.
- score (1.0-5.0): judge only what reviewers say about the 滷肉飯 itself (taste, sauce, fat/lean balance, \
rice, portion), not service, wait times, or other dishes. A review's star rating only counts when the \
review is mainly about the 滷肉飯. Weigh recent reviews more than old ones. If the reviews only list the \
dish without judging it (e.g. 「點了滷肉飯和湯」), score is null. Never guess.
- summary: a short, neutral Traditional Chinese phrase of what reviewers say, e.g. 「滷汁香濃、肥瘦適中，偏甜」. \
Don't quote reviewers word for word.
- price: only an à-la-carte 滷肉飯 price a reviewer states (smallest bowl if several), never a 套餐/便當 price. \
Give the date of that review in price_date.
- confidence: "low" for a single mention or conflicting reviews, "medium" for two consistent mentions, \
"high" for three or more consistent mentions."""

DISH = re.compile(config.DISH_PATTERN, re.I)


def build_content(place: dict, reviews: list[dict]) -> tuple[list[dict], str] | None:
    """Return (message content blocks, content hash), or None if no review mentions the dish."""
    if not any(DISH.search(r["text"]) for r in reviews):
        return None
    parts = [
        f"<review index=\"{i}\" stars=\"{r.get('rating')}\" date=\"{(r.get('publish_time') or '')[:10]}\">\n"
        f"{r['text']}\n</review>"
        for i, r in enumerate(reviews, 1)
    ]
    intro = f"Restaurant: {place['name']}\nAddress: {place['address']}\n\n"
    blocks = [{"type": "text", "text": intro + "\n\n".join(parts)}]
    digest = hashlib.sha256(json.dumps(blocks, sort_keys=True).encode()).hexdigest()[:16]
    return blocks, digest


def params(content: list[dict]) -> dict:
    return {
        "model": config.MODEL,
        "max_tokens": 4000,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": content}],
    }


def record(place_id: str, digest: str, extraction: Rating | None, status: str, error: str | None = None) -> dict:
    row = {
        "place_id": place_id,
        "content_hash": digest,
        "status": status,
        "model": config.MODEL,
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if extraction:
        row.update(extraction.model_dump())
    if error:
        row["error"] = error
    return row


def extract_sync(client: anthropic.Anthropic, place_id: str, content: list[dict], digest: str) -> dict:
    try:
        resp = client.beta.messages.parse(
            **params(content),
            output_format=Rating,
            output_config={"effort": "low"},
            betas=[config.FALLBACK_BETA],
            fallbacks="default",
        )
    except anthropic.BadRequestError as e:
        return record(place_id, digest, None, "error", f"bad request: {e.message}"[:300])
    except anthropic.APIStatusError as e:
        return record(place_id, digest, None, "error", f"{e.status_code}: {e.message}"[:300])
    if resp.stop_reason == "refusal":
        return record(place_id, digest, None, "refused")
    if resp.stop_reason == "max_tokens" or resp.parsed_output is None:
        return record(place_id, digest, None, "error", f"no parsed output (stop_reason={resp.stop_reason})")
    return record(place_id, digest, resp.parsed_output, "ok")


def submit_batch(client: anthropic.Anthropic, jobs: dict[str, tuple[list[dict], str]]) -> str:
    # Server-side fallbacks aren't accepted by the Batches API; refusals are retried with --sync below.
    requests = [
        Request(
            custom_id=place_id,
            params=MessageCreateParamsNonStreaming(
                **params(content),
                output_config={
                    "effort": "low",
                    "format": {"type": "json_schema", "schema": anthropic.transform_schema(Rating)},
                },
            ),
        )
        for place_id, (content, _) in jobs.items()
    ]
    batch = client.messages.batches.create(requests=requests)
    config.BATCH_STATE_FILE.write_text(
        json.dumps({"batch_id": batch.id, "hashes": {pid: d for pid, (_, d) in jobs.items()}})
    )
    print(f"Submitted batch {batch.id} with {len(requests)} requests")
    return batch.id


def collect_batch(client: anthropic.Anthropic, batch_id: str, hashes: dict[str, str]) -> list[dict]:
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            break
        c = batch.request_counts
        print(f"  batch {batch.processing_status}: {c.processing} processing, {c.succeeded} done")
        time.sleep(60)
    rows = []
    for result in client.messages.batches.results(batch_id):
        pid, digest = result.custom_id, hashes[result.custom_id]
        if result.result.type != "succeeded":
            rows.append(record(pid, digest, None, "error", f"batch result {result.result.type}"))
            continue
        msg = result.result.message
        if msg.stop_reason == "refusal":
            rows.append(record(pid, digest, None, "refused"))
            continue
        text = next((b.text for b in msg.content if b.type == "text"), "")
        try:
            rows.append(record(pid, digest, Rating.model_validate_json(text), "ok"))
        except ValidationError as e:
            rows.append(record(pid, digest, None, "error", f"invalid JSON: {e}"[:300]))
    config.BATCH_STATE_FILE.unlink(missing_ok=True)
    return rows


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sync", action="store_true", help="send requests one at a time instead of as a batch")
    parser.add_argument("--limit", type=int, help="only process the first N candidates")
    parser.add_argument("--force", action="store_true", help="re-rate even if the reviews are unchanged")
    parser.add_argument("--dry-run", action="store_true", help="show what would be sent, without calling Claude")
    args = parser.parse_args(argv)

    places = {r["place_id"]: r for r in config.read_jsonl(config.RESTAURANTS_FILE)}
    reviews = config.read_jsonl(config.REVIEWS_FILE)
    ratings = {p["place_id"]: p for p in config.read_jsonl(config.RATINGS_FILE)}

    jobs: dict[str, tuple[list[dict], str]] = {}
    for r in reviews:
        if r["place_id"] not in places:
            continue
        built = build_content(places[r["place_id"]], r["reviews"])
        if not built:
            continue
        prev = ratings.get(r["place_id"])
        if not args.force and prev and prev["content_hash"] == built[1] and prev["status"] == "ok":
            continue
        jobs[r["place_id"]] = built
    if args.limit:
        jobs = dict(list(jobs.items())[: args.limit])

    if args.dry_run:
        chars = sum(len(json.dumps(c, ensure_ascii=False)) for c, _ in jobs.values())
        print(f"{len(jobs)} restaurants to rate, ~{chars:,} input tokens (rough; ~1 per Chinese character)")
        for pid, (content, _) in list(jobs.items())[:3]:
            print(f"--- {places[pid]['name']}\n{content[-1]['text'][:1500]}\n")
        return

    client = anthropic.Anthropic(api_key=config.require_env("ANTHROPIC_API_KEY"))

    # Resume a batch left over from an interrupted run.
    if config.BATCH_STATE_FILE.exists():
        state = json.loads(config.BATCH_STATE_FILE.read_text())
        print(f"Resuming batch {state['batch_id']}")
        new_rows = collect_batch(client, state["batch_id"], state["hashes"])
    elif not jobs:
        print("Nothing to rate: every candidate's reviews are unchanged since the last run.")
        return
    elif args.sync:
        new_rows = []
        for i, (pid, (content, digest)) in enumerate(jobs.items(), 1):
            row = extract_sync(client, pid, content, digest)
            print(f"[{i}/{len(jobs)}] {places[pid]['name']}: {row['status']} {row.get('score')} {row.get('summary') or ''}")
            new_rows.append(row)
    else:
        batch_id = submit_batch(client, jobs)
        hashes = {pid: d for pid, (_, d) in jobs.items()}
        new_rows = collect_batch(client, batch_id, hashes)

    # Refusals and errors from the batch get one more try with server-side fallbacks.
    retry_ids = [r["place_id"] for r in new_rows if r["status"] in ("refused", "error") and r["place_id"] in jobs]
    if retry_ids and not args.sync:
        print(f"Retrying {len(retry_ids)} failed requests one at a time")
        by_id = {r["place_id"]: r for r in new_rows}
        for pid in retry_ids:
            content, digest = jobs[pid]
            by_id[pid] = extract_sync(client, pid, content, digest)
        new_rows = list(by_id.values())

    for row in new_rows:
        ratings[row["place_id"]] = row
    config.write_jsonl(config.RATINGS_FILE, sorted(ratings.values(), key=lambda r: r["place_id"]))
    ok = [r for r in new_rows if r["status"] == "ok"]
    scored = [r for r in ok if r.get("score") is not None]
    print(f"Rated {len(new_rows)}: {len(ok)} ok, {len(scored)} with a score -> {config.RATINGS_FILE}")


if __name__ == "__main__":
    main()
