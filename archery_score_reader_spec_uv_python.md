# Archery Score Reader — Python + uv Implementation Spec

Version: 0.4
Runtime target: macOS / Windows / Linux  
Package manager / runner: `uv`  
Primary language: Python 3.11+

---

## 1. System Goal

The system batch-processes photographed archery handwritten score sheets.

Input is a folder containing captured images. Each image may contain one or more score sheet pages or target/player blocks. Images may include perspective skew, paper deformation, uneven lighting, shadows, blur, occlusion, and red-pen corrections by judges.

The system outputs multiple structured tables. The first two required outputs are:

1. Raw player arrow-level score data
2. Total score summary data

The first production target is not fully automatic perfect OCR. The realistic target is:

> Batch extraction + rule validation + confidence tracking + review item generation + extensible correction strategies + extensible report exporters.

---

## 2. Technology Decisions

### 2.1 Runtime

Use Python with `uv` for dependency management, virtual environment creation, package execution, and CLI workflow.

Recommended baseline:

```toml
requires-python = ">=3.11,<3.13"
```

Python 3.11 is a conservative choice because computer vision and ML packages usually have better wheel availability across macOS, Windows, and Linux.

### 2.2 Core Dependencies

Recommended initial dependencies:

```toml
[project]
dependencies = [
  "opencv-python>=4.9",
  "numpy>=1.26",
  "pillow>=10.0",
  "pydantic>=2.0",
  "pydantic-settings>=2.0",
  "typer>=0.12",
  "rich>=13.0",
  "pandas>=2.0",
  "pyyaml>=6.0",
  "onnxruntime>=1.17",
  "scikit-image>=0.22",
  "tqdm>=4.66"
]
```

Optional training / dataset dependencies:

```toml
[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "pytest-cov>=5.0",
  "ruff>=0.5",
  "mypy>=1.10",
  "types-PyYAML",
  "pre-commit>=3.0"
]
train = [
  "torch>=2.3",
  "torchvision>=0.18",
  "albumentations>=1.4",
  "matplotlib>=3.8"
]
```

Avoid making PyTorch a required runtime dependency unless the deployed inference path needs it. Prefer ONNX for inference.

---

## 3. Cross-platform Requirements

### 3.1 Supported Operating Systems

The system must run on:

- macOS, including Apple Silicon where possible
- Windows 10/11
- Linux x86_64

### 3.2 Path Handling

All file paths must use `pathlib.Path`, not hard-coded `/` or `\\` separators.

```python
from pathlib import Path

input_dir = Path("./input")
output_dir = Path("./output")
```

### 3.3 CLI Invocation

The system should run consistently with `uv`:

```bash
uv run score-reader run --input ./input --output ./output --config ./configs/default.yaml
```

Dataset generation:

```bash
uv run score-reader generate-dataset \
  --template ./templates/score_sheet.png \
  --geometry ./templates/score_sheet_geometry.json \
  --output ./dataset/generated \
  --config ./configs/augmentation.yaml
```

Tests:

```bash
uv run pytest
```

Linting:

```bash
uv run ruff check .
```

Formatting:

```bash
uv run ruff format .
```

Type checking:

```bash
uv run mypy src
```

---

## 4. Functional Requirements

## 4.1 Input

### FR-001: Folder Input

The system input is a folder path.

Example:

```text
input/
  IMG_0001.jpg
  IMG_0002.jpg
  IMG_0003.png
```

Supported image formats:

```text
.jpg
.jpeg
.png
.webp
.tiff
.tif
```

Initial MVP may support only:

```text
.jpg
.jpeg
.png
```

---

## 4.2 Batch Processing

### FR-002: Process All Supported Images in Folder

The system scans the input folder and processes all supported image files.

Per-image pipeline:

```text
Load image
  -> Image quality check
  -> Document detection
  -> Perspective correction / registration
  -> Table region extraction
  -> Target block extraction
  -> Cell extraction
  -> Cell-level score recognition
  -> Red correction detection
  -> Rule-based validation
  -> Correction strategy pipeline
  -> Structured result generation
```

### FR-003: Continue Job After Per-image Failure

If one image fails, the batch job must continue.

Example failed image result:

```json
{
  "image_id": "IMG_0005",
  "status": "failed",
  "errors": [
    {
      "code": "DOCUMENT_NOT_FOUND",
      "message": "Could not locate score sheet"
    }
  ]
}
```

### FR-004: One Image Can Contain Multiple Target Blocks

One image may contain multiple player/target blocks.

Example:

```json
{
  "image_id": "IMG_0001",
  "targets": [
    { "target_index": 0 },
    { "target_index": 1 },
    { "target_index": 2 },
    { "target_index": 3 }
  ]
}
```

---

## 4.3 Recognition Targets

### FR-005: Recognize Target Number

The system should recognize target number fields such as:

```text
1A
1B
1C
1D
12A
12B
```

If confidence is low, output `needs_review = true`.

### FR-006: Recognize Arrow Scores

Allowed values:

```text
X, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, M, blank, invalid
```

Internal numeric mapping:

```text
X       -> 10
10      -> 10
9       -> 9
8       -> 8
7       -> 7
6       -> 6
5       -> 5
4       -> 4
3       -> 3
2       -> 2
1       -> 1
M       -> 0
blank   -> null
invalid -> null
```

### FR-007: Recognize Subtotal, Cumulative, X Count, X+10 Count, Total

Each end has 6 arrows split into two groups of 3. The score sheet columns are:

```text
Arrow 1 | Arrow 2 | Arrow 3 | Subtotal | End Score | Cumulative
```

Each end occupies two rows:

- Row 1 (top half): arrows 1–3, subtotal for top 3
- Row 2 (bottom half): arrows 4–6, subtotal for bottom 3
- End score = top subtotal + bottom subtotal (max 60 per end)
- Cumulative = running total across ends

The system should recognize:

- Per-half subtotal (top 3 arrows, bottom 3 arrows)
- Per-end score (sum of both halves)
- Per-end cumulative score
- X count
- X+10 count
- Written total (max 360 for 6 ends × 6 arrows)

If written values and calculated values do not match, both must be preserved.

```json
{
  "written_total": 348,
  "calculated_total": 346,
  "total_matched": false,
  "needs_review": true
}
```

### FR-008: Detect Red-pen Corrections

The system should detect red-pen marks and corrections.

Supported red mark types:

```text
strike_through
overwrite
circle
correction_text
check_mark
unknown_red_mark
```

MVP behavior:

```json
{
  "has_red_mark": true,
  "red_mark_type": "correction_text",
  "needs_review": true
}
```

If a red correction value can be recognized:

```json
{
  "black_value": "8",
  "red_correction_value": "9",
  "final_value": "9",
  "source": "red_correction",
  "needs_review": true
}
```

---

## 5. Output Requirements

The system writes all output files to a specified output folder.

```text
output/
  raw_player_scores.csv
  total_scores.csv
  recognition_results.json
  review_items.csv
  debug/
    IMG_0001_overlay.jpg
    IMG_0001_cells/
```

---

## 5.1 Output 1: Raw Player Score Table

### FR-009: Generate `raw_player_scores.csv`

This is the most granular table. One row represents one arrow score.

Columns:

| Column | Description |
|---|---|
| `source_image` | Source image filename |
| `sheet_id` | Score sheet ID |
| `target_index` | Target block index inside image |
| `target_no` | Target number, e.g. `12A` |
| `unit` | Unit (school / company / organization) |
| `archer_name` | Archer name |
| `end_no` | End number |
| `arrow_no` | Arrow number inside the end |
| `recognized_value` | Model-recognized value |
| `final_value` | Final value after correction / validation |
| `score_value` | Numeric score |
| `confidence` | Recognition confidence |
| `source` | `black`, `red`, `inferred`, or `manual` |
| `has_red_mark` | Whether red mark exists |
| `needs_review` | Whether human review is required |
| `cell_id` | Stable cell ID |

Example:

```csv
source_image,sheet_id,target_index,target_no,unit,archer_name,end_no,arrow_no,recognized_value,final_value,score_value,confidence,source,has_red_mark,needs_review,cell_id
IMG_0001.jpg,S001,0,12A,台北市,王小明,1,1,10,10,10,0.94,black,false,false,T0_E1_A1
IMG_0001.jpg,S001,0,12A,台北市,王小明,1,2,9,9,9,0.88,black,false,false,T0_E1_A2
IMG_0001.jpg,S001,0,12A,台北市,王小明,1,3,8,9,9,0.61,red,true,true,T0_E1_A3
```

---

## 5.2 Output 2: Total Score Table

### FR-010: Generate `total_scores.csv`

One row represents one player/target summary.

Columns:

| Column | Description |
|---|---|
| `sheet_id` | Score sheet ID |
| `source_image` | Source image filename |
| `target_index` | Target block index |
| `target_no` | Target number |
| `unit` | Unit (school / company / organization) |
| `archer_name` | Archer name |
| `x_count` | Number of X values |
| `x_plus_ten_count` | Number of X or 10 values |
| `written_total` | Written total on sheet |
| `calculated_total` | Total calculated from arrow scores |
| `final_total` | Final selected total |
| `total_matched` | Whether written and calculated totals match |
| `review_cell_count` | Number of cells requiring review |
| `confidence_avg` | Average confidence |
| `status` | `ok`, `warning`, `error`, or `needs_review` |

Example:

```csv
sheet_id,source_image,target_index,target_no,unit,archer_name,x_count,x_plus_ten_count,written_total,calculated_total,final_total,total_matched,review_cell_count,confidence_avg,status
S001,IMG_0001.jpg,0,12A,台北市,王小明,3,8,168,168,168,true,0,0.93,ok
S001,IMG_0001.jpg,1,12B,新北市,陳大文,1,5,155,153,153,false,3,0.81,needs_review
```

---

## 5.3 Output 3: Full Recognition JSON

### FR-011: Generate `recognition_results.json`

CSV outputs are for reporting. JSON output is for downstream software integration and debugging.

Example:

```json
{
  "job_id": "job_20260101_120000",
  "input_dir": "./input",
  "images": [
    {
      "image_id": "IMG_0001",
      "file_name": "IMG_0001.jpg",
      "status": "processed",
      "quality": {
        "blur": 0.18,
        "shadow": 0.35,
        "perspective": 0.41,
        "needs_retake": false
      },
      "targets": [
        {
          "target_index": 0,
          "target_no": {
            "value": "12A",
            "confidence": 0.96,
            "needs_review": false
          },
          "unit": {
            "value": "台北市",
            "confidence": 0.82,
            "needs_review": true
          },
          "archer_name": {
            "value": "王小明",
            "confidence": 0.74,
            "needs_review": true
          },
          "ends": [
            {
              "end_no": 1,
              "top_half": {
                "arrows": [
                  {
                    "arrow_no": 1,
                    "recognized_value": "10",
                    "final_value": "10",
                    "score_value": 10,
                    "confidence": 0.94,
                    "source": "black",
                    "has_red_mark": false,
                    "needs_review": false
                  },
                  { "arrow_no": 2, "recognized_value": "X", "final_value": "X", "score_value": 10, "confidence": 0.97, "source": "black", "has_red_mark": false, "needs_review": false },
                  { "arrow_no": 3, "recognized_value": "9", "final_value": "9", "score_value": 9, "confidence": 0.91, "source": "black", "has_red_mark": false, "needs_review": false }
                ],
                "written_subtotal": 29,
                "calculated_subtotal": 29,
                "subtotal_matched": true
              },
              "bottom_half": {
                "arrows": [
                  { "arrow_no": 4, "recognized_value": "9", "final_value": "9", "score_value": 9, "confidence": 0.88, "source": "black", "has_red_mark": false, "needs_review": false },
                  { "arrow_no": 5, "recognized_value": "10", "final_value": "10", "score_value": 10, "confidence": 0.93, "source": "black", "has_red_mark": false, "needs_review": false },
                  { "arrow_no": 6, "recognized_value": "8", "final_value": "8", "score_value": 8, "confidence": 0.85, "source": "black", "has_red_mark": false, "needs_review": false }
                ],
                "written_subtotal": 27,
                "calculated_subtotal": 27,
                "subtotal_matched": true
              },
              "written_end_score": 56,
              "calculated_end_score": 56,
              "written_cumulative": 56,
              "calculated_cumulative": 56,
              "validated": true
            }
          ],
          "summary": {
            "x_count": 1,
            "x_plus_ten_count": 3,
            "written_total": 348,
            "calculated_total": 348,
            "final_total": 348,
            "validated": true
          }
        }
      ]
    }
  ]
}
```

---

## 5.4 Output 4: Review Items

### FR-012: Generate `review_items.csv`

This output supports future human review UI.

Columns:

| Column | Description |
|---|---|
| `source_image` | Source image |
| `target_index` | Target block index |
| `field_type` | `arrow_score`, `subtotal`, `total`, `target_no`, `name` |
| `cell_id` | Cell ID |
| `recognized_value` | Recognized value |
| `candidate_values` | Top-k candidates |
| `confidence` | Confidence |
| `reason` | Review reason |
| `crop_path` | Cell crop path |

Example:

```csv
source_image,target_index,field_type,cell_id,recognized_value,candidate_values,confidence,reason,crop_path
IMG_0001.jpg,0,arrow_score,T0_E2_A3,8,"8|9|3",0.52,"low_confidence;subtotal_mismatch",debug/IMG_0001_cells/T0_E2_A3.jpg
```

---

## 6. Non-functional Requirements

---

## 6.1 Data Augmentation Pipeline

### NFR-001: Reproducible Synthetic Data Pipeline

The system must provide a data generation and augmentation pipeline.

Inputs:

```text
template image
template geometry JSON
handwriting assets
augmentation config
```

Outputs:

```text
synthetic images
label JSON files
cell crops
debug overlays
```

### NFR-002: Configurable Augmentation

All data generation parameters must be configurable through YAML.

Example:

```yaml
dataset:
  output_dir: ./dataset/generated
  num_images: 10000
  train_ratio: 0.8
  val_ratio: 0.1
  test_ratio: 0.1

score_distribution:
  profile_mix:
    beginner: 0.2
    club: 0.4
    advanced: 0.3
    elite: 0.1

rendering:
  handwriting_fonts_dir: ./assets/fonts/handwriting
  random_offset_px: [-8, 8]
  random_rotation_deg: [-7, 7]
  ink_intensity: [0.55, 1.0]

photo_augmentation:
  perspective_prob: 0.8
  shadow_prob: 0.7
  blur_prob: 0.4
  paper_warp_prob: 0.4
  jpeg_compression_prob: 0.5

red_correction:
  enabled: true
  probability_per_sheet: 0.25
  correction_types:
    strike_through: 0.4
    overwrite: 0.3
    circle: 0.2
    unknown: 0.1
```

### NFR-003: Augmentation Stages

The data pipeline must support independent enable/disable switches for these stages:

```text
1. Ground truth score generation
2. Handwriting rendering
3. Red correction rendering
4. Print / scan degradation
5. Camera degradation
6. Perspective transform
7. Paper warp
8. Shadow / occlusion
9. Label geometry transformation
10. Export
```

### NFR-004: Geometry Labels Must Use Polygons

All transformed labels must use polygons rather than only bounding boxes.

```json
{
  "cell_id": "T0_E1_A1",
  "template_polygon": [[100,100], [150,100], [150,140], [100,140]],
  "image_polygon": [[103,98], [154,101], [153,142], [101,139]],
  "value": "10"
}
```

### NFR-005: Record Random Seed

Each generated synthetic image must record its random seed and config hash.

```json
{
  "image_id": "synthetic_000001",
  "seed": 123456789,
  "augmentation_config_hash": "abc123"
}
```

---

## 6.2 Automated Testing

### NFR-006: Required Test Types

The system must support:

```text
Unit tests
Integration tests
Golden sample tests
Synthetic regression tests
End-to-end tests
```

### NFR-007: Unit Tests

Unit tests must cover:

```text
score value mapping
subtotal calculation
cumulative calculation
X count calculation
X+10 count calculation
CSV export formatting
JSON schema validation
strategy selection logic
augmentation config parsing
```

Example cases:

```text
X -> 10
M -> 0
["X", "10", "9"] -> subtotal 29
["X", "10", "9", "8"] -> x_count = 1, x_plus_ten_count = 2
```

### NFR-008: Integration Tests

Integration tests must cover:

```text
input folder scanning
image processing pipeline orchestration
template registration to cell extraction
cell recognition to rule validation
result aggregation to CSV export
```

### NFR-009: Golden Sample Tests

Maintain fixed sample images and expected outputs.

```text
tests/golden/
  images/
    sample_001.jpg
  expected/
    sample_001.raw_player_scores.csv
    sample_001.total_scores.csv
    sample_001.result.json
```

### NFR-010: Synthetic Regression Tests

Whenever the augmentation pipeline changes, verify:

```text
label polygons are inside image bounds
cell crops can be generated
score totals are consistent
CSV row counts are correct
JSON schema is valid
debug overlays are produced
```

### NFR-011: End-to-end Tests

Example:

```bash
uv run score-reader run \
  --input ./tests/e2e/input \
  --output ./tests/e2e/output \
  --config ./configs/test.yaml
```

Verify:

```text
raw_player_scores.csv exists
total_scores.csv exists
recognition_results.json exists
review_items.csv exists
debug overlays exist
row counts are expected
```

---

## 6.3 Pattern for Correction Strategies

Use Strategy Pattern + Chain of Responsibility.

### NFR-012: Correction Strategy Interface

Python protocol:

```python
from typing import Protocol

class CorrectionStrategy(Protocol):
    name: str

    def applies(self, context: "CorrectionContext") -> bool:
        ...

    def apply(self, context: "CorrectionContext") -> "CorrectionResult":
        ...
```

### Correction Context

```python
from pydantic import BaseModel

class CorrectionContext(BaseModel):
    target: "TargetRecognitionResult"
    config: dict
```

### Correction Result

```python
from pydantic import BaseModel

class CorrectionResult(BaseModel):
    changed: bool
    warnings: list["ValidationWarning"] = []
    strategy_name: str
```

### Built-in Strategy Candidates

```text
LowConfidenceReviewStrategy
SubtotalMismatchStrategy
CumulativeMismatchStrategy
TotalMismatchStrategy
RedCorrectionOverrideStrategy
ImpossibleValueStrategy
XCountMismatchStrategy
XPlusTenMismatchStrategy
BlankCellInferenceStrategy
SuspiciousTenStrategy
```

### Strategy Execution Order

```text
raw recognition result
  -> ImpossibleValueStrategy
  -> RedCorrectionOverrideStrategy
  -> SubtotalMismatchStrategy
  -> CumulativeMismatchStrategy
  -> TotalMismatchStrategy
  -> LowConfidenceReviewStrategy
  -> final result
```

### Python Registration Example

```python
correction_pipeline = CorrectionPipeline([
    ImpossibleValueStrategy(),
    RedCorrectionOverrideStrategy(),
    SubtotalMismatchStrategy(),
    CumulativeMismatchStrategy(),
    TotalMismatchStrategy(),
    LowConfidenceReviewStrategy(),
])
```

Adding a new strategy should require only:

1. Create a new strategy class
2. Register it in config or registry
3. Add tests

The core pipeline should not be modified.

---

## 6.4 Pattern for Output Table Types

Use Exporter Strategy Pattern / Report Generator Pattern.

### NFR-013: Report Exporter Interface

Python protocol:

```python
from pathlib import Path
from typing import Protocol

class ReportExporter(Protocol):
    report_name: str

    def export(self, result: "RecognitionJobResult", output_dir: Path) -> "ExportResult":
        ...
```

### Export Result

```python
from pathlib import Path
from pydantic import BaseModel

class ExportResult(BaseModel):
    report_name: str
    output_path: Path
    row_count: int
    status: str
    error: str | None = None
```

### Required Built-in Exporters

```text
RawPlayerScoresCsvExporter
TotalScoresCsvExporter
RecognitionJsonExporter
ReviewItemsCsvExporter
DebugOverlayExporter
CellCropExporter
```

Adding a new output table should require only:

1. Create a new exporter class
2. Register it in config or registry
3. Add tests

The core recognition pipeline should not be modified.

---

## 7. Recommended Project Structure

```text
score-reader/
  pyproject.toml
  README.md
  uv.lock

  configs/
    default.yaml
    test.yaml
    augmentation.yaml

  templates/
    score_sheet.png
    score_sheet_geometry.json

  assets/
    fonts/
    paper_textures/
    shadow_masks/

  src/
    score_reader/
      __init__.py

      cli.py

      config/
        __init__.py
        settings.py
        load_config.py

      domain/
        __init__.py
        models.py
        score.py
        errors.py

      input/
        __init__.py
        folder_scanner.py

      image/
        __init__.py
        loader.py
        quality_checker.py
        document_detector.py
        perspective_corrector.py
        template_registrar.py

      extraction/
        __init__.py
        target_block_extractor.py
        cell_extractor.py

      recognition/
        __init__.py
        cell_classifier.py
        red_mark_detector.py
        target_no_recognizer.py

      validation/
        __init__.py
        score_calculator.py
        rule_validator.py

      correction/
        __init__.py
        base.py
        pipeline.py
        registry.py
        strategies/
          __init__.py
          impossible_value.py
          red_correction_override.py
          subtotal_mismatch.py
          cumulative_mismatch.py
          total_mismatch.py
          low_confidence_review.py

      export/
        __init__.py
        base.py
        registry.py
        exporters/
          __init__.py
          raw_player_scores_csv.py
          total_scores_csv.py
          recognition_json.py
          review_items_csv.py
          debug_overlay.py

      dataset/
        __init__.py
        generator/
          __init__.py
          ground_truth_generator.py
          sheet_renderer.py
          handwriting_renderer.py
          red_correction_renderer.py
          photo_augmentor.py
          label_transformer.py
          exporter.py

      pipeline/
        __init__.py
        runner.py
        image_processor.py

  tests/
    unit/
    integration/
    golden/
      images/
      expected/
    e2e/
      input/
      expected/
```

---

## 8. `pyproject.toml` Spec

```toml
[project]
name = "score-reader"
version = "0.1.0"
description = "Batch recognition system for handwritten archery score sheets"
readme = "README.md"
requires-python = ">=3.11,<3.13"
dependencies = [
  "opencv-python>=4.9",
  "numpy>=1.26",
  "pillow>=10.0",
  "pydantic>=2.0",
  "pydantic-settings>=2.0",
  "typer>=0.12",
  "rich>=13.0",
  "pandas>=2.0",
  "pyyaml>=6.0",
  "onnxruntime>=1.17",
  "scikit-image>=0.22",
  "tqdm>=4.66"
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "pytest-cov>=5.0",
  "ruff>=0.5",
  "mypy>=1.10",
  "types-PyYAML",
  "pre-commit>=3.0"
]
train = [
  "torch>=2.3",
  "torchvision>=0.18",
  "albumentations>=1.4",
  "matplotlib>=3.8"
]

[project.scripts]
score-reader = "score_reader.cli:app"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM"]

[tool.mypy]
python_version = "3.11"
strict = true
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

---

## 9. Domain Model Spec

Use Pydantic models for validation and JSON serialization.

### 9.1 Score Value Types

```python
from enum import StrEnum

class ArrowScoreValue(StrEnum):
    X = "X"
    TEN = "10"
    NINE = "9"
    EIGHT = "8"
    SEVEN = "7"
    SIX = "6"
    FIVE = "5"
    FOUR = "4"
    THREE = "3"
    TWO = "2"
    ONE = "1"
    M = "M"
    BLANK = "blank"
    INVALID = "invalid"
```

### 9.2 Recognized Field

```python
from typing import Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")

class Candidate(BaseModel, Generic[T]):
    value: T
    confidence: float = Field(ge=0.0, le=1.0)

class RecognizedField(BaseModel, Generic[T]):
    value: T | None
    confidence: float = Field(ge=0.0, le=1.0)
    top_candidates: list[Candidate[T]] = []
    needs_review: bool = False
```

### 9.3 Recognition Job Result

```python
from pathlib import Path
from pydantic import BaseModel

class RecognitionJobResult(BaseModel):
    job_id: str
    input_dir: Path
    processed_at: str
    images: list["ImageRecognitionResult"]
```

### 9.4 Image Recognition Result

```python
class ImageRecognitionResult(BaseModel):
    image_id: str
    file_name: str
    file_path: Path
    status: str
    quality: "ImageQualityResult | None" = None
    targets: list["TargetRecognitionResult"] = []
    errors: list["ProcessingError"] = []
```

### 9.5 Target Recognition Result

```python
class TargetRecognitionResult(BaseModel):
    target_index: int
    target_no: RecognizedField[str]
    unit: RecognizedField[str] | None = None
    archer_name: RecognizedField[str] | None = None
    ends: list["EndScoreResult"] = []
    summary: "TargetScoreSummary"
    review_required: bool = False
    warnings: list["ValidationWarning"] = []
```

### 9.6 Half-end Score Result

Each end has two halves (top 3 arrows and bottom 3 arrows), each with its own subtotal.

```python
class HalfEndScoreResult(BaseModel):
    arrows: list["ArrowScoreResult"]  # exactly 3 arrows
    written_subtotal: RecognizedField[int] | None = None
    calculated_subtotal: int
    subtotal_matched: bool = False
```

### 9.7 End Score Result

```python
class EndScoreResult(BaseModel):
    end_no: int
    top_half: HalfEndScoreResult
    bottom_half: HalfEndScoreResult
    written_end_score: RecognizedField[int] | None = None
    calculated_end_score: int  # top subtotal + bottom subtotal, max 60
    end_score_matched: bool = False
    written_cumulative: RecognizedField[int] | None = None
    calculated_cumulative: int
    cumulative_matched: bool = False
```

### 9.8 Arrow Score Result

```python
class ArrowScoreResult(BaseModel):
    arrow_no: int
    recognized_value: RecognizedField[ArrowScoreValue]
    final_value: ArrowScoreValue
    score_value: int | None
    source: str
    has_red_mark: bool
    red_mark: "RedMarkResult | None" = None
    needs_review: bool
    review_reasons: list[str] = []
    cell_id: str
    crop_path: Path | None = None
```

---

## 10. CLI Spec

Use Typer.

```bash
uv run score-reader --help
```

### 10.1 Run Recognition

```bash
uv run score-reader run \
  --input ./input \
  --output ./output \
  --config ./configs/default.yaml
```

### 10.2 Generate Dataset

```bash
uv run score-reader generate-dataset \
  --template ./templates/score_sheet.png \
  --geometry ./templates/score_sheet_geometry.json \
  --output ./dataset/generated \
  --config ./configs/augmentation.yaml
```

### 10.3 Validate Generated Dataset

```bash
uv run score-reader validate-dataset \
  --dataset ./dataset/generated
```

### 10.4 Print Config

```bash
uv run score-reader print-config --config ./configs/default.yaml
```

---

## 11. Config Spec

### 11.1 Runtime Config

```yaml
input:
  supported_extensions:
    - ".jpg"
    - ".jpeg"
    - ".png"

processing:
  save_debug_images: true
  save_cell_crops: true
  max_workers: 4

quality:
  min_blur_score: 0.4
  max_shadow_score: 0.8
  retake_policy: "warn"

recognition:
  score_cell_model_path: "./models/score-cell.onnx"
  confidence_threshold: 0.75
  top_k: 3

red_mark:
  enabled: true
  red_detection_method: "hsv"
  min_red_area_ratio: 0.02

correction:
  enabled_strategies:
    - ImpossibleValueStrategy
    - RedCorrectionOverrideStrategy
    - SubtotalMismatchStrategy
    - CumulativeMismatchStrategy
    - TotalMismatchStrategy
    - LowConfidenceReviewStrategy

export:
  enabled_exporters:
    - RawPlayerScoresCsvExporter
    - TotalScoresCsvExporter
    - RecognitionJsonExporter
    - ReviewItemsCsvExporter
    - DebugOverlayExporter
```

### 11.2 Augmentation Config

```yaml
dataset:
  output_dir: ./dataset/generated
  num_images: 10000
  train_ratio: 0.8
  val_ratio: 0.1
  test_ratio: 0.1
  seed: 1234

score_distribution:
  profile_mix:
    beginner: 0.2
    club: 0.4
    advanced: 0.3
    elite: 0.1

rendering:
  handwriting_fonts_dir: ./assets/fonts/handwriting
  random_offset_px: [-8, 8]
  random_rotation_deg: [-7, 7]
  ink_intensity: [0.55, 1.0]
  grid_overlap_probability: 0.25

photo_augmentation:
  perspective_prob: 0.8
  shadow_prob: 0.7
  blur_prob: 0.4
  paper_warp_prob: 0.4
  jpeg_compression_prob: 0.5

red_correction:
  enabled: true
  probability_per_sheet: 0.25
  correction_types:
    strike_through: 0.4
    overwrite: 0.3
    circle: 0.2
    unknown: 0.1
```

---

## 12. Main Pipeline Spec

```text
FolderScanner
  -> for each image:
       ImageLoader
       QualityChecker
       DocumentDetector
       PerspectiveCorrector
       TemplateRegistrar
       TargetBlockExtractor
       CellExtractor
       CellClassifier
       RedMarkDetector
       RuleValidator
       CorrectionPipeline
       TargetResult
  -> RecognitionJobResult
  -> ReportExporters
```

### 12.1 Folder Scanner

Responsibilities:

- Validate input folder exists
- Find supported image files
- Return stable sorted list of files
- Ignore unsupported files

### 12.2 Image Processor

Responsibilities:

- Process one image
- Catch image-level exceptions
- Return `ImageRecognitionResult`
- Never terminate whole batch directly

### 12.3 Job Runner

Responsibilities:

- Load config
- Create job ID
- Process images
- Aggregate results
- Run exporters

---

## 13. Correction Strategy Pattern

### 13.1 Base Interface

```python
from typing import Protocol

class CorrectionStrategy(Protocol):
    name: str

    def applies(self, context: CorrectionContext) -> bool:
        ...

    def apply(self, context: CorrectionContext) -> CorrectionResult:
        ...
```

### 13.2 Pipeline

```python
class CorrectionPipeline:
    def __init__(self, strategies: list[CorrectionStrategy]) -> None:
        self.strategies = strategies

    def apply(self, target: TargetRecognitionResult, config: dict) -> TargetRecognitionResult:
        context = CorrectionContext(target=target, config=config)
        for strategy in self.strategies:
            if strategy.applies(context):
                result = strategy.apply(context)
                target.warnings.extend(result.warnings)
        return target
```

### 13.3 Strategy Registry

The registry maps config names to strategy instances.

```python
STRATEGY_REGISTRY = {
    "ImpossibleValueStrategy": ImpossibleValueStrategy,
    "RedCorrectionOverrideStrategy": RedCorrectionOverrideStrategy,
    "SubtotalMismatchStrategy": SubtotalMismatchStrategy,
    "CumulativeMismatchStrategy": CumulativeMismatchStrategy,
    "TotalMismatchStrategy": TotalMismatchStrategy,
    "LowConfidenceReviewStrategy": LowConfidenceReviewStrategy,
}
```

---

## 14. Report Exporter Pattern

### 14.1 Base Interface

```python
from pathlib import Path
from typing import Protocol

class ReportExporter(Protocol):
    report_name: str

    def export(self, result: RecognitionJobResult, output_dir: Path) -> ExportResult:
        ...
```

### 14.2 Exporter Registry

```python
EXPORTER_REGISTRY = {
    "RawPlayerScoresCsvExporter": RawPlayerScoresCsvExporter,
    "TotalScoresCsvExporter": TotalScoresCsvExporter,
    "RecognitionJsonExporter": RecognitionJsonExporter,
    "ReviewItemsCsvExporter": ReviewItemsCsvExporter,
    "DebugOverlayExporter": DebugOverlayExporter,
}
```

---

## 15. Data Augmentation Pipeline Spec

### 15.1 Dataset Generation Flow

```text
Blank template image
  -> Generate structured ground truth scores
  -> Render handwriting into score cells
  -> Render red-pen corrections
  -> Apply print / scan degradation
  -> Apply camera degradation
  -> Apply perspective transform
  -> Apply paper warp
  -> Apply shadows / occlusion
  -> Transform label polygons
  -> Export image + labels + crops + overlay
```

### 15.2 Output Structure

```text
dataset/generated/
  images/
    train/
    val/
    test/
  labels/
    train/
    val/
    test/
  cell_crops/
    train/
    val/
    test/
  debug_overlays/
    train/
    val/
    test/
  manifest.jsonl
```

### 15.3 Synthetic Label Schema

```json
{
  "image_id": "synthetic_000001",
  "seed": 123456789,
  "template_id": "tw_archery_score_sheet_v1",
  "image_size": {
    "width": 1920,
    "height": 1080
  },
  "document": {
    "page_polygon": [[120, 80], [1810, 100], [1760, 1020], [150, 1000]],
    "quality": {
      "blur": 0.21,
      "shadow": 0.35,
      "perspective": 0.44,
      "warp": 0.18
    }
  },
  "targets": [
    {
      "target_index": 0,
      "target_no": {
        "value": "12A",
        "polygon": [[0,0], [0,0], [0,0], [0,0]],
        "source": "synthetic"
      },
      "rounds": [
        {
          "end": 1,
          "arrows": [
            {
              "arrow": 1,
              "value": "X",
              "score_value": 10,
              "polygon": [[0,0], [0,0], [0,0], [0,0]],
              "has_red_correction": false,
              "final_value": "X",
              "needs_review": false
            }
          ],
          "subtotal": 29,
          "cumulative": 29
        }
      ],
      "total": 168,
      "x_count": 3,
      "x_plus_ten_count": 8
    }
  ]
}
```

---

## 16. Automated Test Plan

### 16.1 Unit Test Targets

```text
score_reader.domain.score
score_reader.validation.score_calculator
score_reader.correction.pipeline
score_reader.export.exporters.raw_player_scores_csv
score_reader.export.exporters.total_scores_csv
score_reader.dataset.generator.ground_truth_generator
score_reader.dataset.generator.label_transformer
```

### 16.2 Integration Test Targets

```text
FolderScanner + ImageProcessor with fake recognizer
RecognitionJobResult + Exporters
Config loading + strategy registry
Config loading + exporter registry
Dataset generation with fixed seed
```

### 16.3 Golden Test Policy

Golden outputs should be stable. If an intentional change modifies output, update golden files in the same commit with a clear reason.

### 16.4 CI Commands

```bash
uv sync --extra dev
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

---

## 17. Acceptance Criteria

### AC-001: Folder Batch Processing

Given a folder with 10 supported image files, the system processes all files and writes output files.

### AC-002: Raw Player Scores Output

System writes `raw_player_scores.csv`.

If each image has 4 players, each player has 6 ends, and each end has 6 arrows, then 10 images should produce:

```text
10 * 4 * 6 * 6 = 1440 rows
```

### AC-003: Total Scores Output

System writes `total_scores.csv`.

If each image has 4 players, then 10 images should produce:

```text
10 * 4 = 40 rows
```

### AC-004: Error Isolation

One failed image must not stop the whole batch job.

### AC-005: Correction Strategy Extensibility

Adding a new correction strategy should not modify the core pipeline.

Required steps:

1. Add strategy class
2. Register in strategy registry or config
3. Add tests

### AC-006: Output Table Extensibility

Adding a new report table should not modify the core pipeline.

Required steps:

1. Add exporter class
2. Register in exporter registry or config
3. Add tests

### AC-007: Dataset Reproducibility

Running dataset generation twice with the same seed and config should produce identical labels and equivalent images, excluding metadata timestamps.

---

## 18. Implementation Phases

### Phase 1: Project Skeleton and Domain Model

Deliverables:

```text
uv project setup
CLI skeleton
Pydantic domain models
Score calculator
Exporter interfaces
Correction strategy interfaces
Basic tests
```

### Phase 2: Exporters with Fake Recognition Results

Deliverables:

```text
RawPlayerScoresCsvExporter
TotalScoresCsvExporter
RecognitionJsonExporter
ReviewItemsCsvExporter
Golden sample tests using fake results
```

### Phase 3: Synthetic Data Pipeline MVP

Deliverables:

```text
Ground truth score generator
Template geometry loader
Handwriting renderer
Cell crop exporter
Label JSON exporter
Debug overlay exporter
Fixed-seed regression test
```

### Phase 4: Cell Classifier Integration

Deliverables:

```text
ONNX cell classifier interface
Top-k candidate output
Confidence thresholding
LowConfidenceReviewStrategy
Synthetic validation test
```

### Phase 5: Full Sheet Processing MVP

Deliverables:

```text
Image loader
Quality checker
Document detector
Perspective correction
Template registration
Cell extraction
End-to-end batch run
```

### Phase 6: Red-pen and Rule Correction

Deliverables:

```text
Red mark detector
RedCorrectionOverrideStrategy
SubtotalMismatchStrategy
CumulativeMismatchStrategy
TotalMismatchStrategy
Review item output
```

---

## 19. MVP Scope Recommendation

For the first usable MVP, defer these items:

```text
Full handwritten name recognition
Full handwritten unit recognition
Complex judge signature understanding
Multiple sheet template support
Highly accurate paper dewarping
Fully automatic red correction interpretation
```

Focus first on:

```text
Input folder batch processing
Target block extraction
Arrow score cell recognition
Subtotal / total validation
Raw score CSV
Total score CSV
Review item CSV
Synthetic data generation
Automated tests
Strategy/exporter extensibility
```

---

## 20. Practical Risk Notes

The highest-risk parts are:

1. Cell extraction under perspective and paper deformation
2. Handwritten `10` versus `1` / `0` confusion
3. `X` versus red strike-through / multiplication sign confusion
4. Red-pen correction semantics
5. Synthetic-to-real domain gap
6. Slightly different printed templates
7. Low-quality photos with shadows and blur

The system must preserve confidence, top-k candidates, review reasons, and crop paths so that human review can correct uncertain cases efficiently.

