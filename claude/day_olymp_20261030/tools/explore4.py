from olympiads.models import OlympiadVariantItem as I, OlympiadVariant as V
for vid in (561,562):
    v=V.objects.get(pk=vid); print('==', vid, v.season, v.tour, v.stage, v.kit_key, v.ref_event_id, list(v.grades.values_list('grade',flat=True)) if hasattr(v,'grades') else '')
    for it in v.items.all().order_by('order'):
        print('  ', it.id, it.ref_key, it.number, it.task_variant, it.order, it.max_score, it.problem_id, it.problem.title[:40], it.quality, it.quality_reasons, it.pages.get('source_file'))
