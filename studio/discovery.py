from xml.etree.ElementTree import Element, SubElement, tostring

from django.conf import settings
from django.http import HttpResponse
from django.urls import reverse
from django.views.decorators.http import require_GET


PUBLIC_PAGE_NAMES = ('home', 'enquire', 'redeem-free-natal-chart', 'reviews')


@require_GET
def sitemap(request):
    root = Element('urlset', xmlns='http://www.sitemaps.org/schemas/sitemap/0.9')
    for name in PUBLIC_PAGE_NAMES:
        url = SubElement(root, 'url')
        SubElement(url, 'loc').text = settings.PUBLIC_BASE_URL + reverse(name)
    return HttpResponse(tostring(root, encoding='utf-8', xml_declaration=True), content_type='application/xml')


@require_GET
def robots(request):
    # Private paths receive noindex headers rather than being advertised here.
    body = 'User-agent: *\nDisallow:\n\nSitemap: ' + settings.PUBLIC_BASE_URL + reverse('sitemap') + '\n'
    return HttpResponse(body, content_type='text/plain')
