# -*- coding: utf-8 -*-
"""Онбординг — заготовка фазы 2, шаги пишутся в фазе 3."""
from django.http import Http404
from django.shortcuts import redirect


def entry(request):
    return redirect('/')


def plan(request):
    raise Http404


def step(request, step):
    raise Http404
