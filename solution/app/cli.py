
import argparse
from pathlib import Path

from app.ingestion import ingest_drop
from app.reports import generate_reports


def main():
    parser = argparse.ArgumentParser(
        description="Interaction Ledger and Reporting Pipeline"
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True
    )

    # Ingest command
    ingest_parser = subparsers.add_parser(
        "ingest",
        help="Ingest a data drop"
    )
    ingest_parser.add_argument(
        "drop_path",
        help="Path to the data drop directory"
    )

    # Report command
    report_parser = subparsers.add_parser(
        "report",
        help="Generate all assignment reports"
    )
    report_parser.add_argument(
        "--out",
        default="reports/",
        help="Output directory for reports"
    )

    args = parser.parse_args()

    if args.command == "ingest":
        drop_path = Path(args.drop_path)

        if not drop_path.exists() or not drop_path.is_dir():
            parser.error(f"Invalid data drop directory: {drop_path}")

        result = ingest_drop(drop_path)
        print("Ingestion completed:")
        print(result)

    elif args.command == "report":
        result = generate_reports(args.out)
        print("Reports generated successfully:")
        print(result)


if __name__ == "__main__":
    main()
