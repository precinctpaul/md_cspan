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