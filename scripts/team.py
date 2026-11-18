import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ROLES = [
    ('Planning', 'Define the task scope and acceptance criteria. No unapproved feature changes.'),
    ('Design', 'Review the planning handoff; propose mobile UI and accessibility checks.'),
    ('Development', 'Read the handoffs and produce an implementation plan only. Do not edit code.'),
    ('QA', 'Independently identify test cases, risks and unverified assumptions.'),
    ('Operations', 'Specify measurable engagement metrics and a decision rule. Do not invent data.'),
]


def ask(role, guidance, task, handoffs):
    model = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash-lite')
    url = 'https://generativelanguage.googleapis.com/v1beta/models/' + model + ':generateContent'
    message = ('You are the ' + role + ' team in DOT CHAIN. ' + guidance +
               ' Respond in Korean, under 350 Korean words. Distinguish verified facts from suggestions.\n\n' +
               'Owner task:\n' + task + '\n\nPrior team reports:\n' + handoffs[-9000:])
    payload = {
        'contents': [{'parts': [{'text': message}]}],
        'generationConfig': {'maxOutputTokens': 1000, 'temperature': 0.3},
    }
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode('utf-8'), method='POST',
        headers={'Content-Type': 'application/json', 'x-goog-api-key': os.environ['GEMINI_API_KEY']},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=75) as response:
                result = json.load(response)
            chunks = [part.get('text', '') for item in result.get('candidates', [])
                      for part in item.get('content', {}).get('parts', [])]
            answer = '\n'.join(chunk for chunk in chunks if chunk).strip()
            if not answer:
                raise RuntimeError('No readable response for ' + role)
            return answer
        except urllib.error.HTTPError as err:
            # Avoid printing response bodies: they can include request details.
            if err.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            raise RuntimeError('Gemini request failed for ' + role + ' (HTTP ' + str(err.code) + ')') from None


def main():
    if not os.getenv('GEMINI_API_KEY'):
        raise RuntimeError('GEMINI_API_KEY is missing from GitHub Actions secrets')
    task = os.getenv('TASK', 'Review DOT CHAIN without code changes.')[:3000]
    report = '# DOT CHAIN AI team report\n\n## Owner request\n' + task + '\n'
    handoffs = ''
    path = Path('ai-team-report.md')
    for role, guidance in ROLES:
        print('Running:', role, flush=True)
        try:
            answer = ask(role, guidance, task, handoffs)
        except Exception as err:
            path.write_text(report + '\n## Failure\n' + str(err) + '\n', encoding='utf-8')
            raise
        report += '\n## ' + role + '\n' + answer + '\n'
        handoffs += '\n' + role + ':\n' + answer
        path.write_text(report, encoding='utf-8')
    report += '\n## Approval gate\nNo source files or deployment were changed. Owner approval is required.\n'
    path.write_text(report, encoding='utf-8')


if __name__ == '__main__':
    main()
