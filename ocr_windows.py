import json
import math
import sys
from contextlib import redirect_stdout
from pathlib import Path


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def create_engine():
    import rapidocr
    from rapidocr import RapidOCR

    models = Path(rapidocr.__file__).parent / 'models'
    files = {'Det': 'PP-OCRv6_det_small.onnx',
             'Cls': 'ch_ppocr_mobile_v2.0_cls_mobile.onnx',
             'Rec': 'PP-OCRv6_rec_small.onnx'}
    if not all((models / filename).is_file() for filename in files.values()):
        raise RuntimeError('OCR 模型文件缺失，请重新安装完整版。')
    params = {f'{stage}.model_path': str(models / filename) for stage, filename in files.items()}
    params.update({'Global.log_level': 'error', 'Global.max_side_len': 3200,
                   'EngineConfig.onnxruntime.intra_op_num_threads': 2,
                   'EngineConfig.onnxruntime.inter_op_num_threads': 1})
    return RapidOCR(params=params)


def recognize_page(document, number, engine):
    import numpy as np

    page = document[number - 1]
    try:
        width, height = page.get_size()
        if not all(math.isfinite(value) and value > 0 for value in (width, height)):
            raise ValueError('Invalid page size')
        scale = min(3.5, 3200 / max(width, height))
        bitmap = page.render(scale=scale)
        try:
            image = bitmap.to_pil().convert('RGB')
            try:
                result = engine(np.asarray(image))
                blocks = []
                if result.txts is not None:
                    for box, text, score in zip(result.boxes, result.txts, result.scores):
                        if not text.strip():
                            continue
                        points = [[round(max(0, min(1, float(point[0]) / image.width)), 6),
                                   round(max(0, min(1, float(point[1]) / image.height)), 6)] for point in box]
                        blocks.append({'text': text, 'confidence': round(float(score), 4), 'box': points})
                return {'page': number, 'text': '\n'.join(block['text'] for block in blocks),
                        'ocr_data': {'engine': 'RapidOCR', 'blocks': blocks}}
            finally:
                image.close()
        finally:
            bitmap.close()
    finally:
        page.close()


def main():
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        with redirect_stdout(sys.stderr):
            import pypdfium2 as pdfium
            engine = create_engine()
        if sys.argv[1:] == ['--check']:
            emit({'ready': True, 'engine': 'RapidOCR', 'offline': True})
            return 0
        if len(sys.argv) != 3:
            raise ValueError('Missing PDF or page numbers')
        numbers = [int(value) for value in sys.argv[2].split(',')]
        with pdfium.PdfDocument(sys.argv[1], password='') as document:
            for number in numbers:
                try:
                    if not 1 <= number <= len(document):
                        raise ValueError('Invalid page')
                    with redirect_stdout(sys.stderr):
                        result = recognize_page(document, number, engine)
                    emit(result)
                except Exception:
                    emit({'page': number, 'error': '此页识别失败，请核对原图后重试。'})
        emit({'done': True})
        return 0
    except Exception:
        emit({'fatal': True, 'error': 'Windows OCR 无法启动，请安装完整 OCR 依赖或重新安装最新版。'})
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
