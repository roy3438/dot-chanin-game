import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ROLES = [
    ('Planning', 'Define scope and clear acceptance criteria.'),
    ('Design', 'Review mobile usability, touch areas and accessibility.'),
    ('Development', 'Identify concrete safe changes in the actual source. Do not edit files.'),
    ('QA', 'Propose tests and identify unverified risks. Do not claim browser testing.'),
    ('Operations', 'Propose measurable usage metrics. Do not invent data.'),
]


def call_model(model, prompt):
    url = ('https://generativelanguage.googleapis.com/v1beta/models/'
           + model + ':generateContent')
    data = json.dumps({
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {'temperature': 0.2, 'ma' + chr(120) + 'OutputTokens': 1400},
    }).encode('utf-8')
    request = urllib.request.Request(
        url, data=data, method='POST',
        headers={
            'Content-Type': 'application/json',
            chr(120) + '-goog-api-key': os.environ['GEMINI_API_KEY'],
        },
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=80) as reply:
                result = json.load(reply)
            parts = [part.get('text', '')
                     for item in result.get('candidates', [])
                     for part in item.get('content', {}).get('parts', [])]
            answer = '\n'.join(part for part in parts if part).strip()
            if not answer:
                raise RuntimeError('Model returned no readable answer')
            return answer
        except urllib.error.HTTPError as error:
            if error.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            raise RuntimeError('Gemini HTTP ' + str(error.code)
                               + '. Check model availability and API quota.') from None


def main():
    if not os.getenv('GEMINI_API_KEY'):
        raise RuntimeError('Missing GEMINI_API_KEY secret')
    model = os.getenv('GEMINI_MODEL', '').strip()
    if not model:
        raise RuntimeError('Missing GEMINI_MODEL repository variable')
    source_path = Path('inde' + chr(120) + '.html')
    if not source_path.is_file():
        raise RuntimeError('Missing game HTML file in repository root')
    source = source_path.read_text(encoding='utf-8')
    if len(source) > 40000:
        source = source[:40000] + '\n[Source truncated at 40000 characters]'
    task = os.getenv('TASK', 'Review DOT CHAIN without code changes.')[:3000]
    report = [
        '# DOT CHAIN - AI source review', '',
        '**Owner task:** ' + task, '',
        '**Source:** game HTML (up to first 40000 characters)', '',
        '**Safety:** No game code changed; no browser test performed.', '',
        '**Model:** ' + model, '',
    ]
    handoffs = ''
    try:
        for role, guidance in ROLES:
            print('Running:', role, flush=True)
            prompt = (
                'You are the ' + role + ' role in the DOT CHAIN studio. '
                + guidance + '\nRespond in Korean with concrete observations. '
                'Separate facts confirmed in the source from ideas and unknowns. '
                'Do not claim to have run the game or measured users. '
                'No changes are authorized.\n\nOwner task:\n' + task
                + '\n\nActual game HTML source:\n' + source
                + '\n\nEarlier role handoffs:\n' + handoffs[-7000:]
            )
            answer = call_model(model, prompt)
            report.extend(['## ' + role, '', answer, ''])
            handoffs += '\n' + role + ': ' + answer
        report.extend([
            '## Owner approval', '',
            'This report is advisory. No source changes or deployment occurred.',
        ])
    finally:
        Path('ai-source-review.md').write_text(
            '\n'.join(report) + '\n', encoding='utf-8'
        )


if __name__ == '__main__':
    main()
