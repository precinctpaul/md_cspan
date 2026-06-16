# md_cspan

Majority Democrats C-SPAN archive tooling.

This repo is for building a repeatable C-SPAN intake pipeline that can support:

- Member archive discovery
- Floor speech discovery
- Committee moment discovery
- EVIE POC test batches
- YouTube repurposing backlogs
- LucidLink archive organization
- Frame.io review packets
- Adobe Premiere / After Effects packaging workflows

## Setup

Create a virtual environment:

```bat
cd /d "H:\My Drive\Majority Democrats\Scripts\md_cspan"

python -m venv .venv

.venv\Scripts\activate

pip install -r requirements.txt
```

## Local Matrix Browser

Run the small CSV-backed, member-first matrix browser:

```bat
cd /d "H:\My Drive\Majority Democrats\Scripts\md_cspan"

python -m md_cspan.review_app
```

Open:

```text
http://127.0.0.1:5055
```

The browser defaults to the broad master catalog:

```text
output\cspan_member_programs_all.csv
```

Priority and lead-export CSVs are narrower views of the broad catalog. Use the browser to search, filter, sort, inspect member/topic fields, and open C-SPAN links. It is read-only: not a manual review or triage app, and it does not write reviewed CSVs.
