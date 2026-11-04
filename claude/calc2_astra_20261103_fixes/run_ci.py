"""Пять групп CI исправлений, только собственные синтетические сервисы."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from claude.calc2_astra_20261102 import run_final_ci as ci

ci.LOGS = Path('/private/tmp/calc2-fixes-active-20261103/ci')
base_environment = ci.environment


def environment():
    env = base_environment()
    env['DATABASE_URL'] = 'postgres://calc2_synthetic@127.0.0.1:61383/calc2_fixes_20261103'
    env['TEST_DATABASE_NAME'] = 'test_calc2_fixes_20261103'
    return env


ci.environment = environment
if __name__ == '__main__':
    sys.exit(ci.main())
