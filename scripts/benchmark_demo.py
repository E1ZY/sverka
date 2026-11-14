"""Measure real, fresh demo processing through the local API; never reuse extracted facts."""
import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


def request(base, path, method='GET'):
    headers = {'X-Sverka-Request': '1'}
    with urlopen(Request(base + '/api' + path, method=method, headers=headers), timeout=30) as response:
        return json.load(response)


def gpu_sample():
    try:
        output = subprocess.run(['nvidia-smi', '--query-gpu=name,utilization.gpu,memory.used,memory.total',
                                 '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=5, check=True)
        return [{'name': name.strip(), 'utilization_percent': int(utilization), 'memory_used_mib': int(used),
                 'memory_total_mib': int(total)} for name, utilization, used, total in
                (line.split(',') for line in output.stdout.strip().splitlines())]
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def measure(base, iteration, timeout):
    if any(case['status'] in {'running', 'queued'} for case in request(base, '/cases')):
        raise RuntimeError('Дождитесь завершения других проверок перед замером.')
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    launched = request(base, '/demo', 'POST')
    print(f"Run {iteration}: {launched['case_id']}", flush=True)
    samples, phases, previous, last_sample = [], [], None, -5.
    while True:
        elapsed = time.perf_counter() - started
        if elapsed > timeout:
            raise TimeoutError(f"Проверка {launched['case_id']} превысила {timeout} с; задание продолжает работу на сервере.")
        case = request(base, '/cases/' + launched['case_id'])
        run = next(run for run in case['runs'] if run['id'] == launched['run_id'])
        phase = (run['status'], run['message'])
        if phase != previous:
            phases.append({'elapsed_seconds': round(elapsed, 3), 'status': run['status'], 'message': run['message']})
            print(f"  {elapsed:.1f}s | {run['message']}", flush=True)
            previous = phase
        if elapsed - last_sample >= 5:
            samples.append({'elapsed_seconds': round(elapsed, 3), 'gpus': gpu_sample()})
            last_sample = elapsed
        if run['status'] in {'completed', 'failed'}:
            break
        time.sleep(1)
    observed = time.perf_counter() - started
    result = case.get('result') or {}
    total = next((metric for metric in result.get('metrics', []) if metric['code'] == 'total'), None)
    return {'iteration': iteration, **launched, 'requested_at': started_at,
            'observed_seconds': round(observed, 3), 'processing_seconds': run.get('duration_seconds'),
            'started_at': run.get('started_at'), 'finished_at': run.get('finished_at'), 'status': run['status'],
            'documents': len(case['documents']), 'included_documents': result.get('summary', {}).get('included_documents'),
            'document_errors': [{'name': doc['name'], 'error': doc['error']} for doc in case['documents'] if doc.get('error')],
            'ocr': result.get('ocr'), 'total_metric': total, 'phases': phases, 'gpu_samples': samples}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--runs', type=int, choices=range(1, 6), default=1)
    parser.add_argument('--timeout', type=float, default=1800)
    parser.add_argument('--output', type=Path, default=Path('.runtime/demo-benchmark.json'))
    args = parser.parse_args()
    report = {'base_url': args.base_url, 'runs': []}
    for iteration in range(1, args.runs + 1):
        run = measure(args.base_url.rstrip('/'), iteration, args.timeout)
        report['runs'].append(run)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({key: run[key] for key in ('iteration', 'case_id', 'status', 'processing_seconds',
                                                  'observed_seconds', 'documents', 'ocr')}, ensure_ascii=False), flush=True)
        if run['status'] != 'completed' or run['document_errors']:
            raise RuntimeError('Замер сохранён, но при обработке возникли ошибки. См. отчёт.')


if __name__ == '__main__':
    main()
