"""Checked 33-variant import for a maintenance window. Run inside the web container.

Does not migrate, rescore, delete accounts or send notifications. Plan is the default.
Production use is documented separately; this session runs it only on rehearsal DBs.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys

if not __debug__:
    raise RuntimeError('Validation requires normal Python mode: do not use -O/PYTHONOPTIMIZE')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def inspect(directory):
    import yaml
    from vp.loader import normalize, write_variant
    from vp.models import VPAttempt, VPItem, VPVariant
    manifest = json.loads((directory / 'variants-manifest.json').read_text())
    assert len(manifest) == 33
    parsed = []
    for row in manifest:
        rel = Path(row['path'])
        assert len(rel.parts) == 1 and rel.suffix == '.yaml'
        data = (directory / rel).read_bytes()
        assert hashlib.sha256(data).hexdigest() == row['sha256'], rel
        item = normalize(yaml.safe_load(data))
        assert not item.errors and not item.warnings, (rel, item.errors, item.warnings)
        parsed.append(item)
    slugs = [x.variant['slug'] for x in parsed]
    assert len(set(slugs)) == 33 and sum(len(x.items) for x in parsed) == 583
    changes = []
    for item in parsed:
        result = write_variant(item, publish=True, dry_run=True)
        changed = not result.is_noop
        active = VPAttempt.objects.filter(variant__slug=item.variant['slug'], submitted_at__isnull=True).count()
        changes.append({'slug': item.variant['slug'], 'change': asdict(result), 'changed': changed,
                        'active_attempts': active, 'blocked': changed and active > 0})
    state = {'variants': list(VPVariant.objects.filter(slug__in=slugs).order_by('slug').values()),
             'items': list(VPItem.objects.filter(variant__slug__in=slugs).order_by('variant_id', 'number').values())}
    plan = {'variants': 33, 'items': 583, 'source_sha256': digest(manifest),
            'existing_content_sha256': digest(state), 'changes': changes}
    return parsed, slugs, plan


def history(slugs):
    from vp.models import VPAnswer, VPAttempt
    return digest({'attempts': list(VPAttempt.objects.filter(variant__slug__in=slugs).order_by('pk').values()),
                   'answers': list(VPAnswer.objects.filter(attempt__variant__slug__in=slugs).order_by('pk').values())})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True, type=Path)
    parser.add_argument('--expect-database', required=True)
    parser.add_argument('--mode', choices=['plan', 'apply', 'verify'], default='plan')
    parser.add_argument('--expected-plan-sha256')
    parser.add_argument('--backup-sha256')
    parser.add_argument('--maintenance-confirmed', action='store_true')
    args = parser.parse_args()
    sys.path.insert(0, os.getcwd())
    import django
    django.setup()
    from django.conf import settings
    from django.db import transaction
    from vp.loader import write_variant
    assert settings.DATABASES['default']['NAME'] == args.expect_database, 'Wrong database'
    # All validation is performed before the first write. One outer transaction covers all 33 files.
    with transaction.atomic():
        parsed, slugs, plan = inspect(args.directory)
        plan_hash = digest(plan)
        if args.mode == 'verify':
            assert not any(x['changed'] for x in plan['changes']), 'Imported data differs'
        if args.mode == 'apply':
            assert args.maintenance_confirmed, 'Maintenance window required'
            assert args.expected_plan_sha256 == plan_hash, 'Plan changed: inspect a fresh plan'
            assert args.backup_sha256 and len(args.backup_sha256) == 64 and all(x in '0123456789abcdef' for x in args.backup_sha256), 'Verified backup SHA-256 required'
            assert not any(x['blocked'] for x in plan['changes']), 'Active attempts on changed variants'
            before = history(slugs)
            for item in parsed:
                write_variant(item, publish=True)
            assert history(slugs) == before, 'History changed unexpectedly'
            assert all(write_variant(item, publish=True, dry_run=True).is_noop for item in parsed)
        report = {'mode': args.mode, 'database': args.expect_database, 'plan_sha256': plan_hash,
                  'blocked_by_active_attempts': any(x['blocked'] for x in plan['changes']),
                  'history_unchanged_by_import': args.mode == 'apply', 'plan': plan}
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 2 if report['blocked_by_active_attempts'] and args.mode == 'plan' else 0


if __name__ == '__main__':
    sys.exit(main())
