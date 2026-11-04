"""Run safe authenticated connection checks without inference or messages."""
import json
import os
from pathlib import Path
import sys
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.connection_diagnostics import check_provider


def main():
    credentials = dict(os.environ)
    # Read only the project's ignored secret files; never print their values.
    try:
        from dotenv import dotenv_values
        for key, value in dotenv_values('.env').items():
            if value and not credentials.get(key):
                credentials[key] = value
    except ImportError:
        pass
    path = Path('.streamlit/secrets.toml')
    if path.is_file():
        try:
            for key, value in tomllib.loads(path.read_text(encoding='utf-8')).items():
                if isinstance(value, str) and not credentials.get(key):
                    credentials[key] = value
        except (OSError, ValueError):
            print(json.dumps({'status': 'invalid_secret_file'}))
            return 1
    results = {
        'groq': check_provider('groq', credentials.get('GROQ_API_KEY'),
                               model='openai/gpt-oss-120b'),
        'google': check_provider('google', credentials.get('GOOGLE_API_KEY'),
                                 model=credentials.get('GOOGLE_MODEL', 'gemini-3.6-flash')),
        'telegram': check_provider('telegram', credentials.get('TELEGRAM_TOKEN')),
    }
    print(json.dumps(results, sort_keys=True))
    return 0 if all(value['status'] == 'verified' for value in results.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
