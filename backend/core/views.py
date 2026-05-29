from django.shortcuts import render

# Create your views here.

from django.contrib.gis.geos import Point
from django.http import JsonResponse
import json
from .models import Watershed


def watershed_lookup(request):
    lat = request.GET.get('lat')
    lng = request.GET.get('lng')

    if not lat or not lng:
        return JsonResponse({
            'error': 'lat and lng required'
        }, status=400)

    point = Point(float(lng), float(lat), srid=4326)

    watershed = Watershed.objects.filter(
        geom__contains=point
    ).first()

    if not watershed:
        return JsonResponse({
            'error': 'No watershed found test1 sample'
        }, status=404)

    return JsonResponse({
        'fid': watershed.fid,
        'id': watershed.id,
        'dn': watershed.dn,
        'uid': watershed.uid,
        'geom': json.loads(watershed.geom.geojson),
    })
