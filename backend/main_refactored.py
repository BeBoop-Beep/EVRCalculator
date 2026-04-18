import os
import sys

base_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(base_dir)

# Keep imports stable when invoked as a script path.
if repo_root not in sys.path:
    sys.path.append(repo_root)


def _get_input_source() -> str:
    input_source = os.getenv("EVR_INPUT_SOURCE", "spreadsheet").strip().lower()
    return input_source if input_source in {"db", "spreadsheet"} else "spreadsheet"


def main() -> None:
    from backend.jobs.evr_runner import EVRRunOrchestrator

    set_name = input("What set are we working on: \n")
    try:
        orchestrator = EVRRunOrchestrator()
        orchestrator.run(
            target_set_identifier=set_name,
            input_source=_get_input_source(),
            run_metadata={"trigger": "legacy_interactive"},
        )
    except (ValueError, FileNotFoundError) as exc:
        print(exc)
        return

    print("\nOperation completed successfully!")


if __name__ == "__main__":
    main()