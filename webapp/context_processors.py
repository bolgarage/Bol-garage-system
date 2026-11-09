from .models import Inquiry


def customer_inquiries(request):
    user_inquiries = Inquiry.objects.none()
    show_inquiry_status = False

    match = getattr(request, 'resolver_match', None)
    if (
        request.user.is_authenticated
        and request.user.role == 'buyer'
        and match
        and match.url_name not in {'sign_in', 'sign_up'}
    ):
        user_inquiries = (
            Inquiry.objects.filter(
                buyer=request.user,
                status__in=['new', 'contacted'],
            )
            .select_related('car')
            .order_by('-created_at')
        )
        show_inquiry_status = True

    return {
        'user_inquiries': user_inquiries,
        'show_inquiry_status': show_inquiry_status,
    }
