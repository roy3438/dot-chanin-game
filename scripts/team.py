import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = 'https://generativelanguage.googleapis.com/v1beta'
ROLES = [
    ('Planning', 'Define scope, priorities and acceptance criteria; no unapproved features.'),
    ('Design', 'Use prior handoffs; review mobile usability and accessibility.'),
    ('Development', 'Use prior handoffs; propose implementation only, never modify code.'),
    ('QA', 'Independently identify tests, risks and assumptions.'),
    ('Operations', 'Define measurable engagement metrics and decision gates; never invent data.'),
]


def request_json(method, url, payload=None):
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, method=method, headers={
        'Content-Type': 'application/json',
        'x-goog-api-key': os.environ['GEMINI_API_KEY'],
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=75) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            try:
                body = json.loads(error.read().decode('utf-8'))
                detail = body.get('error', {}).get('message', '')
            except (ValueError, UnicodeError):
                detail = 'No readable error details'
            if error.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            raise RuntimeError('Gemini HTTP ' + str(error.code) + ': ' + detail[:600]) from None
        except urllib.error.URLError as error:
            raise RuntimeError('Gemini network error: ' + str(error.reason)) from None


def available_models():
    models = []
    page = ''
    while True:
        url = API + '/models?pageSize=100'
        if page:
            url += '&pageToken=' + urllib.parse.quote(page)
        response = request_json('GET', url)
        for item in response.get('models', []):
            if 'generateContent' in item.get('supportedGenerationMethods', []):
                models.append(item['name'].removeprefix('models/'))
        page = response.get('nextPageToken', '')
        if not page:
            break
    return models


def select_model(models):
    configured = os.getenv('GEMINI_MODEL', '').strip().removeprefix('models/')
    preferred = [configured, 'gemini-2.5-flash-lite', 'gemini-2.5-flash', 'gemini-2.0-flash-lite', 'gemini-2.0-flash']
    for name in preferred:
        if name and name in models:
            return name
    flash = [name for name in models if 'flash' in name.lower() and 'preview' not in name.lower()]
    if flash:
        return sorted(flash)[0]
    if models:
        return models[0]
    raise RuntimeError('No models with generateContent access were returned for this API key.')


def ask(model, role, guidance, task, handoffs):
    prompt = (
        'You are the ' + role + ' team in DOT CHAIN. ' + guidance +
        ' Answer in Korean in fewer than 350 words. Distinguish verified facts from proposals. '
        'Only the owner task and prior team reports are supplied, not actual game source code or analytics. '
        'Do not claim to have inspected them.\n\nOwner task:\n' + task +
        '\n\nPrior team reports:\n' + handoffs[-9000:]
    )
    response = request_json('POST', API + '/models/' + urllib.parse.quote(model) + ':generateContent', {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {'maxOutputTokens': 1400, 'temperature': 0.3},
    })
    parts = [part.get('text', '') for item in response.get('candidates', [])
             for part in item.get('content', {}).get('parts', [])]
    answer = '\n'.join(part for part in parts if part).strip()
    if not answer:
        raise RuntimeError('No text returned for ' + role + '. Finish reason: ' +
                           str([item.get('finishReason') for item in response.get('candidates', [])]))
    return answer


def main():
    report = Path('ai-team-report.md')
    lines = ['# DOT CHAIN AI team collaboration report', '',
             '**Mode:** Review only; no code changes or deployment.', '']
    try:
        if not os.getenv('GEMINI_API_KEY'):
            raise RuntimeError('GEMINI_API_KEY is missing from repository Actions secrets.')
        print('Checking available Gemini models for this API key...', flush=True)
        models = available_models()
        model = select_model(models)
        print('Selected model:', model, flush=True)
        task = os.getenv('TASK', 'Review DOT CHAIN without changing code.')[:3000]
        lines += ['**Task:** ' + task, '**Selected model:** ' + model, '']
        handoffs = ''
        for role, guidance in ROLES:
            print('Running:', role, flush=True)
            answer = ask(model, role, guidance, task, handoffs)
            lines += ['## ' + role, '', answer, '']
            handoffs += '\n## ' + role + '\n' + answer + '\n'
            report.write_text('\n'.join(lines), encoding='utf-8')
        lines += ['**Status:** All five roles completed. Human approval required for changes.']
        report.write_text('\n'.join(lines), encoding='utf-8')
        print('All five roles completed.', flush=True)
    except Exception as error:
        message = str(error)
        print('ERROR:', message, flush=True)
        lines += ['## Execution failed', '', message, '',
                  'Do not rerun until the failure is reviewed.']
        report.write_text('\n'.join(lines), encoding='utf-8')
        raise SystemExit(1)


if __name__ == '__main__':
    main()
