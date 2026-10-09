from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@never_cache
@require_GET
def token(request):
    # Same-origin fetch refreshes stale form tokens without changing entered data.
    return JsonResponse({'token': get_token(request)})


@never_cache
def failure(request, reason=''):
    return render(request, 'studio/csrf_failure.html', {'retry_path': request.path}, status=403)
