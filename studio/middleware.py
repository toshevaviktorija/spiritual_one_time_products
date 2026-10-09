from django.utils.cache import add_never_cache_headers


class SearchIndexingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path in ('/natal-chart/', '/redeem-free-natal-chart/', '/reviews/', '/enquiries/'):
            add_never_cache_headers(response)
        if request.path.startswith(('/admin/', '/studio/', '/orders/', '/stripe/', '/data-removal/', '/checkout-demo/')) or request.path in ('/natal-chart/thanks/', '/csrf-token/'):
            response['X-Robots-Tag'] = 'noindex, nofollow'
        return response
