"""Delete case data (src/retention.py).

  python -m scripts.purge_cases --case SF-482-735 --reason "taxpayer asked"
  python -m scripts.purge_cases --expired                   # cases idle > 30 days, stale uploads
  python -m scripts.purge_cases --expired --older-than-days 7 --dry-run

Run --dry-run first: it lists what would go and deletes nothing. Schedule --expired (cron, Task
Scheduler or a container job) to apply the retention policy.
"""
import argparse
import sys

from src.retention import (DEFAULT_RETENTION_DAYS, STALE_UPLOAD_HOURS, Layout, purge_case, purge_expired,
                           purge_stale_uploads)


def show(result: dict, dry_run: bool) -> None:
    if "skipped" in result:
        print(f"{result['case_id']}: skipped ({result['skipped']})")
        return
    removed = ", ".join(f"{n} {what.replace('_', ' ')}" for what, n in result["removed"].items() if n)
    print(f"{result['case_id']}: {'would remove' if dry_run else 'removed'} {removed or 'nothing'}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    what = parser.add_mutually_exclusive_group(required=True)
    what.add_argument("--case", help="delete this one case")
    what.add_argument("--expired", action="store_true", help="delete idle cases and stale uploads")
    parser.add_argument("--older-than-days", type=float, default=DEFAULT_RETENTION_DAYS)
    parser.add_argument("--uploads-older-than-hours", type=float, default=STALE_UPLOAD_HOURS)
    parser.add_argument("--reason", default="requested", help="recorded in the audit log")
    parser.add_argument("--actor", default="system:retention", help="who is deleting, for the audit log")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--runtime", default="runtime")
    parser.add_argument("--trace-dir", action="append", help="repeatable; default runtime/traces and traces")
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args(argv)

    layout = Layout(args.runtime, args.trace_dir, args.output_dir)
    try:
        if args.case:
            show(purge_case(args.case, layout, actor=args.actor, reason=args.reason, dry_run=args.dry_run),
                 args.dry_run)
        else:
            for result in purge_expired(layout, max_age_days=args.older_than_days, actor=args.actor,
                                        dry_run=args.dry_run):
                show(result, args.dry_run)
            uploads = purge_stale_uploads(layout, max_age_hours=args.uploads_older_than_hours,
                                          dry_run=args.dry_run)
            print(f"stale uploads: {'would remove' if args.dry_run else 'removed'} {uploads}")
    except ValueError as problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
