# AI Usage Disclosure

## Tools used
- ChatGPT (OpenAI)

## What I used them for
- Understanding the assignment requirements and breaking the implementation into manageable modules.
- Discussing the SQLite database design, ingestion workflow, event ledger, and reporting logic.
- Getting explanations and implementation guidance for Python, SQLite, encryption, HMAC-based phone matching, and timestamp normalization.
- Debugging errors and reviewing CLI commands during development.
- Drafting and improving unit tests for phone normalization, date parsing, lead status calculation, and batch ID determinism.
- Reviewing report outputs and preparing submission documentation.

## What I wrote or decided myself
- I worked through the project implementation and integrated the modules into the final application.
- I made implementation decisions about the database structure, data normalization, duplicate handling, and report generation.
- I reviewed the generated code, adapted it to the project structure, and ran the application locally.
- I executed ingestion for both data drops, checked database counts, generated all five reports, and ran the test suite.

## Where the AI was wrong or unhelpful
- Some suggested code and commands needed adjustment to match the existing project structure and actual function names.
- During development, an incorrect file replacement caused ingestion code to be overwritten. I identified the issue through code inspection and restored the ingestion implementation.
- I did not accept suggestions blindly; I checked the implementation against actual execution results and corrected issues where necessary.

## How I verified AI-generated code
- Ran the complete automated test suite: 25 tests passed.
- Tested ingestion for both `data/drop_1` and `data/drop_2`.
- Re-ran both data drops and verified that database counts remained unchanged, confirming repeated ingestion was skipped.
- Verified the CLI help output and report generation command.
- Confirmed that all five required report files were generated successfully.
- Inspected database counts and report outputs manually.