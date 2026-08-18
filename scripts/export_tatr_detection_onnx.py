"""Download microsoft/table-transformer-detection via HF mirror and export detection.onnx."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

OUT = Path(__file__).resolve().parents[1] / "third_party" / "pdf_layout"
OUT.mkdir(parents=True, exist_ok=True)
DEST = OUT / "detection.onnx"


def main() -> int:
    if DEST.is_file() and DEST.stat().st_size > 1_000_000:
        print(f"already exists: {DEST} ({DEST.stat().st_size} bytes)")
        return 0

    import torch
    from transformers import AutoModelForObjectDetection

    print("loading microsoft/table-transformer-detection ...")
    model = AutoModelForObjectDetection.from_pretrained(
        "microsoft/table-transformer-detection",
        torch_dtype=torch.float32,
    )
    model.eval()

    # TATR typically trained around 800px; keep fixed for ONNX
    h = w = 800
    dummy = torch.randn(1, 3, h, w, dtype=torch.float32)

    class Wrap(torch.nn.Module):
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, pixel_values: torch.Tensor):
            out = self.m(pixel_values=pixel_values)
            # logits: [B,Q,C], boxes: [B,Q,4] (cx,cy,w,h normalized)
            return out.logits, out.pred_boxes

    wrapped = Wrap(model)
    tmp = OUT / "detection.onnx.part"
    print(f"exporting ONNX -> {tmp}")
    torch.onnx.export(
        wrapped,
        dummy,
        str(tmp),
        input_names=["pixel_values"],
        output_names=["logits", "pred_boxes"],
        dynamic_axes={
            "pixel_values": {0: "batch"},
            "logits": {0: "batch"},
            "pred_boxes": {0: "batch"},
        },
        opset_version=17,
    )
    if not tmp.is_file() or tmp.stat().st_size < 1_000_000:
        print("export failed or file too small")
        return 1
    tmp.replace(DEST)
    # sidecar meta for our loader
    (OUT / "detection.meta.json").write_text(
        '{"format":"tatr","input":"pixel_values","size":800,"outputs":["logits","pred_boxes"]}\n',
        encoding="utf-8",
    )
    print(f"saved: {DEST} ({DEST.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("FAIL:", type(e).__name__, e, file=sys.stderr)
        raise SystemExit(1)
