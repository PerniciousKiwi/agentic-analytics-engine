from pathlib import Path

from onnxruntime.quantization import QuantType, quantize_dynamic

ROOT = Path(__file__).resolve().parents[1]

INPUT_PATH = ROOT / "artifacts" / "reranker" / "model.onnx"
OUTPUT_PATH = ROOT / "artifacts" / "reranker" / "model.int8.onnx"


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"ONNX model not found: {INPUT_PATH}")

    quantize_dynamic(
        model_input=str(INPUT_PATH),
        model_output=str(OUTPUT_PATH),
        weight_type=QuantType.QInt8,
    )

    print(f"Quantized model written to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
