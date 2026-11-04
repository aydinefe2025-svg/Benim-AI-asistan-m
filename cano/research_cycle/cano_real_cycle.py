"""CANO: reproducible, bounded OFFLINE research cycle using real packaged datasets.

Run: python cano_real_cycle.py run --output /path/to/output
     python cano_real_cycle.py verify --output /path/to/output

Requires sklearn/numpy and atomic_batch.py; never silently fetches external data,
claims scientific discovery, or approves a finding automatically.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
from contextlib import closing
import sqlite3
import tempfile

import numpy as np
from sklearn import __version__ as sklearn_version
from sklearn.datasets import load_wine, load_digits
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import atomic_batch

SOURCE_INFO = {
    'wine': {'source': 'https://doi.org/10.24432/C5PC7J',
             'description': 'UCI Wine: laboratory chemistry, 3 classes; packaged with scikit-learn',
             'data_origin': 'packaged_dataset_not_live_download'},
    'digits': {'source': 'https://scikit-learn.org/stable/modules/generated/sklearn.datasets.load_digits.html',
               'description': 'UCI-derived handwritten digits: 8x8 images, 10 classes; packaged with scikit-learn',
               'data_origin': 'packaged_dataset_not_live_download'},
}


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda: f.read(65536), b''):
            h.update(part)
    return h.hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('refusing to overwrite symlink')
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='',
                                     prefix='.partial-', dir=path.parent, delete=False) as f:
        name = f.name
        try:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        except BaseException:
            Path(name).unlink(missing_ok=True)
            raise
    os.replace(name, path)


def validate_data(X, y):
    if not isinstance(X, np.ndarray) or X.ndim != 2 or not 1 <= len(X) <= 5000:
        raise ValueError('invalid dataset shape')
    if X.shape[1] > 128 or len(y) != len(X) or not np.isfinite(X).all():
        raise ValueError('nonfinite or oversized dataset')
    if (np.unique(y, return_counts=True)[1] < 5).any():
        raise ValueError('too few examples per class for 5-fold cross-validation')
    row_hashes = [hashlib.sha256(np.asarray(row, dtype='<f8').tobytes()).hexdigest()
                  for row in X]
    if len(set(row_hashes)) != len(X):
        raise ValueError('identical input measurements detected; split-leakage risk')
    return row_hashes


def score_dataset(X, y):
    """Train/validation isolation: scaler is FIT inside every training fold only."""
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    models = {'baseline': DummyClassifier(strategy='most_frequent'),
              'model': make_pipeline(StandardScaler(), LogisticRegression(max_iter=1200))}
    out = {}
    for label, clf in models.items():
        folds = []
        for tr, te in cv.split(X, y):
            clf.fit(X[tr], y[tr])
            pred = clf.predict(X[te])
            folds.append({'n_test': int(len(te)), 'accuracy': round(float(accuracy_score(y[te], pred)), 6),
                          'macro_f1': round(float(f1_score(y[te], pred, average='macro')), 6)})
        out[label] = {'mean_accuracy': round(float(np.mean([f['accuracy'] for f in folds])), 6),
                      'mean_macro_f1': round(float(np.mean([f['macro_f1'] for f in folds])), 6),
                      'folds': folds}
    return out


def dataset_records(name, dataset):
    X = np.asarray(dataset.data, dtype=np.float64)
    y = np.asarray(dataset.target, dtype=np.int64)
    hashes = validate_data(X, y)
    results = score_dataset(X, y)
    counts = {str(int(x)): int(np.sum(y == x)) for x in np.unique(y)}
    info = {'dataset': name, 'sample_count': int(len(X)), 'features': int(X.shape[1]),
            'classes': counts, 'missing_or_nonfinite': 0, 'exact_duplicate_features': 0,
            'source': SOURCE_INFO[name]['source'], 'description': SOURCE_INFO[name]['description'],
            'data_origin': SOURCE_INFO[name]['data_origin'], 'validation': 'stratified 5-fold, seed 42',
            'caveat': ('Samples are not split by writer; individual-writer generalization not assessed.'
                       if name == 'digits' else 'Small, historical, well-separated classification benchmark.'),
            'scores': results}
    return X, y, hashes, info


def csv_string(X, y):
    import io
    f = io.StringIO(newline='')
    w = csv.writer(f, lineterminator='\n')
    w.writerow(['target'] + [f'feature_{i:02d}' for i in range(X.shape[1])])
    for row, target in zip(X, y):
        w.writerow([int(target)] + [format(float(x), '.12g') for x in row])
    return f.getvalue()


def generate_report(result):
    lines = ['# CANO — gerçek veri üzerinde uçtan uca deney', '',
             'Kaynak veriler scikit-learn paketinde bulunan gerçek tarihsel gözlem veri kümeleridir; '
             'bu çalışma **yeni bir bilimsel keşif** veya gerçek zamanlı veri indirme iddiası taşımaz.', '',
             'Her veri kümesi için 5 katlı sınıf-oranlı çapraz doğrulama yapılmıştır. '
             'Ölçekleme yalnızca eğitim katında öğrenilir; karşılaştırma çoğunluk sınıfı taban çizgisiyledir.', '']
    for name in ('wine', 'digits'):
        r = result['datasets'][name]
        lines += [f'## {name}', f"- Kaynak: {r['source']}",
                  f"- {r['sample_count']} kayıt × {r['features']} özellik; sınıf dağılımı {r['classes']}",
                  f"- Taban çizgisi ortalama doğruluk: {r['scores']['baseline']['mean_accuracy']:.4f}",
                  f"- Eğitim katı ayrılmış model doğruluğu: {r['scores']['model']['mean_accuracy']:.4f}",
                  f"- Model macro-F1: {r['scores']['model']['mean_macro_f1']:.4f}",
                  f"- Sınır: {r['caveat']}", '']
    lines += ['## Denetim zinciri',
              f"- İşlenen toplam gerçek kayıt: {result['total_samples']}",
              '- Kayıtların durumu: `pending_review` (otomatik bilimsel onay yok)',
              '- Örnek kayıtları ve deney özetleri tek SQLite veritabanında atomik makbuzlarla tutulur.',
              '- `python cano_real_cycle.py verify --output run` dosya SHA-256 ve SQLite bütünlüğünü yeniden denetler.',
              '- Başka bilgisayarda çalıştırmak için scikit-learn ve NumPy gereklidir.',
              '', '### Kaynaklar',
              '- UCI Wine: https://doi.org/10.24432/C5PC7J',
              '- scikit-learn digits: https://scikit-learn.org/stable/modules/generated/sklearn.datasets.load_digits.html',
              '', '### Henüz tamamlanmış sayılmayanlar',
              'Gerçek zamanlı internet taraması, sürekli arka plan servisi, kendi kendine bilimsel onay, '
              'uzak GitHub/Notion senkronizasyonu bu yerel deneyin kapsamı dışındadır.', '']
    return '\n'.join(lines)


def run_cycle(outdir: Path):
    outdir = Path(outdir)
    if outdir.is_symlink():
        raise ValueError('unsafe output symlink')
    outdir.mkdir(parents=True, exist_ok=True)
    all_records = []
    summaries = {}
    for name, loader in [('wine', load_wine), ('digits', load_digits)]:
        X, y, hashes, info = dataset_records(name, loader())
        atomic_text(outdir / f'{name}_real_data.csv', csv_string(X, y))
        for i, (target, digest) in enumerate(zip(y, hashes)):
            all_records.append({'kind': 'observation', 'title': f'{name} / gözlem {i:04d}',
                                'source': SOURCE_INFO[name]['source'],
                                'evidence': f'real_packaged_data;class={int(target)};row_sha256={digest}'})
        all_records.append({'kind': 'experiment_result', 'title': f'{name} / 5-fold deney',
                            'source': SOURCE_INFO[name]['source'],
                            'evidence': json.dumps({'scores': info['scores'], 'n': int(len(X))},
                                                   sort_keys=True, separators=(',', ':'))})
        summaries[name] = info
    input_jsonl = '\n'.join(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
                            for r in all_records) + '\n'
    atomic_text(outdir / 'observations.jsonl', input_jsonl)
    database = outdir / 'findings.sqlite3'
    import_result = atomic_batch.run(outdir / 'observations.jsonl', database, limit=10000)
    proof = atomic_batch.audit(database)
    if not proof['ok'] or not import_result['all_processed'] or import_result['rejected']:
        raise RuntimeError(f'failed ingestion verification: {proof} / {import_result}')
    with closing(sqlite3.connect(f'file:{database.resolve()}?mode=ro', uri=True)) as conn:
        counts = dict(conn.execute('SELECT status,COUNT(*) FROM findings GROUP BY status'))
    if counts != {'pending_review': len(all_records)}:
        raise RuntimeError(f'unexpected finding statuses/counts: {counts}')
    report = {'protocol': 'CANO-REAL-1', 'sklearn_version': sklearn_version,
              'datasets': summaries, 'total_samples': sum(r['sample_count'] for r in summaries.values()),
              'finding_count': len(all_records), 'ingestion': import_result, 'audit': proof,
              'status': 'local_experiment_verified;findings_pending_review'}
    atomic_text(outdir / 'results.json', json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)+'\n')
    atomic_text(outdir / 'RESULTS.md', generate_report(report))
    files = ['wine_real_data.csv', 'digits_real_data.csv', 'observations.jsonl', 'results.json', 'RESULTS.md']
    manifest = {'format': 'CANO-MANIFEST-1', 'files': {name: {'size': (outdir / name).stat().st_size,
                                                               'sha256': sha_file(outdir / name)} for name in files},
                'db_integrity': proof['ok'], 'expected_findings': len(all_records)}
    atomic_text(outdir / 'manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)+'\n')
    return report


def verify_cycle(outdir: Path):
    outdir = Path(outdir)
    errors = []
    try:
        if outdir.is_symlink():
            raise ValueError('unsafe directory')
        m = json.loads((outdir / 'manifest.json').read_text(encoding='utf-8'))
        files = {'wine_real_data.csv', 'digits_real_data.csv', 'observations.jsonl', 'results.json', 'RESULTS.md'}
        if m.get('format') != 'CANO-MANIFEST-1' or set(m.get('files', {})) != files:
            raise ValueError('unexpected manifest schema')
        for name in files:
            path = outdir / name
            spec = m['files'][name]
            if path.is_symlink() or not path.is_file() or path.stat().st_size != spec['size'] or sha_file(path) != spec['sha256']:
                errors.append(f'file mismatch: {name}')
        proof = atomic_batch.audit(outdir / 'findings.sqlite3')
        if not proof['ok'] or proof['checked'] != m.get('expected_findings'):
            errors.append('SQLite receipt/finding audit mismatch')
        result = json.loads((outdir / 'results.json').read_text(encoding='utf-8'))
        if result.get('finding_count') != m['expected_findings']:
            errors.append('report count mismatch')
        for name in ('wine', 'digits'):
            with (outdir / f'{name}_real_data.csv').open(newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader)
                n = sum(1 for _ in reader)
            if n != result['datasets'][name]['sample_count'] or len(header)-1 != result['datasets'][name]['features']:
                errors.append(f'dataset rows or columns mismatch: {name}')
        return {'ok': not errors, 'errors': errors, 'checked_findings': proof.get('checked', 0)}
    except (OSError, ValueError, KeyError, TypeError, IndexError, json.JSONDecodeError, sqlite3.DatabaseError) as e:
        return {'ok': False, 'errors': [type(e).__name__ + ': ' + str(e)[:160]] + errors,
                'checked_findings': 0}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('run', 'verify'))
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = run_cycle(a.output) if a.command == 'run' else verify_cycle(a.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if a.command == 'verify' and not result['ok']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()